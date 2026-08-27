"""Claude provider — wraps the Anthropic SDK, matching the LLMProvider contract."""

import logging
import os
import time
from typing import Optional

import anthropic

from .base import LLMProvider

logger = logging.getLogger(__name__)

# Pinned to the dated snapshot rather than the "claude-sonnet-4-5" alias, which
# the API no longer offers. Same model the comparison in Chapter 4 was run
# against, and pinning it keeps that comparison reproducible.
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

_TOOL_NAME = "submit_technical_debt_analysis"
_MAX_TOKENS = 8192


class ClaudeProvider(LLMProvider):
    """Claude backend — uses a forced tool call to get schema-conformant JSON."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        system_instruction: str = "",
    ) -> None:
        self.model = model
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Get a key at https://console.anthropic.com and add it to .env."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self._system_instruction = system_instruction

    def analyze(self, prompt: str, schema: dict) -> dict:
        """Send `prompt` to Claude and return the tool-call input as parsed JSON.

        The response schema is enforced via a forced tool call (input_schema =
        `schema`), which is the reliable way to get schema-conformant JSON out
        of Claude — no text parsing or markdown-fence stripping needed.

        Retries up to _MAX_RETRIES times on rate-limit/overload errors
        (429/529/503) with exponential backoff.
        """
        _MAX_RETRIES = 5
        _BACKOFF_BASE = 30  # seconds

        tool = {
            "name": _TOOL_NAME,
            "description": "Submit the structured technical debt analysis for the given code snapshot.",
            "input_schema": schema,
        }

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=_MAX_TOKENS,
                    system=self._system_instruction,
                    tools=[tool],
                    tool_choice={"type": "tool", "name": _TOOL_NAME},
                    messages=[{"role": "user", "content": prompt}],
                )
            except anthropic.APIStatusError as exc:
                is_retryable = exc.status_code in (429, 503, 529)
                if is_retryable and attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "Claude %s (attempt %d/%d) — retrying in %ds",
                        exc.status_code, attempt, _MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                    continue
                raise

            tool_use = next((b for b in response.content if b.type == "tool_use"), None)
            if tool_use is None:
                raise ValueError("Claude returned no tool_use block")
            return tool_use.input
