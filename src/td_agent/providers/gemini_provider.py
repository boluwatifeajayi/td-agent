"""Gemini provider — wraps google.genai, matching the LLMProvider contract."""

import json
import logging
import os
import time
from typing import List, Optional

from google import genai
from google.genai import types

from .base import LLMProvider, parse_json_response

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash-lite"


class _RateLimiter:
    """Sliding-window rate limiter sized for Gemini free tier (15 req/min).

    Uses 14 as the cap to stay safely inside the quota boundary.
    """

    def __init__(self, max_per_minute: int = 14) -> None:
        self._max = max_per_minute
        self._window: List[float] = []

    def wait_if_needed(self) -> None:
        now = time.monotonic()
        self._window = [t for t in self._window if now - t < 60.0]
        if len(self._window) >= self._max:
            sleep_for = 60.0 - (now - self._window[0]) + 0.5  # 0.5 s safety margin
            if sleep_for > 0:
                logger.info("Rate limit: sleeping %.1f s before next Gemini request", sleep_for)
                time.sleep(sleep_for)
        self._window.append(time.monotonic())


class GeminiProvider(LLMProvider):
    """Gemini backend — free-tier rate limited, retries on 503/UNAVAILABLE."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        system_instruction: str = "",
    ) -> None:
        self.model = model
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com and add it to .env."
            )
        self._client = genai.Client(api_key=key)
        self._generate_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
        )
        self._rate_limiter = _RateLimiter()

    def analyze(self, prompt: str, schema: dict) -> dict:
        """Send `prompt` to Gemini and return the parsed JSON response.

        Retries up to _MAX_RETRIES times on 503/UNAVAILABLE with exponential
        backoff, and once on JSON parse failure (LLM formatting artefact).
        """
        _MAX_RETRIES = 5
        _BACKOFF_BASE = 30  # seconds

        for attempt in range(1, _MAX_RETRIES + 1):
            self._rate_limiter.wait_if_needed()
            try:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=self._generate_config,
                )
            except Exception as exc:
                err = str(exc)
                is_503 = "503" in err or "UNAVAILABLE" in err
                if is_503 and attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "Gemini 503 (attempt %d/%d) — retrying in %ds",
                        attempt, _MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                    continue
                raise

            if not response.text:
                raise ValueError("Gemini returned an empty response")
            try:
                return parse_json_response(response.text)
            except json.JSONDecodeError:
                # Lite models occasionally produce minor formatting artefacts
                # even in JSON mode; one retry is usually enough.
                if attempt < _MAX_RETRIES:
                    logger.warning("JSON parse failed; retrying")
                    continue
                raise
