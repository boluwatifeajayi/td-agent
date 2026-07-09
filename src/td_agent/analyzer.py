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

from pathlib import Path

from .git_utils import (
    CommitInfo,
    get_churn_data,
    get_file_sizes,
    get_recent_files,
    get_source_files,
    read_file_at_commit,
)

load_dotenv()

logger = logging.getLogger(__name__)

# --- Smart file selection -------------------------------------------------

_DEBT_PRONE_KEYWORDS = ("auth", "config", "payment", "security", "gateway", "token", "oauth")
_ENTRY_POINT_NAMES = frozenset({"main", "app", "server", "index", "application"})
_LOCK_FILES = frozenset({"package-lock.json", "poetry.lock", "pipfile.lock"})
_BUILD_DIRS = frozenset({"target", "dist", "build", ".gradle"})


def _is_excluded_file(path: str) -> bool:
    """Generated files, lock files, and build artifacts — never worth analysing."""
    name = Path(path).name.lower()
    if name in _LOCK_FILES:
        return True
    if ".generated." in name or name.endswith("_pb2.py") or name.endswith(".min.js"):
        return True
    return any(part.lower() in _BUILD_DIRS for part in Path(path).parts[:-1])


_CATEGORIES = [
    "code_smell", "architectural", "maintainability",
    "security", "performance", "duplication",
    "complexity", "documentation", "testing", "dependency",
]
_SEVERITIES = ["low", "medium", "high", "critical"]
_CONFIDENCES = ["high", "medium", "low"]

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
                    "confidence":          {"type": "string", "enum": _CONFIDENCES},
                    "remediation_minutes": {"type": "integer"},
                    "description":         {"type": "string"},
                    "location":            {"type": "string"},
                    "suggestion":          {"type": "string"},
                    "why_debt":            {"type": "string"},
                },
                "required": [
                    "category", "severity", "confidence", "remediation_minutes",
                    "description", "location", "suggestion", "why_debt",
                ],
            },
        },
        "summary":             {"type": "string"},
        "overall_assessment":  {"type": "string"},
        "files_analyzed":      {"type": "integer"},
    },
    "required": ["issues", "summary", "overall_assessment", "files_analyzed"],
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
    "\n\n"
    "For each issue's confidence field, judge how certain you are based on the clarity of "
    "evidence visible in the code: use 'high' for clear-cut, mechanically verifiable issues "
    "(duplicated blocks, missing null checks, obvious hardcoded secrets), 'medium' when the "
    "issue is likely but depends on usage patterns you can't fully see, and 'low' for "
    "judgment calls about architecture or design intent made without full repository context. "
    "\n\n"
    "For each issue's why_debt field, write 1-2 sentences explaining why this specifically "
    "constitutes technical debt and the concrete consequence if left unaddressed — not a "
    "restatement of the description, but the downstream cost. Example: 'Authentication logic "
    "appears in 7 services. Password policy changes require editing multiple locations.' "
    "\n\n"
    "For the top-level summary field, write 2-4 sentences describing the overall debt picture "
    "across the whole codebase: which category of debt dominates, where it is concentrated, "
    "and the single biggest risk if nothing is fixed. Focus on patterns across files, not a "
    "list of individual issues. Repeat the same content in overall_assessment for "
    "backward compatibility."
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
    confidence: str = "medium"
    why_debt: str = ""
    is_cross_service_pattern: bool = False


