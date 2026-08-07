"""Unit tests for TechnicalDebtAnalyzer with a mocked LLM provider.

Provider-specific behaviour (client construction, rate limiting, retries,
raw-response parsing) is covered separately in test_gemini_provider.py and
test_claude_provider.py — these tests only exercise analyzer.py's own logic
(file selection, prioritisation, dedup, error capture) against the
LLMProvider interface, so they stay valid regardless of which provider is
plugged in.
"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from td_agent.analyzer import CommitAnalysisResult, TechnicalDebtAnalyzer, TechnicalDebtIssue
from td_agent.git_utils import CommitInfo


def _fake_commit(hash_: str = "abcd1234efgh5678") -> CommitInfo:
    return CommitInfo(
        hash=hash_,
        short_hash=hash_[:8],
        date=datetime(2024, 6, 1),
        message="feat: add payment service",
        author="dev@example.com",
    )


def _fake_llm_response(issues: list, assessment: str = "OK", files: int = 5) -> dict:
    return {"issues": issues, "overall_assessment": assessment, "files_analyzed": files}


def _make_analyzer(mock_get_provider, api_key: str = "test-key") -> TechnicalDebtAnalyzer:
    """Construct an analyzer with a mocked LLMProvider (analyze() returns parsed dicts)."""
    mock_provider = MagicMock()
    mock_provider.model = "gemini-2.5-flash-lite"
    mock_get_provider.return_value = mock_provider
    return TechnicalDebtAnalyzer(api_key=api_key)


class TestTechnicalDebtAnalyzer:

    @patch("td_agent.analyzer.get_provider")
    @patch("td_agent.analyzer.get_source_files", return_value=["src/Foo.java", "src/Bar.java"])
    @patch("td_agent.analyzer.read_file_at_commit", return_value="public class Foo {}")
    def test_successful_analysis(self, mock_read, mock_files, mock_get_provider):
        analyzer = _make_analyzer(mock_get_provider)
        llm_data = _fake_llm_response(
            issues=[
                {
                    "category": "code_smell",
                    "severity": "medium",
                    "remediation_minutes": 30,
                    "description": "Missing Javadoc on public class",
                    "location": "src/Foo.java",
                    "suggestion": "Add class-level Javadoc",
                },
                {
                    "category": "complexity",
                    "severity": "high",
                    "remediation_minutes": 120,
                    "description": "God class with 50 methods",
                    "location": "src/Bar.java",
                    "suggestion": "Extract sub-responsibilities into separate classes",
                },
            ],
            assessment="Moderate debt, manageable.",
            files=2,
        )
        analyzer._provider.analyze.return_value = llm_data

        result = analyzer.analyze_commit("/fake/repo", _fake_commit())

        assert isinstance(result, CommitAnalysisResult)
        assert result.ai_debt_score == 150
        assert len(result.issues) == 2
        assert result.analysis_error is None
        assert result.overall_assessment == "Moderate debt, manageable."
        assert result.model == "gemini-2.5-flash-lite"

    @patch("td_agent.analyzer.get_provider")
    @patch("td_agent.analyzer.get_source_files", return_value=["src/SleuthAnnotationUtils.java"])
    @patch("td_agent.analyzer.read_file_at_commit", return_value="public class SleuthAnnotationUtils {}")
    def test_duplicate_issues_are_deduplicated(self, mock_read, mock_files, mock_get_provider):
        analyzer = _make_analyzer(mock_get_provider)
        base_issue = {
            "category": "code_smell",
            "severity": "medium",
            "confidence": "high",
            "remediation_minutes": 20,
            "description": "Method uses reflection unsafely",
            "location": "src/ServiceA.java:42",
            "suggestion": "Avoid reflection",
            "why_debt": "Reflection breaks at runtime with no compile-time safety net.",
        }
        # True duplicate: identical location + description — must be dropped
        true_dup = {**base_issue}
        # Cross-service instance: same description, different location — must be KEPT
        cross_service_instance = {**base_issue, "location": "src/ServiceB.java:7"}
        # Unrelated unique issue
        unique_issue = {**base_issue, "location": "src/Other.java:99", "description": "Different finding"}

        llm_data = _fake_llm_response(
            issues=[true_dup] * 5 + [cross_service_instance, unique_issue],
            files=1,
        )
        analyzer._provider.analyze.return_value = llm_data

        result = analyzer.analyze_commit("/fake/repo", _fake_commit())

        # 4 true duplicates removed (5 identical → 1 kept); cross-service and unique are kept
        assert result.duplicates_removed == 4
        assert len(result.issues) == 3
        assert result.ai_debt_score == 60  # 3 issues × 20 min

        # Both "reflection" issues at distinct locations are flagged as cross-service
        reflection = [i for i in result.issues if i.description == "Method uses reflection unsafely"]
        assert len(reflection) == 2
        assert all(i.is_cross_service_pattern for i in reflection)

        # Unique issue is not a cross-service pattern
        other = [i for i in result.issues if i.description == "Different finding"]
        assert len(other) == 1
        assert not other[0].is_cross_service_pattern

    @patch("td_agent.analyzer.get_provider")
    @patch("td_agent.analyzer.get_source_files", return_value=[])
    def test_no_source_files_returns_zero_score(self, mock_files, mock_get_provider):
        analyzer = _make_analyzer(mock_get_provider)
        result = analyzer.analyze_commit("/fake/repo", _fake_commit())

        assert result.ai_debt_score == 0
        assert result.issues == []
        assert result.analysis_error is None
        analyzer._provider.analyze.assert_not_called()

    @patch("td_agent.analyzer.get_provider")
    @patch("td_agent.analyzer.get_source_files", return_value=["src/Main.py"])
    @patch("td_agent.analyzer.read_file_at_commit", return_value="x = 1")
    def test_llm_error_captured(self, mock_read, mock_files, mock_get_provider):
        analyzer = _make_analyzer(mock_get_provider)
        analyzer._provider.analyze.side_effect = Exception("API rate limit")

        result = analyzer.analyze_commit("/fake/repo", _fake_commit())

        assert result.analysis_error is not None
        assert "API rate limit" in result.analysis_error
        assert result.ai_debt_score == 0

    def test_category_breakdown(self):
        commit = _fake_commit()
        issues = [
            TechnicalDebtIssue("code_smell", "low", 10, "d", "l", "s"),
            TechnicalDebtIssue("code_smell", "medium", 20, "d", "l", "s"),
            TechnicalDebtIssue("complexity", "high", 60, "d", "l", "s"),
        ]
        result = CommitAnalysisResult(
            commit=commit,
            issues=issues,
            ai_debt_score=90,
            files_analyzed=3,
            overall_assessment="test",
        )
        assert result.category_breakdown == {"code_smell": 30, "complexity": 60}

    def test_severity_breakdown(self):
        commit = _fake_commit()
        issues = [
            TechnicalDebtIssue("code_smell", "low", 10, "d", "l", "s"),
            TechnicalDebtIssue("code_smell", "high", 20, "d", "l", "s"),
            TechnicalDebtIssue("complexity", "high", 60, "d", "l", "s"),
        ]
        result = CommitAnalysisResult(
            commit=commit,
            issues=issues,
            ai_debt_score=90,
            files_analyzed=3,
            overall_assessment="test",
        )
        assert result.severity_breakdown == {"low": 1, "high": 2}

    @patch("td_agent.analyzer.get_provider")
    @patch("td_agent.analyzer.get_source_files",
           return_value=[f"src/file_{i}.py" for i in range(200)])
    @patch("td_agent.analyzer.read_file_at_commit", return_value="x = 1")
    def test_file_count_capped(self, mock_read, mock_files, mock_get_provider):
        analyzer = _make_analyzer(mock_get_provider)
        analyzer._provider.analyze.return_value = _fake_llm_response(issues=[], files=analyzer.MAX_FILES)

        result = analyzer.analyze_commit("/fake/repo", _fake_commit())

        assert result.analysis_error is None
        # 200 unique candidates, capped at MAX_FILES → the rest are skipped
        assert result.files_skipped == 200 - analyzer.MAX_FILES
        # Confirm analyze() was called exactly once (all files batched in one call)
        analyzer._provider.analyze.assert_called_once()

    @patch("td_agent.analyzer.get_provider")
    @patch("td_agent.analyzer.get_source_files", return_value=[
        "src/util.py",
        "src/auth/login.py",
        "src/main.py",
        "package-lock.json",
        "proto/schema_pb2.py",
        "static/vendor.min.js",
        "dist/bundle.js",
    ])
    @patch("td_agent.analyzer.read_file_at_commit", return_value="x = 1")
    def test_prioritization_and_exclusions(self, mock_read, mock_files, mock_get_provider):
        analyzer = _make_analyzer(mock_get_provider)
        analyzer._provider.analyze.return_value = _fake_llm_response(issues=[], files=3)

        analyzer.analyze_commit("/fake/repo", _fake_commit())

        prompt = analyzer._provider.analyze.call_args.args[0]
        # Excluded files never reach the prompt
        assert "package-lock.json" not in prompt
        assert "schema_pb2.py" not in prompt
        assert "vendor.min.js" not in prompt
        assert "dist/bundle.js" not in prompt
        # Debt-prone (auth) file appears before entry point, which appears
        # before the plain remaining file (churn/recency tiers are empty for
        # a nonexistent repo path)
        auth_pos = prompt.index("src/auth/login.py")
        main_pos = prompt.index("src/main.py")
        util_pos = prompt.index("src/util.py")
        assert auth_pos < main_pos < util_pos

    @patch("td_agent.analyzer.get_provider")
    @patch("td_agent.analyzer.get_source_files", return_value=["src/A.py"])
    @patch("td_agent.analyzer.read_file_at_commit", return_value="x = 1")
    def test_provider_error_captured_as_analysis_error(self, mock_read, mock_files, mock_get_provider):
        analyzer = _make_analyzer(mock_get_provider)
        analyzer._provider.analyze.side_effect = ValueError("provider returned an empty response")

        result = analyzer.analyze_commit("/fake/repo", _fake_commit())

        assert result.analysis_error is not None
        assert "empty" in result.analysis_error.lower()

    def test_missing_api_key_raises(self):
        original = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                TechnicalDebtAnalyzer(api_key=None)
        finally:
            if original is not None:
                os.environ["GEMINI_API_KEY"] = original

    @patch("td_agent.analyzer.get_provider")
    def test_provider_selection_is_delegated(self, mock_get_provider):
        """analyzer.py must not hardcode a provider — selection is entirely get_provider()'s job."""
        mock_provider = MagicMock()
        mock_provider.model = "claude-sonnet-4-5"
        mock_get_provider.return_value = mock_provider

        analyzer = TechnicalDebtAnalyzer(provider="claude", api_key="test-key", model="claude-sonnet-4-5")

        mock_get_provider.assert_called_once()
        _, kwargs = mock_get_provider.call_args
        assert mock_get_provider.call_args.args[0] == "claude"
        assert kwargs["api_key"] == "test-key"
        assert kwargs["model"] == "claude-sonnet-4-5"
        assert analyzer.model == "claude-sonnet-4-5"
