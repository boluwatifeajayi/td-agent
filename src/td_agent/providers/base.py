"""Abstract LLM provider interface shared by all backends."""

import json
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Common interface each LLM backend implements so callers can treat
    providers interchangeably. `model` must reflect the exact model string
    that actually served the request, so callers can record it honestly.
    """

    model: str

    @abstractmethod
    def analyze(self, prompt: str, schema: dict) -> dict:
        """Send `prompt` to the LLM and return the parsed JSON response matching `schema`."""
        raise NotImplementedError


def parse_json_response(text: str) -> dict:
    """Parse JSON from model output, tolerating markdown code-fence wrappers."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        end = len(lines) - 1
        while end > 0 and lines[end].strip() in ("```", ""):
            end -= 1
        text = "\n".join(lines[1:end + 1])
    start = text.find("{")
    stop = text.rfind("}")
    if start != -1 and stop != -1 and stop > start:
        text = text[start:stop + 1]
    return json.loads(text)
