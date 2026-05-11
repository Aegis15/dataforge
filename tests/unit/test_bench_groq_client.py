"""Unit tests for the benchmark-local Groq client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from dataforge.bench.groq_client import GroqBenchClient


def _mock_response(payload: dict[str, object]) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


class TestGroqBenchClient:
    """Groq benchmark client behavior with mocked HTTP responses."""

    def test_complete_parses_content_and_usage(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = _mock_response(
            {
                "choices": [{"message": {"content": '{"repairs": []}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            }
        )

        with patch("dataforge.bench.groq_client.httpx.Client", return_value=mock_client):
            completion = GroqBenchClient(api_key="test").complete(
                [{"role": "user", "content": "hi"}]
            )

        assert completion.text == '{"repairs": []}'
        assert completion.prompt_tokens == 12
        assert completion.completion_tokens == 5
        assert completion.warnings == ()
        assert mock_client.post.call_args.kwargs["json"]["max_tokens"] == 512

    def test_complete_warns_when_usage_is_missing(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = _mock_response(
            {"choices": [{"message": {"content": '{"repairs": []}'}}]}
        )

        with patch("dataforge.bench.groq_client.httpx.Client", return_value=mock_client):
            completion = GroqBenchClient(api_key="test").complete(
                [{"role": "user", "content": "hi"}]
            )

        assert completion.prompt_tokens == 0
        assert completion.completion_tokens == 0
        assert completion.warnings == ("missing_usage_payload",)

    def test_complete_honors_retry_after_on_rate_limit(self) -> None:
        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        rate_limited_response = httpx.Response(
            429,
            headers={"retry-after": "7"},
            request=request,
        )
        rate_limited_error = httpx.HTTPStatusError(
            "rate limited",
            request=request,
            response=rate_limited_response,
        )
        mock_response = _mock_response(
            {
                "choices": [{"message": {"content": '{"repairs": []}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            }
        )
        mock_response.raise_for_status.side_effect = [rate_limited_error, None]
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with (
            patch("dataforge.bench.groq_client.httpx.Client", return_value=mock_client),
            patch("dataforge.bench.groq_client.time.sleep") as sleep,
        ):
            completion = GroqBenchClient(api_key="test").complete(
                [{"role": "user", "content": "hi"}]
            )

        assert completion.text == '{"repairs": []}'
        sleep.assert_called_once_with(7.0)

    def test_complete_raises_on_unexpected_payload(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = _mock_response({"choices": []})

        with (
            patch("dataforge.bench.groq_client.httpx.Client", return_value=mock_client),
            pytest.raises(ValueError, match="Unexpected Groq response payload"),
        ):
            GroqBenchClient(api_key="test").complete([{"role": "user", "content": "hi"}])

    def test_complete_raises_clear_timeout_error(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.side_effect = httpx.TimeoutException("slow")

        with (
            patch("dataforge.bench.groq_client.httpx.Client", return_value=mock_client),
            pytest.raises(TimeoutError, match="timed out after 3.0 seconds"),
        ):
            GroqBenchClient(api_key="test", timeout_s=3).complete(
                [{"role": "user", "content": "hi"}]
            )
