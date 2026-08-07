"""Unit tests for ClaudeProvider — mirrors test_gemini_provider.py.

All Anthropic SDK calls are mocked; no real API key or network access needed.
"""

import os
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from td_agent.providers.claude_provider import DEFAULT_MODEL, ClaudeProvider

_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {"type": "array"},
        "overall_assessment": {"type": "string"},
        "files_analyzed": {"type": "integer"},
    },
    "required": ["issues", "overall_assessment", "files_analyzed"],
}


def _make_tool_use_response(input_dict: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.input = input_dict
    resp = MagicMock()
    resp.content = [block]
    return resp


def _make_status_error(status_code: int) -> anthropic.APIStatusError:
    request = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    exc = anthropic.APIStatusError("boom", response=response, body=None)
    exc.status_code = status_code
    return exc


class TestClaudeProvider:

    @patch("td_agent.providers.claude_provider.anthropic.Anthropic")
    def test_successful_analysis(self, mock_anthropic_cls):
        mock_anthropic_cls.return_value = MagicMock()
        provider = ClaudeProvider(api_key="test-key")
        provider._client.messages.create.return_value = _make_tool_use_response(
            {"issues": [], "overall_assessment": "OK", "files_analyzed": 1}
        )

        result = provider.analyze("some prompt", _SCHEMA)

        assert result == {"issues": [], "overall_assessment": "OK", "files_analyzed": 1}
        assert provider.model == DEFAULT_MODEL

    @patch("td_agent.providers.claude_provider.anthropic.Anthropic")
    def test_schema_validation_uses_forced_tool_call(self, mock_anthropic_cls):
        """The schema is passed as the tool's input_schema and tool_choice is forced,
        which is how Claude is made to return schema-conformant JSON reliably."""
        mock_anthropic_cls.return_value = MagicMock()
        provider = ClaudeProvider(api_key="test-key")
        provider._client.messages.create.return_value = _make_tool_use_response(
            {"issues": [], "overall_assessment": "OK", "files_analyzed": 1}
        )

        provider.analyze("some prompt", _SCHEMA)

        _, kwargs = provider._client.messages.create.call_args
        assert kwargs["tools"][0]["input_schema"] == _SCHEMA
        assert kwargs["tool_choice"] == {"type": "tool", "name": kwargs["tools"][0]["name"]}
        assert kwargs["messages"] == [{"role": "user", "content": "some prompt"}]

    @patch("td_agent.providers.claude_provider.time.sleep", return_value=None)
    @patch("td_agent.providers.claude_provider.anthropic.Anthropic")
    def test_retries_on_overloaded_then_succeeds(self, mock_anthropic_cls, mock_sleep):
        mock_anthropic_cls.return_value = MagicMock()
        provider = ClaudeProvider(api_key="test-key")
        provider._client.messages.create.side_effect = [
            _make_status_error(529),
            _make_tool_use_response({"issues": [], "overall_assessment": "OK", "files_analyzed": 1}),
        ]

        result = provider.analyze("prompt", _SCHEMA)

        assert result["overall_assessment"] == "OK"
        assert provider._client.messages.create.call_count == 2
        mock_sleep.assert_called_once()

    @patch("td_agent.providers.claude_provider.anthropic.Anthropic")
    def test_non_retryable_error_raises_immediately(self, mock_anthropic_cls):
        mock_anthropic_cls.return_value = MagicMock()
        provider = ClaudeProvider(api_key="test-key")
        provider._client.messages.create.side_effect = _make_status_error(400)

        with pytest.raises(anthropic.APIStatusError):
            provider.analyze("prompt", _SCHEMA)
        provider._client.messages.create.assert_called_once()

    @patch("td_agent.providers.claude_provider.anthropic.Anthropic")
    def test_missing_tool_use_block_raises_value_error(self, mock_anthropic_cls):
        mock_anthropic_cls.return_value = MagicMock()
        provider = ClaudeProvider(api_key="test-key")
        text_block = MagicMock()
        text_block.type = "text"
        resp = MagicMock()
        resp.content = [text_block]
        provider._client.messages.create.return_value = resp

        with pytest.raises(ValueError, match="no tool_use"):
            provider.analyze("prompt", _SCHEMA)

    @patch("td_agent.providers.claude_provider.anthropic.Anthropic")
    def test_missing_api_key_raises(self, mock_anthropic_cls):
        original = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                ClaudeProvider(api_key=None)
        finally:
            if original is not None:
                os.environ["ANTHROPIC_API_KEY"] = original
        mock_anthropic_cls.assert_not_called()

    @patch("td_agent.providers.claude_provider.anthropic.Anthropic")
    def test_custom_model_is_recorded(self, mock_anthropic_cls):
        mock_anthropic_cls.return_value = MagicMock()
        provider = ClaudeProvider(api_key="test-key", model="claude-opus-4-6")
        assert provider.model == "claude-opus-4-6"
