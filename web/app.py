"""Flask web dashboard for td-agent results."""

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from td_agent.report import list_analyzed_repos, load_results  # noqa: E402

app = Flask(__name__)
app.config["DATA_DIR"] = _ROOT / "data"
app.config["SECRET_KEY"] = os.urandom(24)

# SonarQube results live in the dissertation directory (not part of this project).
# If the path doesn't exist the comparison section is simply hidden.
_SONAR_DIR = Path.home() / "dissertation" / "results"


# ---------------------------------------------------------------------------
# SonarQube helper
# ---------------------------------------------------------------------------

def _load_sonar(repo_name: str) -> dict:
    """Return SonarQube rows keyed by full commit_hash, or {} if unavailable."""
    path = _SONAR_DIR / f"{repo_name}_results.csv"
    if not path.exists():
        return {}
    data: dict = {}
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                h = row.get("commit_hash", "").strip()
                if h:
                    data[h] = {
                        "sqale_index": int(row.get("sqale_index") or 0),
                        "commit_date":  row.get("commit_date", "")[:10],
                        "code_smells":  int(row.get("code_smells") or 0),
                        "bugs":         int(row.get("bugs") or 0),
                    }
    except Exception:
        return {}
    return data


def _sonar_summary(sonar: dict) -> dict | None:
    """Latest SonarQube stats, or None if no data."""
    if not sonar:
        return None
    latest = max(sonar.values(), key=lambda s: s["commit_date"])
    return latest


def _data_dir() -> Path:
    return Path(app.config["DATA_DIR"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    repos = list_analyzed_repos(_data_dir())
    summaries = []
    for name in sorted(repos):
        rows = load_results(name, _data_dir())
        if not rows:
            continue
        latest = rows[-1]           # sorted oldest→newest by load_results
        sonar = _load_sonar(name)
        sq = _sonar_summary(sonar)
        summaries.append({
            "name":          name,
            "commit_count":  len(rows),
            "latest_score":  latest["ai_debt_score"],
            "latest_sonar":  sq["sqale_index"] if sq else None,
            "latest_date":   latest["commit_date"][:10],
        })
    return render_template("index.html", repos=summaries)


@app.route("/project/<name>")
def project(name):
    rows = load_results(name, _data_dir())
    if not rows:
        return f"No results for '{name}'. Run td-agent analyze first.", 404

    sonar  = _load_sonar(name)
    sq_sum = _sonar_summary(sonar)

    # Most recent commit breakdown data for the donut charts
    latest = rows[-1]
    cat_data = latest["category_breakdown"]   # {category: minutes}
    sev_data = latest["severity_breakdown"]   # {severity: count}

    # Flatten all issues across commits for the issue table
    all_issues = []
    for r in rows:
        for issue in r.get("issues", []):
            all_issues.append({
                **issue,
                "commit_short_hash": r["commit_short_hash"],
                "commit_date":       r["commit_date"][:10],
            })
    # Default sort: most expensive first
    all_issues.sort(key=lambda i: -i.get("remediation_minutes", 0))

    return render_template(
        "project.html",
        repo_name=name,
        rows=rows,
        sonar=sonar,
        sq_summary=sq_sum,
        cat_data=cat_data,
        sev_data=sev_data,
        all_issues=all_issues,
    )


@app.route("/api/data/<name>")
def api_data(name):
    """JSON endpoint consumed by Chart.js on the project page."""
    rows  = load_results(name, _data_dir())
    sonar = _load_sonar(name)

    labels        = []
    ai_scores     = []
    sonar_matched = []   # sqale_index for the same commit, or null

    for r in rows:
        labels.append(r["commit_short_hash"])
        ai_scores.append(r["ai_debt_score"])
        sq = sonar.get(r["commit_hash"])
        sonar_matched.append(sq["sqale_index"] if sq else None)

    # Full SonarQube timeline for the secondary chart (all analyzed commits)
    sonar_timeline = sorted(
        [{"date": v["commit_date"], "sqale": v["sqale_index"]} for v in sonar.values()],
        key=lambda x: x["date"],
    ) if sonar else []

    return jsonify({
        "labels":          labels,
        "dates":           [r["commit_date"][:10] for r in rows],
        "scores":          ai_scores,
        "issue_counts":    [r["issue_count"] for r in rows],
        "sonar_matched":   sonar_matched,
        "sonar_timeline":  sonar_timeline,
    })


@app.route("/analyze", methods=["GET", "POST"])
def run_analysis():
    if request.method == "GET":
        return render_template("analyze.html")

    repo_path = request.form.get("repo_path", "").strip()
    mode      = request.form.get("mode", "sample_every")
    n_value   = request.form.get("n_value", "20")

    if not repo_path:
        return render_template("analyze.html", error="Repository path is required.")

    resolved = Path(repo_path).expanduser().resolve()
    if not resolved.exists():
        return render_template("analyze.html", error=f"Path does not exist: {resolved}")

    cmd = [sys.executable, "-m", "td_agent.cli", "analyze", "--repo", str(resolved)]
    if mode == "test":
        cmd.append("--test")
    elif mode == "commits":
        cmd += ["--commits", n_value]
    else:
        cmd += ["--sample-every", n_value]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(_ROOT), timeout=3600,
        )
        repo_name = resolved.name
        output = result.stdout + result.stderr
        if result.returncode == 0:
            return redirect(url_for("project", name=repo_name))
        return render_template("analyze.html", error=output[-2000:] if output else "Analysis failed.")
    except subprocess.TimeoutExpired:
        return render_template("analyze.html", error="Analysis timed out (1 hour limit).")
    except Exception as exc:
        return render_template("analyze.html", error=str(exc))


if __name__ == "__main__":
    print("TD Agent dashboard → http://localhost:5000")
    app.run(debug=True, port=5000)
