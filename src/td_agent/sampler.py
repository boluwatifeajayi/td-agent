"""Commit sampling strategies for controlling analysis scope."""

from typing import List

from .git_utils import CommitInfo


def sample_every_n(commits: List[CommitInfo], n: int) -> List[CommitInfo]:
    """Sample every nth commit, returned oldest-first for timeline ordering.

    ``commits`` is expected in newest-first order (as returned by get_commits).
    """
    if n < 1:
        raise ValueError(f"Sample interval must be >= 1, got {n}")
    chronological = list(reversed(commits))
    return chronological[::n]


def sample_evenly(commits: List[CommitInfo], count: int) -> List[CommitInfo]:
    """Return up to ``count`` evenly-spaced commits, oldest-first.

    Always includes the first and last commit so the chart spans the full
    project history.
    """
    if count < 1:
        raise ValueError(f"Count must be >= 1, got {count}")
    chronological = list(reversed(commits))
    total = len(chronological)
    if total <= count:
        return chronological

    # Build evenly-spaced index list including 0 and total-1
    indices = [round(i * (total - 1) / (count - 1)) for i in range(count)]
    seen: set = set()
    result = []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            result.append(chronological[idx])
    return result


def sample_latest(commits: List[CommitInfo]) -> List[CommitInfo]:
    """Return only the most recent commit (for --test mode)."""
    return [commits[0]] if commits else []
