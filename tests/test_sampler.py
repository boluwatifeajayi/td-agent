"""Unit tests for commit sampling logic."""

from datetime import datetime, timedelta

import pytest

from td_agent.git_utils import CommitInfo
from td_agent.sampler import sample_every_n, sample_evenly, sample_latest


def _commits(n: int) -> list:
    """Create n fake CommitInfo objects, newest first (index 0 = newest)."""
    return [
        CommitInfo(
            hash=f"{'a' * 7}{i:01x}" * 5,
            short_hash=f"abc{i:05d}",
            date=datetime(2020, 1, 1) + timedelta(days=(n - 1 - i)),
            message=f"commit {i}",
            author="test",
        )
        for i in range(n)
    ]


class TestSampleEveryN:
    def test_basic(self):
        c = _commits(10)
        result = sample_every_n(c, 2)
        # chronological = reversed(c); step 2 → indices 0, 2, 4, 6, 8
        assert len(result) == 5

    def test_n_equals_one_returns_all(self):
        c = _commits(5)
        assert len(sample_every_n(c, 1)) == 5

    def test_n_larger_than_total(self):
        c = _commits(3)
        assert len(sample_every_n(c, 10)) == 1  # only index 0

    def test_oldest_first(self):
        c = _commits(6)
        result = sample_every_n(c, 1)
        dates = [r.date for r in result]
        assert dates == sorted(dates)

    def test_invalid_n_raises(self):
        with pytest.raises(ValueError):
            sample_every_n(_commits(5), 0)


class TestSampleEvenly:
    def test_exact_count(self):
        c = _commits(100)
        result = sample_evenly(c, 10)
        assert len(result) == 10

    def test_count_exceeds_total(self):
        c = _commits(5)
        result = sample_evenly(c, 20)
        assert len(result) == 5

    def test_includes_first_and_last(self):
        c = _commits(50)
        chronological = list(reversed(c))
        result = sample_evenly(c, 5)
        assert result[0].hash == chronological[0].hash
        assert result[-1].hash == chronological[-1].hash

    def test_oldest_first(self):
        c = _commits(30)
        result = sample_evenly(c, 6)
        dates = [r.date for r in result]
        assert dates == sorted(dates)

    def test_invalid_count_raises(self):
        with pytest.raises(ValueError):
            sample_evenly(_commits(5), 0)


class TestSampleLatest:
    def test_returns_one(self):
        c = _commits(10)
        result = sample_latest(c)
        assert len(result) == 1
        assert result[0].hash == c[0].hash  # newest

    def test_empty_input(self):
        assert sample_latest([]) == []