@dataclass
class CommitAnalysisResult:
    commit: CommitInfo
    issues: List[TechnicalDebtIssue]
    ai_debt_score: int
    files_analyzed: int
    overall_assessment: str
    summary: str = ""
    model: str = ""
    files_skipped: int = 0
    duplicates_removed: int = 0
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
        files, files_skipped = self._collect_files(repo_path, commit.hash)
        if not files:
            return CommitAnalysisResult(
                commit=commit,
                issues=[],
                ai_debt_score=0,
                files_analyzed=0,
                overall_assessment="No source files found for analysis.",
                summary="No source files found for analysis.",
                model=self.model,
            )

        logger.debug(
            "Sending %d files (~%d chars) to Gemini for %s",
            len(files), sum(len(c) for _, c in files), commit.short_hash,
        )
        try:
            raw = self._call_llm(files, commit)
            issues = [TechnicalDebtIssue(**issue) for issue in raw.get("issues", [])]
            issues, duplicates_removed = self._dedupe_issues(issues)
            return CommitAnalysisResult(
                commit=commit,
                issues=issues,
                ai_debt_score=sum(i.remediation_minutes for i in issues),
                files_analyzed=raw.get("files_analyzed", len(files)),
                overall_assessment=raw.get("overall_assessment", ""),
                summary=raw.get("summary", raw.get("overall_assessment", "")),
                model=self.model,
                files_skipped=files_skipped,
                duplicates_removed=duplicates_removed,
            )
        except Exception as exc:
            logger.error("Analysis failed for %s: %s", commit.short_hash, exc)
            return CommitAnalysisResult(
                commit=commit,
                issues=[],
                ai_debt_score=0,
                files_analyzed=len(files),
                overall_assessment="",
                model=self.model,
                files_skipped=files_skipped,
                analysis_error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prioritize_paths(self, repo_path: str, commit_hash: str, paths: List[str]) -> List[str]:
        """Order candidate paths so the most debt-relevant files are analysed first.

        Priority tiers (highest first):
          1. High-churn files (from git history)
          2. Debt-prone names: auth, config, payment, security, gateway, token, oauth
          3. Recently modified files
          4. Service entry points (main, app, server, index, application)
          5. Remaining files by blob size, descending

        Each git-metadata lookup degrades gracefully — if churn/recency/size
        data is unavailable, the corresponding tier is simply skipped.
        """
        path_set = set(paths)
        ordered: List[str] = []
        seen: set = set()

        def add(candidates: List[str]) -> None:
            for p in candidates:
                if p in path_set and p not in seen:
                    seen.add(p)
                    ordered.append(p)

        try:
            churn = get_churn_data(repo_path)
            add([f["path"] for f in churn["top_churned_files"]])
        except Exception as exc:
            logger.debug("Churn data unavailable for %s: %s", repo_path, exc)

        add([p for p in paths if any(k in p.lower() for k in _DEBT_PRONE_KEYWORDS)])

        try:
            add(get_recent_files(repo_path, commit_hash))
        except Exception as exc:
            logger.debug("Recent-file data unavailable for %s: %s", repo_path, exc)

        add([p for p in paths if Path(p).stem.lower() in _ENTRY_POINT_NAMES])

        sizes: dict = {}
        try:
            sizes = get_file_sizes(repo_path, commit_hash)
        except Exception as exc:
            logger.debug("File sizes unavailable for %s: %s", repo_path, exc)
        remaining = [p for p in paths if p not in seen]
        remaining.sort(key=lambda p: -sizes.get(p, 0))
        add(remaining)

        return ordered

    def _collect_files(self, repo_path: str, commit_hash: str) -> Tuple[List[Tuple[str, str]], int]:
        """Gather readable source files up to MAX_FILES / MAX_CHARS limits.

        Returns (collected files, count of candidate source files skipped
        because of the caps or unreadability).
        """
        paths = [p for p in get_source_files(repo_path, commit_hash) if not _is_excluded_file(p)]
        paths = self._prioritize_paths(repo_path, commit_hash, paths)
        collected: List[Tuple[str, str]] = []
        total_chars = 0
        for i, path in enumerate(paths):
            if len(collected) >= self.MAX_FILES:
                return collected, len(paths) - i
            content = read_file_at_commit(repo_path, commit_hash, path)
            if content is None:
                continue
            if total_chars + len(content) > self.MAX_CHARS:
                return collected, len(paths) - i
            collected.append((path, content))
            total_chars += len(content)
        return collected, len(paths) - len(collected)

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
    def _dedupe_issues(
        issues: List[TechnicalDebtIssue],
    ) -> Tuple[List[TechnicalDebtIssue], int]:
        """Deduplicate issues and flag cross-service patterns.

        True duplicates (identical location AND description) are dropped — these
        are the same finding emitted twice by the LLM for the same file.

        Cross-service patterns (same description appearing at 2+ distinct locations)
        are kept in full and marked with is_cross_service_pattern = True, because
        they represent the same anti-pattern replicated across multiple services —
        genuine architectural debt that must not be collapsed to a single count.
        """
        seen_exact: set = set()
        deduped: List[TechnicalDebtIssue] = []
        for issue in issues:
            key = (issue.location, issue.description)
            if key not in seen_exact:
                seen_exact.add(key)
                deduped.append(issue)

        duplicates_removed = len(issues) - len(deduped)

        # Descriptions appearing at 2+ distinct locations are cross-service patterns
        desc_locs: Dict[str, set] = {}
        for issue in deduped:
            desc_locs.setdefault(issue.description, set()).add(issue.location)
        cross_service_descs = {d for d, locs in desc_locs.items() if len(locs) >= 2}

        for issue in deduped:
            if issue.description in cross_service_descs:
                issue.is_cross_service_pattern = True

        return deduped, duplicates_removed

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
