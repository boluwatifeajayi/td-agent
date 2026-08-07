"""LLM provider registry — get_provider(name) returns a configured LLMProvider."""

import os
from typing import Optional

from .base import LLMProvider

_PROVIDERS = frozenset({"gemini", "claude"})


def get_provider(
    name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    system_instruction: str = "",
) -> LLMProvider:
    """Instantiate the LLM provider selected by `name`, the AI_PROVIDER env
    var, or 'gemini' as the default (in that priority order).
    """
    resolved = (name or os.environ.get("AI_PROVIDER") or "gemini").lower()
    if resolved not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider '{resolved}'. Choose one of: {', '.join(sorted(_PROVIDERS))}"
        )

    if resolved == "claude":
        from .claude_provider import ClaudeProvider, DEFAULT_MODEL
        return ClaudeProvider(
            api_key=api_key, model=model or DEFAULT_MODEL, system_instruction=system_instruction,
        )

    from .gemini_provider import GeminiProvider, DEFAULT_MODEL
    return GeminiProvider(
        api_key=api_key, model=model or DEFAULT_MODEL, system_instruction=system_instruction,
    )


__all__ = ["get_provider", "LLMProvider"]
