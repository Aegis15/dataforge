"""Unit tests for the benchmark-local Groq client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from dataforge.bench.groq_client import (
    CerebrasBenchClient,
    GeminiBenchClient,
    GroqBenchClient,
    ProviderRateLimitError,
    ProviderRequestError,
    _is_rate_limit_error,
)


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
        assert mock_client.post.call_args.args[0] == (
            "https://api.groq.com/openai/v1/chat/completions"
        )

    def test_cerebras_client_uses_cerebras_endpoint_and_model(self) -> None:
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
            completion = CerebrasBenchClient(api_key="test").complete(
                [{"role": "user", "content": "hi"}]
            )

        assert completion.text == '{"repairs": []}'
        assert mock_client.post.call_args.args[0] == ("https://api.cerebras.ai/v1/chat/completions")
        assert mock_client.post.call_args.kwargs["json"]["model"] == (
            "qwen-3-235b-a22b-instruct-2507"
        )

    def test_gemini_client_uses_generate_content_payload(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = _mock_response(
            {
                "candidates": [{"content": {"parts": [{"text": '{"repairs": []}'}]}}],
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 5},
            }
        )

        with patch("dataforge.bench.groq_client.httpx.Client", return_value=mock_client):
            completion = GeminiBenchClient(api_key="test").complete(
                [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "{}"},
                ]
            )

        assert completion.text == '{"repairs": []}'
        assert completion.prompt_tokens == 12
        assert completion.completion_tokens == 5
        assert mock_client.post.call_args.args[0] == (
            "https://generativelanguage.googleapis.com/v1beta/"
            "models/gemini-3.1-pro-preview:generateContent"
        )
        request_json = mock_client.post.call_args.kwargs["json"]
        assert request_json["systemInstruction"]["parts"][0]["text"] == "sys"
        assert request_json["contents"][1]["role"] == "model"

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

    def test_complete_raises_when_retry_after_exceeds_cap(self) -> None:
        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        rate_limited_response = httpx.Response(
            429,
            headers={"retry-after": "3356"},
            text='{"error":{"message":"wait"}}',
            request=request,
        )
        rate_limited_error = httpx.HTTPStatusError(
            "rate limited",
            request=request,
            response=rate_limited_response,
        )
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = rate_limited_error
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with (
            patch("dataforge.bench.groq_client.httpx.Client", return_value=mock_client),
            patch("dataforge.bench.groq_client.time.sleep") as sleep,
            pytest.raises(ProviderRateLimitError, match="exceeds cap"),
        ):
            GroqBenchClient(api_key="test", max_retry_after_s=120).complete(
                [{"role": "user", "content": "hi"}]
            )

        sleep.assert_not_called()

    def test_complete_raises_on_unexpected_payload(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = _mock_response({"choices": []})

        with (
            patch("dataforge.bench.groq_client.httpx.Client", return_value=mock_client),
            pytest.raises(ValueError, match="Unexpected groq response payload"),
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

    def test_complete_raises_provider_request_error_with_response_body(self) -> None:
        request = httpx.Request("POST", "https://api.cerebras.ai/v1/chat/completions")
        response = httpx.Response(
            400,
            text='{"message":"context length exceeded"}',
            request=request,
        )
        bad_request = httpx.HTTPStatusError("bad request", request=request, response=response)
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = bad_request
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with (
            patch("dataforge.bench.groq_client.httpx.Client", return_value=mock_client),
            pytest.raises(ProviderRequestError, match="context length exceeded"),
        ):
            CerebrasBenchClient(api_key="test", model="llama3.1-8b").complete(
                [{"role": "user", "content": "large prompt"}]
            )

    def test_rate_limit_helper_and_spacing_sleep(self) -> None:
        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        rate_limited = httpx.HTTPStatusError(
            "rate limited",
            request=request,
            response=httpx.Response(429, request=request),
        )
        unavailable = httpx.HTTPStatusError(
            "unavailable",
            request=request,
            response=httpx.Response(503, request=request),
        )

        with patch("dataforge.bench.groq_client.httpx.Client"):
            client = GroqBenchClient(api_key="test", min_interval_s=5)
        client._last_success_at = 10.0

        with (
            patch("dataforge.bench.groq_client.time.monotonic", return_value=12.0),
            patch("dataforge.bench.groq_client.time.sleep") as sleep,
        ):
            client._respect_spacing()

        assert _is_rate_limit_error(rate_limited) is True
        assert _is_rate_limit_error(unavailable) is False
        sleep.assert_called_once_with(3.0)

    def test_retryable_503_final_attempt_raises_provider_error(self) -> None:
        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        response = httpx.Response(503, text="temporarily down", request=request)
        unavailable = httpx.HTTPStatusError("unavailable", request=request, response=response)
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = unavailable
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        with (
            patch("dataforge.bench.groq_client.httpx.Client", return_value=mock_client),
            patch("dataforge.bench.groq_client.time.sleep") as sleep,
            pytest.raises(ProviderRequestError, match="temporarily down"),
        ):
            GroqBenchClient(api_key="test", max_retries=1).complete(
                [{"role": "user", "content": "hi"}]
            )

        sleep.assert_not_called()

    def test_invalid_retry_after_uses_fallback_delay(self) -> None:
        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        rate_limited_response = httpx.Response(
            429,
            headers={"retry-after": "not-a-number"},
            request=request,
        )
        rate_limited_error = httpx.HTTPStatusError(
            "rate limited",
            request=request,
            response=rate_limited_response,
        )
        success = _mock_response(
            {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
        )
        rate_limit_then_success = MagicMock()
        rate_limit_then_success.raise_for_status.side_effect = [rate_limited_error, None]
        mock_client = MagicMock()
        mock_client.post.side_effect = [rate_limit_then_success, success]

        with (
            patch("dataforge.bench.groq_client.httpx.Client", return_value=mock_client),
            patch("dataforge.bench.groq_client.time.sleep") as sleep,
        ):
            completion = GroqBenchClient(api_key="test").complete(
                [{"role": "user", "content": "hi"}]
            )

        assert completion.text == "ok"
        sleep.assert_called_once_with(2.0)

    def test_gemini_missing_usage_and_unexpected_payload(self) -> None:
        missing_usage_client = MagicMock()
        missing_usage_client.post.return_value = _mock_response(
            {"candidates": [{"content": {"parts": [{"text": "ok"}, {"text": "!"}]}}]}
        )
        bad_payload_client = MagicMock()
        bad_payload_client.post.return_value = _mock_response({"candidates": []})

        with patch("dataforge.bench.groq_client.httpx.Client", return_value=missing_usage_client):
            completion = GeminiBenchClient(api_key="test").complete(
                [{"role": "user", "content": "hi"}]
            )

        assert completion.text == "ok!"
        assert completion.warnings == ("missing_usage_payload",)

        with (
            patch("dataforge.bench.groq_client.httpx.Client", return_value=bad_payload_client),
            pytest.raises(ValueError, match="Unexpected gemini response payload"),
        ):
            GeminiBenchClient(api_key="test").complete([{"role": "user", "content": "hi"}])
