"""Unit tests for TechnicalDebtAnalyzer with mocked Gemini client."""

import json
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


def _make_gemini_response(response_dict: dict) -> MagicMock:
    """Build a mock Gemini response whose .text is the JSON-serialised dict."""
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(response_dict)
    return mock_resp


def _make_analyzer(mock_genai_client_cls, api_key: str = "test-key") -> TechnicalDebtAnalyzer:
    """Construct an analyzer with a mocked genai.Client."""
    mock_genai_client_cls.return_value = MagicMock()
    return TechnicalDebtAnalyzer(api_key=api_key)


class TestTechnicalDebtAnalyzer:

    @patch("td_agent.analyzer.genai.Client")
    @patch("td_agent.analyzer.get_source_files", return_value=["src/Foo.java", "src/Bar.java"])
    @patch("td_agent.analyzer.read_file_at_commit", return_value="public class Foo {}")
    def test_successful_analysis(self, mock_read, mock_files, mock_client_cls):
        analyzer = _make_analyzer(mock_client_cls)
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
        analyzer._client.models.generate_content.return_value = _make_gemini_response(llm_data)

        result = analyzer.analyze_commit("/fake/repo", _fake_commit())

        assert isinstance(result, CommitAnalysisResult)
        assert result.ai_debt_score == 150
        assert len(result.issues) == 2
        assert result.analysis_error is None
        assert result.overall_assessment == "Moderate debt, manageable."

    @patch("td_agent.analyzer.genai.Client")
    @patch("td_agent.analyzer.get_source_files", return_value=["src/SleuthAnnotationUtils.java"])
    @patch("td_agent.analyzer.read_file_at_commit", return_value="public class SleuthAnnotationUtils {}")
    def test_duplicate_issues_are_deduplicated(self, mock_read, mock_files, mock_client_cls):
        analyzer = _make_analyzer(mock_client_cls)
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
        analyzer._client.models.generate_content.return_value = _make_gemini_response(llm_data)

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

    @patch("td_agent.analyzer.genai.Client")
    @patch("td_agent.analyzer.get_source_files", return_value=[])
    def test_no_source_files_returns_zero_score(self, mock_files, mock_client_cls):
        analyzer = _make_analyzer(mock_client_cls)
        result = analyzer.analyze_commit("/fake/repo", _fake_commit())

        assert result.ai_debt_score == 0
        assert result.issues == []
        assert result.analysis_error is None

    @patch("td_agent.analyzer.genai.Client")
    @patch("td_agent.analyzer.get_source_files", return_value=["src/Main.py"])
    @patch("td_agent.analyzer.read_file_at_commit", return_value="x = 1")
    def test_llm_error_captured(self, mock_read, mock_files, mock_client_cls):
        analyzer = _make_analyzer(mock_client_cls)
        analyzer._client.models.generate_content.side_effect = Exception("API rate limit")

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

    @patch("td_agent.analyzer.genai.Client")
    @patch("td_agent.analyzer.get_source_files",
           return_value=[f"src/file_{i}.py" for i in range(200)])
    @patch("td_agent.analyzer.read_file_at_commit", return_value="x = 1")
    def test_file_count_capped(self, mock_read, mock_files, mock_client_cls):
        analyzer = _make_analyzer(mock_client_cls)
        llm_data = _fake_llm_response(issues=[], files=analyzer.MAX_FILES)
        analyzer._client.models.generate_content.return_value = _make_gemini_response(llm_data)

        result = analyzer.analyze_commit("/fake/repo", _fake_commit())

        assert result.analysis_error is None
        # 200 unique candidates, capped at MAX_FILES → the rest are skipped
        assert result.files_skipped == 200 - analyzer.MAX_FILES
        # Confirm generate_content was called exactly once (all files batched in one call)
        analyzer._client.models.generate_content.assert_called_once()

    @patch("td_agent.analyzer.genai.Client")
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
    def test_prioritization_and_exclusions(self, mock_read, mock_files, mock_client_cls):
        analyzer = _make_analyzer(mock_client_cls)
        llm_data = _fake_llm_response(issues=[], files=3)
        analyzer._client.models.generate_content.return_value = _make_gemini_response(llm_data)

        analyzer.analyze_commit("/fake/repo", _fake_commit())

        prompt = analyzer._client.models.generate_content.call_args.kwargs["contents"]
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

    @patch("td_agent.analyzer.genai.Client")
    @patch("td_agent.analyzer.get_source_files", return_value=["src/A.py"])
    @patch("td_agent.analyzer.read_file_at_commit", return_value="x = 1")
    def test_empty_response_raises_error(self, mock_read, mock_files, mock_client_cls):
        analyzer = _make_analyzer(mock_client_cls)
        empty_resp = MagicMock()
        empty_resp.text = ""
        analyzer._client.models.generate_content.return_value = empty_resp

        result = analyzer.analyze_commit("/fake/repo", _fake_commit())

        assert result.analysis_error is not None
        assert "empty" in result.analysis_error.lower()

    @patch("td_agent.analyzer.genai.Client")
    def test_missing_api_key_raises(self, mock_client_cls):
        original = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                TechnicalDebtAnalyzer(api_key=None)
        finally:
            if original is not None:
                os.environ["GEMINI_API_KEY"] = original
