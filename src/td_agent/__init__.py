"""td-agent — AI-powered technical debt detection using Claude."""

from .analyzer import CommitAnalysisResult, TechnicalDebtAnalyzer, TechnicalDebtIssue
from .git_utils import CommitInfo, get_commits, get_source_files, read_file_at_commit
from .sampler import sample_every_n, sample_evenly, sample_latest

__version__ = "0.1.0"
__all__ = [
    "TechnicalDebtAnalyzer",
    "CommitAnalysisResult",
    "TechnicalDebtIssue",
    "CommitInfo",
    "get_commits",
    "get_source_files",
    "read_file_at_commit",
    "sample_every_n",
    "sample_evenly",
    "sample_latest",
]
