"""Git repository helpers — commit history and file reading without checkout."""

import logging
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

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


def get_churn_data(repo_path: str) -> dict:
    """Compute per-file change frequency across the full commit history.

    Parses a single ``git log --numstat`` invocation — pure git metadata,
    no file reading, no API calls. Fast even on large histories.

    Returns a dict with:
      - top_churned_files: top 10 files by change count, each
        {"path": str, "change_count": int, "author_count": int}
      - total_commits: number of commits in the history
      - hotspot_threshold: 75th-percentile change count; files at or above
        this are considered hotspots
    """
    path = Path(repo_path).expanduser().resolve()
    # %H<TAB>%an marks each commit header; numstat lines follow as
    # "<added>\t<deleted>\t<path>".
    proc = subprocess.run(
        ["git", "-C", str(path), "log", "--numstat", "--format=%H%x09%an"],
        capture_output=True, text=True, check=True,
    )

    change_count: Dict[str, int] = {}
    file_authors: Dict[str, Set[str]] = {}
    total_commits = 0
    current_author = ""

    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        first = parts[0]
        if len(parts) == 2 and len(first) == 40 and all(c in "0123456789abcdef" for c in first):
            total_commits += 1
            current_author = parts[1]
            continue
        if len(parts) == 3:
            file_path = parts[2]
            # Normalise rename notation: "old => new" / "dir/{old => new}/f"
            if "=>" in file_path:
                if "{" in file_path:
                    prefix, rest = file_path.split("{", 1)
                    inner, suffix = rest.split("}", 1)
                    new_part = inner.split("=>")[-1].strip()
                    file_path = (prefix + new_part + suffix).replace("//", "/")
                else:
                    file_path = file_path.split("=>")[-1].strip()
            if _is_excluded(file_path):
                continue
            change_count[file_path] = change_count.get(file_path, 0) + 1
            file_authors.setdefault(file_path, set()).add(current_author)

    if not change_count:
        return {"top_churned_files": [], "total_commits": total_commits, "hotspot_threshold": 0}

    counts = sorted(change_count.values())
    # 75th percentile (nearest-rank method)
    rank = max(1, math.ceil(0.75 * len(counts)))
    hotspot_threshold = counts[rank - 1]

    ranked = sorted(change_count.items(), key=lambda kv: (-kv[1], kv[0]))
    top_churned_files = [
        {
            "path": p,
            "change_count": n,
            "author_count": len(file_authors.get(p, set())),
        }
        for p, n in ranked[:10]
    ]

    return {
        "top_churned_files": top_churned_files,
        "total_commits": total_commits,
        "hotspot_threshold": hotspot_threshold,
    }


def get_recent_files(repo_path: str, commit_hash: str, n_commits: int = 10) -> List[str]:
    """Paths touched by the ``n_commits`` most recent commits up to ``commit_hash``.

    Order-preserving and de-duplicated (most recently touched first).
    """
    path = Path(repo_path).expanduser().resolve()
    proc = subprocess.run(
        ["git", "-C", str(path), "log", "--name-only", "--format=",
         "-n", str(n_commits), commit_hash],
        capture_output=True, text=True, check=True,
    )
    seen: Set[str] = set()
    result: List[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            result.append(line)
    return result


def get_file_sizes(repo_path: str, commit_hash: str) -> Dict[str, int]:
    """Blob sizes (bytes) for every file at a commit, without checkout."""
    repo = _open_repo(repo_path)
    commit = repo.commit(commit_hash)
    return {
        blob.path: blob.size
        for blob in commit.tree.traverse()
        if blob.type == "blob"
    }


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
