"""Unit tests for GeminiProvider — client construction, retries, JSON parsing."""

import os
from unittest.mock import MagicMock, patch

import pytest

from td_agent.providers.gemini_provider import DEFAULT_MODEL, GeminiProvider

_SCHEMA = {"type": "object", "properties": {}}


def _make_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


class TestGeminiProvider:

    @patch("td_agent.providers.gemini_provider.genai.Client")
    def test_successful_analysis(self, mock_client_cls):
        mock_client_cls.return_value = MagicMock()
        provider = GeminiProvider(api_key="test-key")
        provider._client.models.generate_content.return_value = _make_response(
            '{"issues": [], "overall_assessment": "OK", "files_analyzed": 1}'
        )

        result = provider.analyze("some prompt", _SCHEMA)

        assert result == {"issues": [], "overall_assessment": "OK", "files_analyzed": 1}
        assert provider.model == DEFAULT_MODEL

    @patch("td_agent.providers.gemini_provider.genai.Client")
    def test_strips_markdown_fences(self, mock_client_cls):
        mock_client_cls.return_value = MagicMock()
        provider = GeminiProvider(api_key="test-key")
        provider._client.models.generate_content.return_value = _make_response(
            '```json\n{"issues": [], "overall_assessment": "OK", "files_analyzed": 1}\n```'
        )

        result = provider.analyze("prompt", _SCHEMA)

        assert result["overall_assessment"] == "OK"

    @patch("td_agent.providers.gemini_provider.time.sleep", return_value=None)
    @patch("td_agent.providers.gemini_provider.genai.Client")
    def test_retries_on_503_then_succeeds(self, mock_client_cls, mock_sleep):
        mock_client_cls.return_value = MagicMock()
        provider = GeminiProvider(api_key="test-key")
        provider._client.models.generate_content.side_effect = [
            Exception("503 UNAVAILABLE"),
            _make_response('{"issues": [], "overall_assessment": "OK", "files_analyzed": 1}'),
        ]

        result = provider.analyze("prompt", _SCHEMA)

        assert result["overall_assessment"] == "OK"
        assert provider._client.models.generate_content.call_count == 2
        mock_sleep.assert_called_once()

    @patch("td_agent.providers.gemini_provider.genai.Client")
    def test_non_retryable_error_raises_immediately(self, mock_client_cls):
        mock_client_cls.return_value = MagicMock()
        provider = GeminiProvider(api_key="test-key")
        provider._client.models.generate_content.side_effect = Exception("invalid request")

        with pytest.raises(Exception, match="invalid request"):
            provider.analyze("prompt", _SCHEMA)

    @patch("td_agent.providers.gemini_provider.genai.Client")
    def test_empty_response_raises_value_error(self, mock_client_cls):
        mock_client_cls.return_value = MagicMock()
        provider = GeminiProvider(api_key="test-key")
        provider._client.models.generate_content.return_value = _make_response("")

        with pytest.raises(ValueError, match="empty"):
            provider.analyze("prompt", _SCHEMA)

    @patch("td_agent.providers.gemini_provider.genai.Client")
    def test_missing_api_key_raises(self, mock_client_cls):
        original = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                GeminiProvider(api_key=None)
        finally:
            if original is not None:
                os.environ["GEMINI_API_KEY"] = original
        mock_client_cls.assert_not_called()

    @patch("td_agent.providers.gemini_provider.genai.Client")
    def test_custom_model_is_recorded(self, mock_client_cls):
        mock_client_cls.return_value = MagicMock()
        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-pro")
        assert provider.model == "gemini-2.5-pro"
