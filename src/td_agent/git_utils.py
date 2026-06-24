"""Git repository helpers — commit history and file reading without checkout."""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import git

logger = logging.getLogger(__name__)

SOURCE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".kt", ".scala",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hxx",
    ".cs",
    ".swift",
    ".sh", ".bash",
    ".sql",
})

EXCLUDE_DIRS = frozenset({
    "node_modules", ".git", "vendor", "dist", "build",
    "target", "__pycache__", "venv", ".venv", "env",
    ".gradle", ".mvn", "coverage", "htmlcov",
    ".pytest_cache", ".mypy_cache", "site-packages",
    ".idea", ".vscode", "test-results", "out", "bin", "obj",
    ".angular", ".next", ".nuxt",
})

MAX_FILE_BYTES = 100_000


@dataclass
class CommitInfo:
    """Lightweight commit record."""
    hash: str
    short_hash: str
    date: datetime
    message: str
    author: str


def _open_repo(repo_path: str) -> git.Repo:
    path = Path(repo_path).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"Repository path does not exist: {path}")
    return git.Repo(str(path), search_parent_directories=True)


def get_commits(repo_path: str) -> List[CommitInfo]:
    """Return all commits, newest first."""
    repo = _open_repo(repo_path)
    result = []
    for c in repo.iter_commits("HEAD"):
        result.append(CommitInfo(
            hash=c.hexsha,
            short_hash=c.hexsha[:8],
            date=datetime.fromtimestamp(c.committed_date),
            message=c.message.strip().splitlines()[0],
            author=str(c.author),
        ))
    return result


def _is_excluded(path: str) -> bool:
    return any(part in EXCLUDE_DIRS for part in Path(path).parts)


def get_source_files(repo_path: str, commit_hash: str) -> List[str]:
    """List source file paths present at a given commit (sorted)."""
    repo = _open_repo(repo_path)
    commit = repo.commit(commit_hash)
    result = []
    for blob in commit.tree.traverse():
        if blob.type != "blob":
            continue
        if _is_excluded(blob.path):
            continue
        if Path(blob.path).suffix.lower() in SOURCE_EXTENSIONS:
            result.append(blob.path)
    return sorted(result)


def read_file_at_commit(repo_path: str, commit_hash: str, file_path: str) -> Optional[str]:
    """Read a file's content at a specific commit without checking out.

    Returns None if the file is binary, too large, or otherwise unreadable.
    """
    repo = _open_repo(repo_path)
    try:
        blob = repo.commit(commit_hash).tree / file_path
        raw = blob.data_stream.read()
        if len(raw) > MAX_FILE_BYTES:
            logger.debug("Skipping large file %s (%d bytes)", file_path, len(raw))
            return None
        return raw.decode("utf-8", errors="replace")
    except (KeyError, AttributeError, git.GitCommandError) as exc:
        logger.debug("Cannot read %s at %s: %s", file_path, commit_hash[:8], exc)
        return None
