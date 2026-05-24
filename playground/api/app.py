"""Stateless FastAPI backend for the hosted DataForge playground.

The hosted playground is intentionally split across two free-tier hosts:

- Cloudflare Workers Static Assets serves the static frontend.
- Hugging Face Spaces serves this API-only backend.

All uploaded data is processed in memory or under a per-request temporary
directory and is discarded before the request completes.
"""

import io
import logging
import os
import tempfile
import time
from collections import defaultdict
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

import pandas as pd
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
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

MAX_UPLOAD_BYTES = 1_048_576
MAX_MULTIPART_OVERHEAD_BYTES = 16_384
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
SLOWAPI_CONFIG = Path(__file__).resolve().parent / "slowapi.env"
ALLOWED_SAMPLES = {"hospital_10rows", "flights_10rows", "beers_10rows"}


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
                return JSONResponse(status_code=400, content={"error": "invalid_content_length"})
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
    allow_origins=_build_cors_origins(),
    allow_origin_regex=_build_cors_origin_regex(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)
app.state.limiter = limiter
app.add_exception_handler(HTTPException, problem_exception_handler)
configure_fastapi_observability(app, service_name="dataforge-playground-api")


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
    )


async def _read_upload(file: UploadFile) -> bytes:
    """Read an uploaded file with a defensive hard cap."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": "file_too_large", "max_bytes": MAX_UPLOAD_BYTES},
        )
    return data


def _csv_to_df(data: bytes) -> pd.DataFrame:
    """Parse CSV bytes into a string-preserving DataFrame."""
    return pd.read_csv(
        io.BytesIO(data),
        dtype=str,
        keep_default_na=False,
        na_filter=False,
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
) -> tuple[list[VerifiedFix], RepairTransaction]:
    """Run the real dry-run repair pipeline inside a temporary workspace."""
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
        return result.fixes, result.transaction


@app.get("/")
async def root() -> dict[str, Any]:
    """Return service metadata for humans and uptime probes."""
    return {
        "service": "DataForge Playground API",
        "status": "ok",
        "docs_url": "/api/docs",
        "frontend_hosting": "cloudflare_static_assets",
    }


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Return backend readiness plus UI-facing capability metadata."""
    return {
        "status": "ok",
        "advanced_available": _advanced_available(),
        "max_upload_bytes": MAX_UPLOAD_BYTES,
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
        df = _csv_to_df(source_bytes)
        issues = run_all_detectors(df, schema=None)
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

    return _issues_to_response(issues, df, advanced_requested=advanced_requested)


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
        fixes, transaction = _run_repair_pipeline(
            upload_name=upload_name,
            source_bytes=source_bytes,
            allow_llm=advanced_requested,
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

    return _fixes_to_response(fixes, transaction, source_name=upload_name)
