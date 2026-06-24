"""Core LLM analysis — sends code snapshots to Gemini and parses technical debt."""

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from google import genai
from google.genai import types
from dotenv import load_dotenv

from .git_utils import CommitInfo, get_source_files, read_file_at_commit

load_dotenv()

logger = logging.getLogger(__name__)

_CATEGORIES = [
    "code_smell", "architectural", "maintainability",
    "security", "performance", "duplication",
    "complexity", "documentation", "testing", "dependency",
]
_SEVERITIES = ["low", "medium", "high", "critical"]

# Schema included verbatim in the prompt — Gemini uses response_mime_type for JSON mode
# and the schema description steers the structure.
_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category":            {"type": "string", "enum": _CATEGORIES},
                    "severity":            {"type": "string", "enum": _SEVERITIES},
                    "remediation_minutes": {"type": "integer"},
                    "description":         {"type": "string"},
                    "location":            {"type": "string"},
                    "suggestion":          {"type": "string"},
                },
                "required": [
                    "category", "severity", "remediation_minutes",
                    "description", "location", "suggestion",
                ],
            },
        },
        "overall_assessment": {"type": "string"},
        "files_analyzed":     {"type": "integer"},
    },
    "required": ["issues", "overall_assessment", "files_analyzed"],
}

_SCHEMA_TEXT = json.dumps(_ANALYSIS_SCHEMA, indent=2)

_SYSTEM_PROMPT = (
    "You are an expert software engineer specialising in code quality and technical debt analysis. "
    "Analyse the provided source code snapshot and identify technical debt issues. "
    "\n\n"
    "For remediation_minutes, use realistic estimates: renaming a variable ≈ 5 min, "
    "fixing a missing null-check ≈ 15 min, extracting a class ≈ 60 min, "
    "untangling tight coupling ≈ 240 min, addressing a broken architecture ≈ 480+ min. "
    "\n\n"
    "The AI Technical Debt Score for a commit equals the sum of all remediation_minutes. "
    "This metric is designed to be directly comparable to SonarQube's SQALE index. "
    "Be thorough but realistic — focus on meaningful, actionable debt rather than trivial "
    "style preferences unless they are pervasive across the codebase."
)


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


@dataclass
class TechnicalDebtIssue:
    category: str
    severity: str
    remediation_minutes: int
    description: str
    location: str
    suggestion: str


@dataclass
class CommitAnalysisResult:
    commit: CommitInfo
    issues: List[TechnicalDebtIssue]
    ai_debt_score: int
    files_analyzed: int
    overall_assessment: str
    analysis_error: Optional[str] = None

    @property
    def category_breakdown(self) -> Dict[str, int]:
        """Total remediation minutes per category."""
        bd: Dict[str, int] = {}
        for issue in self.issues:
            bd[issue.category] = bd.get(issue.category, 0) + issue.remediation_minutes
        return bd

    @property
    def severity_breakdown(self) -> Dict[str, int]:
        """Issue count per severity level."""
        bd: Dict[str, int] = {}
        for issue in self.issues:
            bd[issue.severity] = bd.get(issue.severity, 0) + 1
        return bd


class TechnicalDebtAnalyzer:
    """Analyses git commits for technical debt using Gemini."""

    DEFAULT_MODEL = "gemini-2.5-flash-lite"
    MAX_FILES = 80
    MAX_CHARS = 400_000

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com and add it to .env."
            )
        self._client = genai.Client(api_key=key)
        self._generate_config = types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            response_mime_type="application/json",
        )
        self._rate_limiter = _RateLimiter()

    def analyze_commit(self, repo_path: str, commit: CommitInfo) -> CommitAnalysisResult:
        """Analyse a single commit. Always returns a result — errors are captured."""
        files = self._collect_files(repo_path, commit.hash)
        if not files:
            return CommitAnalysisResult(
                commit=commit,
                issues=[],
                ai_debt_score=0,
                files_analyzed=0,
                overall_assessment="No source files found for analysis.",
            )

        logger.debug(
            "Sending %d files (~%d chars) to Gemini for %s",
            len(files), sum(len(c) for _, c in files), commit.short_hash,
        )
        try:
            raw = self._call_llm(files, commit)
            issues = [TechnicalDebtIssue(**issue) for issue in raw.get("issues", [])]
            return CommitAnalysisResult(
                commit=commit,
                issues=issues,
                ai_debt_score=sum(i.remediation_minutes for i in issues),
                files_analyzed=raw.get("files_analyzed", len(files)),
                overall_assessment=raw.get("overall_assessment", ""),
            )
        except Exception as exc:
            logger.error("Analysis failed for %s: %s", commit.short_hash, exc)
            return CommitAnalysisResult(
                commit=commit,
                issues=[],
                ai_debt_score=0,
                files_analyzed=len(files),
                overall_assessment="",
                analysis_error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_files(self, repo_path: str, commit_hash: str) -> List[Tuple[str, str]]:
        """Gather readable source files up to MAX_FILES / MAX_CHARS limits."""
        paths = get_source_files(repo_path, commit_hash)
        collected: List[Tuple[str, str]] = []
        total_chars = 0
        for path in paths:
            if len(collected) >= self.MAX_FILES:
                break
            content = read_file_at_commit(repo_path, commit_hash, path)
            if content is None:
                continue
            if total_chars + len(content) > self.MAX_CHARS:
                break
            collected.append((path, content))
            total_chars += len(content)
        return collected

    def _build_prompt(self, files: List[Tuple[str, str]], commit: CommitInfo) -> str:
        header = (
            f"Commit: {commit.short_hash}  Date: {commit.date.strftime('%Y-%m-%d')}\n"
            f"Message: {commit.message}\n"
            f"Files below ({len(files)} source files):\n"
        )
        parts = [header]
        for path, content in files:
            parts.append(f"\n=== {path} ===\n{content}")
        parts.append(f"\n\nRespond with a JSON object matching this exact schema:\n{_SCHEMA_TEXT}")
        return "".join(parts)

    def _call_llm(self, files: List[Tuple[str, str]], commit: CommitInfo) -> dict:
        """Send files to Gemini and return the parsed JSON response."""
        self._rate_limiter.wait_if_needed()
        prompt = self._build_prompt(files, commit)
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self._generate_config,
        )
        if not response.text:
            raise ValueError("Gemini returned an empty response")
        try:
            return self._parse_json(response.text)
        except json.JSONDecodeError:
            # Lite models occasionally produce minor formatting artefacts even in JSON
            # mode; one retry is usually enough to get a clean response.
            logger.warning("JSON parse failed for %s; retrying once", commit.short_hash)
            self._rate_limiter.wait_if_needed()
            response2 = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._generate_config,
            )
            return self._parse_json(response2.text)

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Parse JSON from model output, tolerating markdown code-fence wrappers."""
        text = text.strip()
        # Strip ```json ... ``` or ``` ... ``` if the model wrapped its output
        if text.startswith("```"):
            lines = text.splitlines()
            end = len(lines) - 1
            while end > 0 and lines[end].strip() in ("```", ""):
                end -= 1
            text = "\n".join(lines[1:end + 1])
        # Extract outermost {...} in case surrounding noise remains
        start = text.find("{")
        stop = text.rfind("}")
        if start != -1 and stop != -1 and stop > start:
            text = text[start:stop + 1]
        return json.loads(text)
