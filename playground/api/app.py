"""Stateless FastAPI backend for the hosted DataForge playground.

The hosted playground is intentionally split across two free-tier hosts:

- Cloudflare Workers Static Assets serves the static frontend.
- Hugging Face Spaces serves this API-only backend.

All uploaded data is processed in memory or under a per-request temporary
directory and is discarded before the request completes.
"""

import asyncio
import io
import logging
import os
import re
import tempfile
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, TypeVar, cast

import pandas as pd
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pandas.errors import EmptyDataError, ParserError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from dataforge import (
    CONTRACT_VERSION,
    Issue,
    RepairPipelineRequest,
    RepairTransaction,
    Severity,
    VerifiedFix,
    run_all_detectors,
    run_repair_pipeline,
)
from dataforge.http.problem import problem_exception_handler, problem_response
from dataforge.observability import configure_fastapi_observability


class FallbackRateLimitExceededError(Exception):
    """Fallback exception shape matching slowapi's detail attribute."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


try:
    _slowapi_module = import_module("slowapi")
    _slowapi_errors = import_module("slowapi.errors")
    _slowapi_util = import_module("slowapi.util")
    _SlowapiLimiter: Any | None = _slowapi_module.Limiter
    _SlowapiRateLimitExceeded: type[Exception] | None = _slowapi_errors.RateLimitExceeded
    get_remote_address = cast(Callable[[Request], str], _slowapi_util.get_remote_address)

    SLOWAPI_AVAILABLE = True
except ModuleNotFoundError:
    _SlowapiLimiter = None
    _SlowapiRateLimitExceeded = None
    SLOWAPI_AVAILABLE = False

    def get_remote_address(request: Request) -> str:
        """Return the client host for fallback rate-limit keys."""
        return request.client.host if request.client else "unknown"


_CallableT = TypeVar("_CallableT", bound=Callable[..., Any])


class _StorageLike(Protocol):
    """Minimal storage protocol used by tests and fallback middleware."""

    def reset(self) -> None: ...


class _LimiterLike(Protocol):
    """Minimal limiter protocol shared by slowapi and the fallback."""

    _storage: _StorageLike

    def limit(self, limit_value: str) -> Callable[[_CallableT], _CallableT]: ...


class _FallbackStorage:
    """Small in-memory windowed counter used when slowapi is unavailable."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], list[float]] = defaultdict(list)

    def reset(self) -> None:
        """Clear all fallback counters."""
        self._hits.clear()

    def allow(self, key: tuple[str, str], *, limit: int, window_seconds: float) -> bool:
        """Record a hit and return whether it fits inside the window."""
        now = time.monotonic()
        hits = [seen for seen in self._hits[key] if now - seen < window_seconds]
        hits.append(now)
        self._hits[key] = hits
        return len(hits) <= limit


class _FallbackLimiter:
    """Decorator-compatible fallback limiter."""

    def __init__(self) -> None:
        self._storage: _StorageLike = _FallbackStorage()

    def limit(self, _limit_value: str) -> Callable[[_CallableT], _CallableT]:
        """Return an identity decorator; middleware enforces the limit."""

        def decorator(func: _CallableT) -> _CallableT:
            return func

        return decorator


_RateLimitExceeded: type[Exception] = (
    _SlowapiRateLimitExceeded
    if _SlowapiRateLimitExceeded is not None
    else FallbackRateLimitExceededError
)

