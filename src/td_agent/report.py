"""CSV persistence and HTML report generation for analysis results."""

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional

from .analyzer import CommitAnalysisResult

_DATA_DIR = Path(__file__).parent.parent.parent / "data"

_FIELDNAMES = [
    "commit_hash",
    "commit_short_hash",
    "commit_date",
    "commit_message",
    "model",
    "ai_debt_score",
    "issue_count",
    "files_analyzed",
    "category_breakdown",
    "severity_breakdown",
    "issues",            # full issue list as JSON array
    "overall_assessment",
    "summary",
    "duplicates_removed",
]


_CONFIDENCE_SCORES = {"low": 1, "medium": 2, "high": 3}


def provider_from_model(model: str) -> str:
    """Infer the provider name from a model string (e.g. 'gemini-2.5-flash-lite' -> 'gemini')."""
    m = (model or "").lower()
    if m.startswith("claude"):
        return "claude"
    if m.startswith("gemini"):
        return "gemini"
    return "unknown"


def average_confidence(issues: List[Dict]) -> Optional[float]:
    """Mean confidence across issues on a low=1/medium=2/high=3 scale, or None if no issues."""
    scores = [_CONFIDENCE_SCORES[i["confidence"]] for i in issues if i.get("confidence") in _CONFIDENCE_SCORES]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


def _data_dir(override: Optional[Path]) -> Path:
    base = override or _DATA_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_csv_path(repo_name: str, data_dir: Optional[Path] = None) -> Path:
    return _data_dir(data_dir) / f"{repo_name}_ai_results.csv"


def save_results(
    results: List[CommitAnalysisResult],
    repo_name: str,
    data_dir: Optional[Path] = None,
) -> Path:
    """Append successful results to CSV, skipping any that already have a clean row.

    Failed analyses (analysis_error set) are never written — they are logged to
    stderr by the CLI and do not pollute the stored data.
    """
    path = get_csv_path(repo_name, data_dir)

    # Collect (commit_hash, model) pairs that already have a *successful* row
    # so we never overwrite good data and never double-write — keyed by model
    # (not just commit_hash) so re-analysing the same commit with a different
    # provider adds a new row instead of being silently dropped.
    existing_ok: set = set()
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            existing_ok = {(row["commit_hash"], row["model"]) for row in csv.DictReader(f)}

    mode = "a" if path.exists() else "w"
    with open(path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
        if mode == "w":
            writer.writeheader()
        for r in results:
            if r.analysis_error:
                continue                      # skip failed analyses entirely
            if (r.commit.hash, r.model) in existing_ok:
                continue                      # already stored
            writer.writerow({
                "commit_hash":        r.commit.hash,
                "commit_short_hash":  r.commit.short_hash,
                "commit_date":        r.commit.date.isoformat(),
                "commit_message":     r.commit.message,
                "model":              r.model,
                "ai_debt_score":      r.ai_debt_score,
                "issue_count":        len(r.issues),
                "files_analyzed":     r.files_analyzed,
                "category_breakdown": json.dumps(r.category_breakdown),
                "severity_breakdown": json.dumps(r.severity_breakdown),
                "issues":             json.dumps([
                    {
                        "category":                i.category,
                        "severity":                i.severity,
                        "confidence":              i.confidence,
                        "remediation_minutes":     i.remediation_minutes,
                        "description":             i.description,
                        "location":                i.location,
                        "suggestion":              i.suggestion,
                        "why_debt":                i.why_debt,
                        "is_cross_service_pattern": i.is_cross_service_pattern,
                    }
                    for i in r.issues
                ]),
                "overall_assessment": r.overall_assessment,
                "summary":            r.summary,
                "duplicates_removed": r.duplicates_removed,
            })
    return path


def load_results(repo_name: str, data_dir: Optional[Path] = None) -> List[Dict]:
    """Load CSV results as plain dicts with all JSON fields parsed."""
    path = get_csv_path(repo_name, data_dir)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["category_breakdown"] = json.loads(row.get("category_breakdown") or "{}")
        row["severity_breakdown"] = json.loads(row.get("severity_breakdown") or "{}")
        row["issues"]             = json.loads(row.get("issues") or "[]")
        row["ai_debt_score"]      = int(row.get("ai_debt_score") or 0)
        row["issue_count"]        = int(row.get("issue_count") or 0)
        row["files_analyzed"]     = int(row.get("files_analyzed") or 0)
        row["duplicates_removed"] = int(row.get("duplicates_removed") or 0)
    # Sort oldest → newest for timeline charts
    rows.sort(key=lambda r: r["commit_date"])
    return rows


def list_analyzed_repos(data_dir: Optional[Path] = None) -> List[str]:
    """Return names of repos that have result CSV files."""
    base = _data_dir(data_dir)
    return [p.stem.removesuffix("_ai_results") for p in base.glob("*_ai_results.csv")]


def build_html_report(repo_name: str, data: List[Dict]) -> str:
    """Generate a standalone HTML report with a Chart.js debt-score timeline."""
    labels = json.dumps([r["commit_short_hash"] for r in data])
    scores = json.dumps([r["ai_debt_score"] for r in data])

    rows = ""
    for r in data:
        sev = r["severity_breakdown"]
        sev_str = ", ".join(f"{k}:{v}" for k, v in sorted(sev.items()))
        rows += (
            f"<tr>"
            f"<td>{r['commit_short_hash']}</td>"
            f"<td>{r['commit_date'][:10]}</td>"
            f"<td><strong>{r['ai_debt_score']}</strong></td>"
            f"<td>{r['issue_count']}</td>"
            f"<td>{r['files_analyzed']}</td>"
            f"<td>{sev_str}</td>"
            f"<td style='max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>"
            f"{r['overall_assessment'][:150]}</td>"
            f"</tr>\n"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TD Agent — {repo_name}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          max-width: 1200px; margin: 2rem auto; padding: 0 1rem; color: #333; }}
  h1 {{ border-bottom: 2px solid #dc3545; padding-bottom: .5rem; }}
  .chart-container {{ max-height: 380px; margin: 2rem 0; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .9rem; }}
  th, td {{ border: 1px solid #dee2e6; padding: .55rem .75rem; text-align: left; }}
  thead {{ background: #f8f9fa; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
</style>
</head>
<body>
<h1>Technical Debt Report — {repo_name}</h1>
<div class="chart-container"><canvas id="debtChart"></canvas></div>
<script>
new Chart(document.getElementById('debtChart'), {{
  type: 'line',
  data: {{
    labels: {labels},
    datasets: [{{
      label: 'AI Technical Debt Score (minutes)',
      data: {scores},
      borderColor: 'rgb(220,53,69)',
      backgroundColor: 'rgba(220,53,69,0.08)',
      fill: true, tension: 0.3, pointRadius: 4,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ title: {{ display: true, text: 'AI Technical Debt Score over Commit History' }}, legend: {{ position: 'bottom' }} }},
    scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: 'Remediation Minutes' }} }} }}
  }}
}});
</script>
<h2>Commit-by-Commit Results</h2>
<table>
<thead><tr><th>Commit</th><th>Date</th><th>Debt Score (min)</th><th>Issues</th><th>Files</th><th>Severity</th><th>Assessment</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>"""
