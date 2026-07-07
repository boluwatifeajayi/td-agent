"""Unit tests for git_utils churn analysis with mocked subprocess."""

from unittest.mock import MagicMock, patch

from td_agent.git_utils import get_churn_data

_HASH_A = "a" * 40
_HASH_B = "b" * 40
_HASH_C = "c" * 40


def _mock_git_log(stdout: str) -> MagicMock:
    proc = MagicMock()
    proc.stdout = stdout
    proc.returncode = 0
    return proc


class TestGetChurnData:

    @patch("td_agent.git_utils.subprocess.run")
    def test_empty_repo(self, mock_run):
        mock_run.return_value = _mock_git_log("")
        data = get_churn_data("/fake/repo")
        assert data == {
            "top_churned_files": [],
            "total_commits": 0,
            "hotspot_threshold": 0,
        }

    @patch("td_agent.git_utils.subprocess.run")
    def test_top_file_ordering(self, mock_run):
        # hot.py touched in 3 commits, warm.py in 2, cold.py in 1
        log = (
            f"{_HASH_A}\tAlice\n"
            "10\t2\thot.py\n"
            "5\t1\twarm.py\n"
            "1\t0\tcold.py\n"
            "\n"
            f"{_HASH_B}\tBob\n"
            "3\t3\thot.py\n"
            "2\t0\twarm.py\n"
            "\n"
            f"{_HASH_C}\tAlice\n"
            "1\t1\thot.py\n"
        )
        mock_run.return_value = _mock_git_log(log)
        data = get_churn_data("/fake/repo")

        assert data["total_commits"] == 3
        paths = [f["path"] for f in data["top_churned_files"]]
        assert paths == ["hot.py", "warm.py", "cold.py"]
        counts = [f["change_count"] for f in data["top_churned_files"]]
        assert counts == [3, 2, 1]

    @patch("td_agent.git_utils.subprocess.run")
    def test_author_count_accuracy(self, mock_run):
        # shared.py touched by Alice and Bob; solo.py only by Alice (twice)
        log = (
            f"{_HASH_A}\tAlice\n"
            "1\t0\tshared.py\n"
            "1\t0\tsolo.py\n"
            "\n"
            f"{_HASH_B}\tBob\n"
            "2\t1\tshared.py\n"
            "\n"
            f"{_HASH_C}\tAlice\n"
            "1\t1\tsolo.py\n"
        )
        mock_run.return_value = _mock_git_log(log)
        data = get_churn_data("/fake/repo")

        by_path = {f["path"]: f for f in data["top_churned_files"]}
        assert by_path["shared.py"]["author_count"] == 2
        assert by_path["solo.py"]["author_count"] == 1
        assert by_path["solo.py"]["change_count"] == 2

    @patch("td_agent.git_utils.subprocess.run")
    def test_hotspot_threshold_is_75th_percentile(self, mock_run):
        # Four files with change counts 1, 1, 2, 4 → 75th percentile (nearest rank) = 2
        lines = [f"{_HASH_A}\tAlice", "1\t0\ta.py", "1\t0\tb.py", "1\t0\tc.py", "1\t0\td.py"]
        lines += [f"{_HASH_B}\tAlice", "1\t0\tc.py", "1\t0\td.py"]
        lines += [f"{_HASH_C}\tBob", "1\t0\td.py"]
        lines += [f"{'d' * 40}\tBob", "1\t0\td.py"]
        mock_run.return_value = _mock_git_log("\n".join(lines))
        data = get_churn_data("/fake/repo")

        assert data["total_commits"] == 4
        assert data["hotspot_threshold"] == 2

    @patch("td_agent.git_utils.subprocess.run")
    def test_excluded_dirs_and_binary_entries_skipped(self, mock_run):
        # Binary files appear as "-\t-\tpath" in numstat; still counted as a change.
        # node_modules paths must be excluded entirely.
        log = (
            f"{_HASH_A}\tAlice\n"
            "-\t-\tlogo.png\n"
            "1\t0\tnode_modules/lib/index.js\n"
            "1\t0\tsrc/app.py\n"
        )
        mock_run.return_value = _mock_git_log(log)
        data = get_churn_data("/fake/repo")

        paths = [f["path"] for f in data["top_churned_files"]]
        assert "node_modules/lib/index.js" not in paths
        assert "src/app.py" in paths
        assert "logo.png" in paths  # binary but not excluded
