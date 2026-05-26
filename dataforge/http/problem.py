"""RFC 9457 problem details helpers for FastAPI surfaces."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class ProblemDetail(BaseModel):
    """RFC 9457 problem detail response with extension members."""

    type: str = Field(default="about:blank")
    title: str
    status: int
    detail: str
    instance: str | None = None

    model_config = ConfigDict(strict=True, extra="allow")


def problem_body(
    *,
    status: int,
    title: str,
    detail: str,
    type_: str = "about:blank",
    instance: str | None = None,
    **extensions: Any,
) -> dict[str, Any]:
    """Build a problem details JSON object."""
    body = ProblemDetail(
        type=type_,
        title=title,
        status=status,
        detail=detail,
        instance=instance,
        **extensions,
    )
    return body.model_dump(mode="json", exclude_none=True)


def problem_response(
    *,
    status: int,
    title: str,
    detail: str,
    type_: str = "about:blank",
    instance: str | None = None,
    headers: Mapping[str, str] | None = None,
    **extensions: Any,
) -> JSONResponse:
    """Return an RFC 9457 JSON response."""
    return JSONResponse(
        status_code=status,
        content=problem_body(
            status=status,
            title=title,
            detail=detail,
            type_=type_,
            instance=instance,
            **extensions,
        ),
        headers=headers,
        media_type="application/problem+json",
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Normalize FastAPI HTTPException values into problem details."""
    raw_detail = exc.detail
    extensions: dict[str, Any] = {}
    if isinstance(raw_detail, dict):
        error_code = str(raw_detail.get("error", "http_error"))
        message = str(raw_detail.get("message") or raw_detail.get("detail") or error_code)
        extensions.update(raw_detail)
    else:
        error_code = "http_error"
        message = str(raw_detail)

    request_id = getattr(request.state, "dataforge_request_id", None)
    if isinstance(request_id, str) and request_id and "request_id" not in extensions:
        extensions["request_id"] = request_id

    return problem_response(
        status=exc.status_code,
        type_=f"https://dataforge.local/problems/{error_code}",
        title=error_code.replace("_", " ").title(),
        detail=message,
        instance=str(request.url.path),
        headers=exc.headers,
        **extensions,
    )


async def problem_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Adapter with the broad exception signature Starlette expects."""
    if isinstance(exc, HTTPException):
        return await http_exception_handler(request, exc)
    raise exc