logger = logging.getLogger("playground.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def _positive_int_env(name: str, default: int) -> int:
    """Return a positive integer env override, falling back safely."""
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


MAX_UPLOAD_BYTES = _positive_int_env("DATAFORGE_PLAYGROUND_MAX_UPLOAD_BYTES", 1_048_576)
MAX_MULTIPART_OVERHEAD_BYTES = 16_384
MAX_UPLOAD_ROWS = _positive_int_env("DATAFORGE_PLAYGROUND_MAX_ROWS", 10_000)
MAX_UPLOAD_COLUMNS = _positive_int_env("DATAFORGE_PLAYGROUND_MAX_COLUMNS", 128)
MAX_UPLOAD_CELLS = _positive_int_env("DATAFORGE_PLAYGROUND_MAX_CELLS", 200_000)
REQUEST_TIMEOUT_SECONDS = _positive_int_env("DATAFORGE_PLAYGROUND_TIMEOUT_SECONDS", 20)
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
SLOWAPI_CONFIG = Path(__file__).resolve().parent / "slowapi.env"
ALLOWED_SAMPLES = {"hospital_10rows", "flights_10rows", "beers_10rows"}
ACCEPTED_UPLOAD_TYPES = {"", "text/csv", "text/plain", "application/vnd.ms-excel"}
OTEL_ENABLED_VALUES = {"1", "true", "yes", "on"}


class _RequestMetrics:
    """Tiny in-process request counters for free-tier health reporting."""

    def __init__(self, window_size: int = 200) -> None:
        self._lock = Lock()
        self._window_size = window_size
        self._latencies_ms: deque[float] = deque(maxlen=window_size)
        self._requests_total = 0
        self._responses_4xx = 0
        self._responses_5xx = 0
        self._routes: dict[str, int] = defaultdict(int)

    def record(self, *, method: str, path: str, status_code: int, duration_ms: float) -> None:
        """Record one completed request."""
        with self._lock:
            self._requests_total += 1
            self._latencies_ms.append(duration_ms)
            self._routes[f"{method} {path}"] += 1
            if 400 <= status_code < 500:
                self._responses_4xx += 1
            elif status_code >= 500:
                self._responses_5xx += 1

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-safe metrics snapshot."""
        with self._lock:
            latencies = sorted(self._latencies_ms)
            total = self._requests_total
            responses_5xx = self._responses_5xx
            return {
                "requests_total": total,
                "responses_4xx": self._responses_4xx,
                "responses_5xx": responses_5xx,
                "error_rate": round(responses_5xx / total, 4) if total else 0.0,
                "latency_ms": {
                    "window_size": len(latencies),
                    "p50": _percentile(latencies, 0.50),
                    "p95": _percentile(latencies, 0.95),
                    "max": round(latencies[-1], 2) if latencies else 0.0,
                },
                "routes": dict(sorted(self._routes.items())),
            }


def _percentile(values: list[float], percentile: float) -> float:
    """Return a nearest-rank percentile for a small rolling window."""
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int(round(percentile * (len(values) - 1)))))
    return round(values[index], 2)


request_metrics = _RequestMetrics()


def _request_id(request: Request) -> str | None:
    """Return the current request id when request middleware has assigned one."""
    request_id = getattr(request.state, "dataforge_request_id", None)
    return request_id if isinstance(request_id, str) and request_id else None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request IDs, duration headers, and lightweight metrics."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.dataforge_request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            request_metrics.record(
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=duration_ms,
            )
            logger.exception(
                "Playground request crashed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        request_metrics.record(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["X-DataForge-Request-Id"] = request_id
        response.headers["X-DataForge-Duration-Ms"] = f"{duration_ms:.2f}"
        logger.info(
            "Playground request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response


class SizeCapMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared Content-Length cannot contain a valid upload."""

    def __init__(
        self,
        app: ASGIApp,
        max_file_bytes: int = MAX_UPLOAD_BYTES,
        max_multipart_overhead_bytes: int = MAX_MULTIPART_OVERHEAD_BYTES,
    ) -> None:
        super().__init__(app)
        self.max_file_bytes = max_file_bytes
        self.max_body_bytes = max_file_bytes + max_multipart_overhead_bytes

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Check Content-Length before any request body is read."""
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                return problem_response(
                    status=400,
                    type_="https://dataforge.local/problems/invalid_content_length",
                    title="Invalid Content Length",
                    detail="The Content-Length header must be an integer.",
                    instance=str(request.url.path),
                    error="invalid_content_length",
                    request_id=_request_id(request),
                )
            if length > self.max_body_bytes:
                logger.warning(
                    "Rejected request: Content-Length %d exceeds max body %d",
                    length,
                    self.max_body_bytes,
                )
                return problem_response(
                    status=413,
                    type_="https://dataforge.local/problems/file_too_large",
                    title="File Too Large",
                    detail="The uploaded request body exceeds the playground limit.",
                    instance=str(request.url.path),
                    error="file_too_large",
                    max_bytes=self.max_file_bytes,
                    request_id=_request_id(request),
                )
        return await call_next(request)


class FallbackRateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce the playground POST limit when slowapi is not installed."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Apply a 10/minute in-memory fallback to mutating playground endpoints."""
        if request.method == "POST" and request.url.path in {"/api/profile", "/api/repair"}:
            storage = limiter._storage
            key = (get_remote_address(request), request.url.path)
            if isinstance(storage, _FallbackStorage) and not storage.allow(
                key,
                limit=10,
                window_seconds=60.0,
            ):
                return problem_response(
                    status=429,
                    type_="https://dataforge.local/problems/rate_limit_exceeded",
                    title="Rate Limit Exceeded",
                    detail="10 per 1 minute",
                    instance=str(request.url.path),
                    headers={"Retry-After": "60"},
                    error="rate_limit_exceeded",
                    retry_after=60,
                    request_id=_request_id(request),
                )
        return await call_next(request)


class OriginGuardMiddleware(BaseHTTPMiddleware):
    """Reject browser requests from origins outside the configured allowlist."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        allow_origins: list[str],
        allow_origin_regex: str | None,
    ) -> None:
        super().__init__(app)
        self._allow_origins = frozenset(allow_origins)
        self._allow_origin_pattern = (
            re.compile(allow_origin_regex) if allow_origin_regex is not None else None
        )

    def _allowed(self, origin: str) -> bool:
        if origin in self._allow_origins:
            return True
        return bool(
            self._allow_origin_pattern is not None and self._allow_origin_pattern.fullmatch(origin)
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Deny disallowed browser origins before endpoint handlers run."""
        origin = request.headers.get("origin")
        if origin and not self._allowed(origin):
            return problem_response(
                status=403,
                type_="https://dataforge.local/problems/origin_not_allowed",
                title="Origin Not Allowed",
                detail="This playground backend only accepts browser requests from configured frontend origins.",
                instance=str(request.url.path),
                error="origin_not_allowed",
                request_id=_request_id(request),
            )
        return await call_next(request)


if _SlowapiLimiter is not None:
    limiter: _LimiterLike = cast(
        _LimiterLike,
        _SlowapiLimiter(key_func=get_remote_address, config_filename=str(SLOWAPI_CONFIG)),
    )
else:
    limiter = _FallbackLimiter()


def _advanced_available() -> bool:
    """Return whether at least one backend LLM provider is configured."""
    return bool(os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY"))


def _build_cors_origins() -> list[str]:
    """Build the explicit CORS allowlist from the environment."""
    env_origins = os.environ.get("DATAFORGE_PLAYGROUND_ORIGINS", "")
    return [origin.strip() for origin in env_origins.split(",") if origin.strip()]


def _build_cors_origin_regex() -> str | None:
    """Build the regex allowlist for local development only."""
    patterns: list[str] = []
    if os.environ.get("DATAFORGE_PLAYGROUND_DEV") == "1":
        patterns.append(r"http://(?:localhost|127(?:\.\d{1,3}){3})(?::\d+)?")
    if not patterns:
        return None
    return "^(" + "|".join(patterns) + ")$"


CORS_ORIGINS = _build_cors_origins()
CORS_ORIGIN_REGEX = _build_cors_origin_regex()


app = FastAPI(
    title="DataForge Playground API",
    description="Stateless backend for the hosted DataForge playground.",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
)
app.add_middleware(
    SizeCapMiddleware,
    max_file_bytes=MAX_UPLOAD_BYTES,
    max_multipart_overhead_bytes=MAX_MULTIPART_OVERHEAD_BYTES,
)
if not SLOWAPI_AVAILABLE:
    app.add_middleware(FallbackRateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)
app.add_middleware(
    OriginGuardMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
)
app.add_middleware(RequestContextMiddleware)
app.state.limiter = limiter
app.add_exception_handler(HTTPException, problem_exception_handler)
OTEL_INSTRUMENTED = configure_fastapi_observability(app, service_name="dataforge-playground-api")


@app.exception_handler(_RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a machine-readable 429 response."""
    detail = str(getattr(exc, "detail", str(exc)))
    return problem_response(
        status=429,
        type_="https://dataforge.local/problems/rate_limit_exceeded",
        title="Rate Limit Exceeded",
        detail=detail,
        instance=str(request.url.path),
        headers={"Retry-After": "60"},
        error="rate_limit_exceeded",
        retry_after=60,
        request_id=_request_id(request),
    )


def _upload_problem(
    *,
    status_code: int,
    error: str,
    message: str,
    **extensions: Any,
) -> HTTPException:
    """Build an HTTPException that normalizes to problem+json."""
    return HTTPException(
        status_code=status_code,
        detail={"error": error, "message": message, **extensions},
    )


def _validate_upload_file(file: UploadFile) -> None:
    """Reject clearly unsupported upload metadata before reading bytes."""
    upload_name = Path(file.filename or "upload.csv").name
    content_type = (file.content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if not upload_name.lower().endswith(".csv") and content_type not in ACCEPTED_UPLOAD_TYPES:
        raise _upload_problem(
            status_code=415,
            error="unsupported_file_type",
            message="Upload a CSV file with a .csv extension or text/csv content type.",
            accepted_types=sorted(ACCEPTED_UPLOAD_TYPES - {""}),
        )


async def _read_upload(file: UploadFile) -> bytes:
    """Read an uploaded file with a defensive hard cap."""
    _validate_upload_file(file)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise _upload_problem(
            status_code=413,
            error="file_too_large",
            message="The uploaded CSV is larger than the hosted playground limit.",
            max_bytes=MAX_UPLOAD_BYTES,
        )
    if len(data) == 0:
        raise _upload_problem(
            status_code=400,
            error="empty_csv",
            message="CSV must include a header row and at least one data row.",
        )
    return data


def _csv_to_df(data: bytes) -> pd.DataFrame:
    """Parse CSV bytes into a string-preserving DataFrame."""
    try:
        df = pd.read_csv(
            io.BytesIO(data),
            dtype=str,
            keep_default_na=False,
            na_filter=False,
        )
    except EmptyDataError as exc:
        raise _upload_problem(
            status_code=400,
            error="empty_csv",
            message="CSV must include a header row and at least one data row.",
        ) from exc
    except ParserError as exc:
        raise _upload_problem(
            status_code=400,
            error="invalid_csv",
            message="CSV could not be parsed. Check quoting, delimiters, and row structure.",
        ) from exc

    if len(df.columns) == 0 or len(df) == 0:
        raise _upload_problem(
            status_code=400,
            error="empty_csv",
            message="CSV must include a header row and at least one data row.",
        )
    _enforce_dataframe_limits(df)
    return df


def _enforce_dataframe_limits(df: pd.DataFrame) -> None:
    """Apply hosted playground row, column, and cell limits after parsing."""
    row_total = len(df)
    column_total = len(df.columns)
    cell_total = row_total * column_total
    if row_total > MAX_UPLOAD_ROWS:
        raise _upload_problem(
            status_code=413,
            error="too_many_rows",
            message="The uploaded CSV has more rows than the hosted playground allows.",
            max_rows=MAX_UPLOAD_ROWS,
            observed_rows=row_total,
        )
    if column_total > MAX_UPLOAD_COLUMNS:
        raise _upload_problem(
            status_code=413,
            error="too_many_columns",
            message="The uploaded CSV has more columns than the hosted playground allows.",
            max_columns=MAX_UPLOAD_COLUMNS,
            observed_columns=column_total,
        )
    if cell_total > MAX_UPLOAD_CELLS:
        raise _upload_problem(
            status_code=413,
            error="too_many_cells",
            message="The uploaded CSV has too many cells for the hosted playground.",
            max_cells=MAX_UPLOAD_CELLS,
            observed_cells=cell_total,
        )


def _severity_to_str(severity: Severity) -> str:
    """Convert a Severity enum into the JSON response value."""
    return severity.value


def _issues_to_response(
    issues: list[Issue],
    df: pd.DataFrame,
    *,
    advanced_requested: bool,
) -> dict[str, Any]:
    """Format detected issues into the public playground JSON contract."""
    grouped: dict[tuple[str, str, str], list[int]] = {}
    for issue in issues:
        key = (issue.column, issue.issue_type, _severity_to_str(issue.severity))
        grouped.setdefault(key, []).append(issue.row)

    payload_issues: list[dict[str, Any]] = []
    for (column, issue_type, severity), row_indices in grouped.items():
        unique_rows = sorted(set(row_indices))
        payload_issues.append(
            {
                "column": column,
                "issue_type": issue_type,
                "severity": severity,
                "row_indices": unique_rows,
                "count": len(unique_rows),
            }
        )

    return {
        "issues": payload_issues,
        "meta": {
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": list(df.columns),
            "total_issues": len(issues),
            "advanced_requested": advanced_requested,
            "api_version": app.version,
            "contract_version": CONTRACT_VERSION,
        },
    }


def _fixes_to_response(
    fixes: list[VerifiedFix],
    transaction: RepairTransaction,
    *,
    receipt: Any,
    source_name: str,
) -> dict[str, Any]:
    """Format accepted repair proposals plus a redacted transaction journal."""
    payload_fixes: list[dict[str, Any]] = []
    for proposed_fix in fixes:
        payload_fixes.append(
            {
                "row": proposed_fix.row,
                "column": proposed_fix.column,
                "old_value": proposed_fix.old_value,
                "new_value": proposed_fix.new_value,
                "detector_id": proposed_fix.detector_id,
                "reason": proposed_fix.reason,
                "confidence": proposed_fix.confidence,
                "provenance": proposed_fix.provenance,
                "verifier_reason": proposed_fix.verifier_reason,
            }
        )

    return {
        "fixes": payload_fixes,
        "txn_journal": {
            "txn_id": transaction.txn_id,
            "created_at": transaction.created_at.isoformat(),
            "source_name": source_name,
            "source_sha256": transaction.source_sha256,
            "fixes_count": len(transaction.fixes),
            "applied": transaction.applied,
            "events": [{"event_type": "created"}],
            "note": (
                "Playground is stateless. This journal is ephemeral and discarded "
                "after the response. Install the CLI to apply and revert repairs."
            ),
        },
        "receipt": {
            "contract_version": receipt.contract_version,
            "safety_verdict": receipt.safety_verdict,
            "verifier_verdict": receipt.verifier_verdict,
            "issues_count": receipt.issues_count,
            "fixes_count": receipt.fixes_count,
            "candidate_provenance": receipt.candidate_provenance,
            "source_sha256": receipt.source_sha256,
            "reason": receipt.reason,
        },
        "meta": {
            "api_version": app.version,
            "contract_version": CONTRACT_VERSION,
        },
    }


def _require_advanced_mode(advanced_requested: bool) -> None:
    """Reject advanced mode requests unless a provider key is configured."""
    if advanced_requested and not _advanced_available():
        raise HTTPException(status_code=400, detail={"error": "advanced_mode_unavailable"})


def _run_repair_pipeline(
    *,
    upload_name: str,
    source_bytes: bytes,
    allow_llm: bool,
) -> tuple[list[VerifiedFix], RepairTransaction, Any]:
    """Run the real dry-run repair pipeline inside a temporary workspace."""
    _csv_to_df(source_bytes)
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_root = Path(tmpdir)
        upload_path = temp_root / upload_name
        upload_path.write_bytes(source_bytes)

        result = run_repair_pipeline(
            RepairPipelineRequest(
                source_path=upload_path,
                mode="dry_run",
                schema=None,
                create_dry_run_transaction=True,
                allow_llm=allow_llm,
            )
        )
        if result.transaction is None:
            raise RuntimeError(result.receipt.reason)
        return result.fixes, result.transaction, result.receipt


_ResultT = TypeVar("_ResultT")


async def _run_with_timeout(label: str, func: Callable[[], _ResultT]) -> _ResultT:
    """Run a blocking pipeline step with a public timeout failure mode."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(func),
            timeout=float(REQUEST_TIMEOUT_SECONDS),
        )
    except TimeoutError as exc:
        logger.warning("%s timed out after %d seconds", label, REQUEST_TIMEOUT_SECONDS)
        raise _upload_problem(
            status_code=504,
            error="request_timeout",
            message="The playground backend timed out before completing the request.",
            timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        ) from exc


def _profile_upload(source_bytes: bytes, *, advanced_requested: bool) -> dict[str, Any]:
    """Parse and profile a CSV upload in a worker thread."""
    df = _csv_to_df(source_bytes)
    issues = run_all_detectors(df, schema=None)
    return _issues_to_response(issues, df, advanced_requested=advanced_requested)


def _limits_payload() -> dict[str, int]:
    """Return processing limits exposed to the frontend and monitors."""
    return {
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_rows": MAX_UPLOAD_ROWS,
        "max_columns": MAX_UPLOAD_COLUMNS,
        "max_cells": MAX_UPLOAD_CELLS,
    }


def _environment_name() -> str:
    """Return a non-secret deployment environment label."""
    configured = os.environ.get("DATAFORGE_ENV") or os.environ.get("DATAFORGE_PLAYGROUND_ENV")
    if configured:
        return configured
    return "development" if os.environ.get("DATAFORGE_PLAYGROUND_DEV") == "1" else "production"


@app.get("/")
async def root() -> dict[str, Any]:
    """Return service metadata for humans and uptime probes."""
    return {
        "service": "DataForge Playground API",
        "status": "ok",
        "api_version": app.version,
        "contract_version": CONTRACT_VERSION,
        "docs_url": "/api/docs",
        "frontend_hosting": "cloudflare_static_assets",
    }


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Return backend readiness plus UI-facing capability metadata."""
    return {
        "service": "DataForge Playground API",
        "status": "ok",
        "advanced_available": _advanced_available(),
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "api_version": app.version,
        "contract_version": CONTRACT_VERSION,
        "build_sha": os.environ.get("DATAFORGE_BUILD_SHA")
        or os.environ.get("GITHUB_SHA")
        or "unknown",
        "server_time_utc": datetime.now(UTC).isoformat(),
        "environment": _environment_name(),
        "limits": _limits_payload(),
        "cors_configured": bool(CORS_ORIGINS or CORS_ORIGIN_REGEX),
        "otel_enabled": os.environ.get("DATAFORGE_OTEL_ENABLED", "").strip().lower()
        in OTEL_ENABLED_VALUES,
        "otel_instrumented": OTEL_INSTRUMENTED,
        "metrics": request_metrics.snapshot(),
    }


@app.get("/api/samples/{name}")
async def get_sample(name: str) -> StreamingResponse:
    """Return a bundled sample CSV by name."""
    if name not in ALLOWED_SAMPLES:
        raise HTTPException(
            status_code=404,
            detail={"error": "sample_not_found", "available": sorted(ALLOWED_SAMPLES)},
        )

    csv_path = SAMPLES_DIR / f"{name}.csv"
    if not csv_path.exists():
        logger.error("Sample file missing on disk: %s", csv_path)
        raise HTTPException(status_code=500, detail={"error": "sample_file_missing"})

    return StreamingResponse(
        io.BytesIO(csv_path.read_bytes()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


@app.post("/api/profile")
@limiter.limit("10/minute")
async def profile(request: Request, file: UploadFile) -> dict[str, Any]:
    """Profile an uploaded CSV and return the detected issues."""
    advanced_requested = request.query_params.get("advanced", "false").lower() == "true"
    _require_advanced_mode(advanced_requested)

    source_bytes = await _read_upload(file)
    upload_name = Path(file.filename or "upload.csv").name
    logger.info(
        "Profile request: filename=%s bytes=%d advanced=%s",
        upload_name,
        len(source_bytes),
        advanced_requested,
    )

    try:
        return await _run_with_timeout(
            "profile",
            lambda: _profile_upload(source_bytes, advanced_requested=advanced_requested),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Profile endpoint failed")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "profile_failed",
                "message": "The profile pipeline could not complete safely.",
            },
        ) from exc


@app.post("/api/repair")
@limiter.limit("10/minute")
async def repair(request: Request, file: UploadFile) -> dict[str, Any]:
    """Return dry-run repair proposals plus an ephemeral transaction journal."""
    dry_run = request.query_params.get("dry_run", "true").lower() == "true"
    advanced_requested = request.query_params.get("advanced", "false").lower() == "true"

    if not dry_run:
        raise HTTPException(status_code=400, detail={"error": "apply_not_supported"})
    _require_advanced_mode(advanced_requested)

    source_bytes = await _read_upload(file)
    upload_name = Path(file.filename or "upload.csv").name
    logger.info(
        "Repair request: filename=%s bytes=%d advanced=%s",
        upload_name,
        len(source_bytes),
        advanced_requested,
    )

    try:
        fixes, transaction, receipt = await _run_with_timeout(
            "repair",
            lambda: _run_repair_pipeline(
                upload_name=upload_name,
                source_bytes=source_bytes,
                allow_llm=advanced_requested,
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Repair endpoint failed")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "repair_failed",
                "message": "The repair pipeline could not complete safely.",
            },
        ) from exc

    return _fixes_to_response(fixes, transaction, receipt=receipt, source_name=upload_name)
