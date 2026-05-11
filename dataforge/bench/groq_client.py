"""Minimal Groq client for benchmark-only LLM baselines."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import cast

import httpx


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Return whether an exception is a Groq 429 response."""
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _retry_after_s(exc: httpx.HTTPStatusError, *, fallback_s: float) -> float:
    """Return Groq's retry-after delay when present."""
    raw_retry_after = exc.response.headers.get("retry-after")
    if raw_retry_after is None:
        return fallback_s
    try:
        return max(float(raw_retry_after), fallback_s)
    except ValueError:
        return fallback_s


@dataclass(frozen=True, kw_only=True)
class GroqCompletion:
    """Completion payload plus conservative usage accounting."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    warnings: tuple[str, ...]


class GroqBenchClient:
    """Sequential Groq client with fixed 429 retry and spacing."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        min_interval_s: float = 2.0,
        max_tokens: int = 512,
        max_retries: int = 5,
        timeout_s: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._min_interval_s = min_interval_s
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._timeout_s = timeout_s
        self._last_success_at: float | None = None
        self._client = httpx.Client(
            timeout=self._timeout_s,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    @property
    def model(self) -> str:
        """Return the configured Groq model name."""
        return self._model

    def _respect_spacing(self) -> None:
        """Sleep long enough to keep requests sequential with a fixed gap."""
        if self._last_success_at is None:
            return
        elapsed = time.monotonic() - self._last_success_at
        remaining = self._min_interval_s - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _post(self, messages: list[dict[str, str]]) -> dict[str, object]:
        """Issue the underlying Groq chat-completions request."""
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": self._max_tokens,
        }
        last_rate_limit_error: httpx.HTTPStatusError | None = None
        for attempt in range(self._max_retries):
            response: httpx.Response | None = None
            try:
                response = self._client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if not _is_rate_limit_error(exc) or attempt == self._max_retries - 1:
                    raise
                last_rate_limit_error = exc
                retry_s = _retry_after_s(exc, fallback_s=2.0 * (attempt + 1))
                logging.getLogger("dataforge.bench.groq_client").warning(
                    "groq_rate_limit attempt=%d retry_after_s=%.2f", attempt + 1, retry_s
                )
                time.sleep(retry_s)
                continue
            except httpx.TimeoutException as exc:
                raise TimeoutError(
                    f"Groq request timed out after {self._timeout_s:.1f} seconds."
                ) from exc
            return dict(response.json())
        if last_rate_limit_error is not None:
            raise last_rate_limit_error
        raise RuntimeError("Groq request failed without a response.")

    def complete(self, messages: list[dict[str, str]]) -> GroqCompletion:
        """Send one benchmark completion request to Groq."""
        self._respect_spacing()
        payload = self._post(messages)
        self._last_success_at = time.monotonic()

        warnings: list[str] = []
        usage = payload.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0)) if isinstance(usage, dict) else 0
        completion_tokens = int(usage.get("completion_tokens", 0)) if isinstance(usage, dict) else 0
        if not usage:
            warnings.append("missing_usage_payload")
            logging.getLogger("dataforge.bench.groq_client").warning("groq_missing_usage_payload")

        try:
            choices = cast(list[dict[str, object]], payload["choices"])
            message = cast(dict[str, object], choices[0]["message"])
            content = str(message["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Unexpected Groq response payload: {json.dumps(payload)}") from exc
        return GroqCompletion(
            text=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            warnings=tuple(warnings),
        )
