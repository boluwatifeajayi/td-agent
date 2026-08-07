"""Unit tests for the provider registry (get_provider selection logic)."""

import os
from unittest.mock import MagicMock, patch

import pytest

from td_agent.providers import get_provider


class TestGetProvider:

    @patch("td_agent.providers.gemini_provider.genai.Client")
    def test_defaults_to_gemini_when_unspecified(self, mock_client_cls):
        mock_client_cls.return_value = MagicMock()
        original = os.environ.pop("AI_PROVIDER", None)
        try:
            provider = get_provider(api_key="test-key")
            assert type(provider).__name__ == "GeminiProvider"
        finally:
            if original is not None:
                os.environ["AI_PROVIDER"] = original

    @patch("td_agent.providers.claude_provider.anthropic.Anthropic")
    def test_explicit_claude_selection(self, mock_anthropic_cls):
        mock_anthropic_cls.return_value = MagicMock()
        provider = get_provider("claude", api_key="test-key")
        assert type(provider).__name__ == "ClaudeProvider"

    @patch("td_agent.providers.claude_provider.anthropic.Anthropic")
    def test_ai_provider_env_var_selects_claude(self, mock_anthropic_cls):
        mock_anthropic_cls.return_value = MagicMock()
        os.environ["AI_PROVIDER"] = "claude"
        try:
            provider = get_provider(api_key="test-key")
            assert type(provider).__name__ == "ClaudeProvider"
        finally:
            del os.environ["AI_PROVIDER"]

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("chatgpt", api_key="test-key")

    @patch("td_agent.providers.claude_provider.anthropic.Anthropic")
    def test_explicit_argument_overrides_env_var(self, mock_anthropic_cls):
        mock_anthropic_cls.return_value = MagicMock()
        os.environ["AI_PROVIDER"] = "claude"
        try:
            with patch("td_agent.providers.gemini_provider.genai.Client") as mock_gemini_cls:
                mock_gemini_cls.return_value = MagicMock()
                provider = get_provider("gemini", api_key="test-key")
                assert type(provider).__name__ == "GeminiProvider"
        finally:
            del os.environ["AI_PROVIDER"]
