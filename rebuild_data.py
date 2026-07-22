"""One-off data recovery script.

Context: the local data/ directory (gitignored) was lost to hardware
damage. This rebuilds data/<repo>_ai_results.csv for each previously
analysed repo using ONLY the aggregate figures the analyst recovered
from their own notes (score, issue_count, severity_breakdown, top
category, model, date, summary).

It deliberately does NOT fabricate per-issue detail (individual
descriptions, file locations, per-issue remediation minutes) — that
level of detail was not recoverable from notes and inventing it would
misrepresent synthetic content as original Gemini analysis output.
Each row's `issues` field instead contains a single explanatory
placeholder, and `summary`/`overall_assessment` are prefixed with an
explicit data-recovery disclaimer so the dashboard and raw CSV both
make the reconstruction obvious.

Run with: python3 rebuild_data.py
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

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
    "issues",
    "overall_assessment",
    "summary",
    "duplicates_removed",
]

DISCLAIMER = (
    "[DATA RECOVERY NOTE: the original data/ directory was lost to hardware "
    "damage. This row's aggregate figures (score, issue count, severity "
    "breakdown, top category) are real, recovered from the analyst's own "
    "notes taken during the original run. Per-issue detail (individual "
    "findings, file locations, remediation minutes per issue) was NOT "
    "recoverable and has not been fabricated — see the single placeholder "
    "entry in `issues` below.] "
)

REPOS = [
    dict(name="piggymetrics", score=495, issues=65, date="2021-11-15",
         top_category="maintainability", severity=dict(critical=0, high=2, medium=5, low=58),
         summary=("High technical debt in JS code quality and auth security. dashboard.js/"
                   "login.js have extremely long functions, global variable overuse, "
                   "duplication. Critical flaw: NoOpPasswordEncoder in auth service.")),
    dict(name="train-ticket", score=280, issues=31, date="2022-11-01",
         top_category="maintainability", severity=dict(critical=0, high=0, medium=3, low=28),
         summary=("Maintainability/testing debt — repetitive controllers, hardcoded config, "
                   "verbose logging. Fragile UI tests + weak JWT error handling risk cascading "
                   "failures. Cross-service pattern detected: SecurityConfig duplicated across "
                   "many services.")),
    dict(name="microservices-demo", score=200, issues=17, date="2026-07-09",
         top_category="maintainability", severity=dict(critical=0, high=0, medium=0, low=17),
         summary=("Duplicated Go utility code (env var mapping, gRPC client setup, "
                   "profiling/tracing init) across services. Risk: a bug fixed in one copy "
                   "but not others.")),
    dict(name="DeathStarBench", score=1385, issues=31, date="2024-06-27",
         top_category="maintainability", severity=dict(critical=0, high=5, medium=23, low=3),
         summary=("Complex, lengthy functions in the hotel reservation system violating SRP. "
                   "Duplicated service-init/data-handling logic; Dapr social-network apps rely "
                   "on global config state.")),
    dict(name="geoserver-cloud", score=315, issues=9, date="2026-07-06",
         top_category="maintainability", severity=dict(critical=0, high=0, medium=6, low=3),
         summary=("Moderate debt — duplicated filter logic (NpeAwareSuffixStripFilter) across "
                   "modules, monolithic Web UI config, reflection-based gateway filter "
                   "management.")),
    dict(name="taotao-cloud-project", score=490, issues=36, date="2026-06-27",
         top_category="maintainability", severity=dict(critical=0, high=1, medium=25, low=10),
         summary=("Directory-traversal vulnerability in a shell script is the standout issue; "
                   "otherwise verbose logging, commented-out code, empty files/packages.")),
    dict(name="erda", score=365, issues=22, date="2026-07-06",
         top_category="maintainability", severity=dict(critical=0, high=0, medium=3, low=19),
         summary=("Debt concentrated in the AI proxy service — verbose config loading, token "
                   "estimation logic, duplicated request/error handling across HTTP/gRPC. "
                   "Architectural debt in model-provider extensibility.")),
    dict(name="light-4j", score=190, issues=20, date="2026-06-22",
         top_category="code_smell", severity=dict(critical=0, high=0, medium=3, low=17),
         summary=("Code smells + missing docs in config modules. Many client-module tests "
                   "disabled/deprecated — risk of auth/config regressions going undetected.")),
    dict(name="spring-petclinic-microservices", score=1770, issues=100, date="2026-05-17",
         top_category="architectural", severity=dict(critical=0, high=0, medium=4, low=96),
         summary=("Architectural debt from hardcoded service hostnames; maintainability debt "
                   "from inconsistent JS module patterns and mutable state. Risk: brittle "
                   "service integration, deployment failures.")),
    dict(name="robot-shop", score=1530, issues=75, date="2023-03-06",
         top_category="maintainability", severity=dict(critical=0, high=3, medium=55, low=17),
         summary=("Maintainability/complexity/testing debt — outdated deps, logic embedded in "
                   "handlers, thin test coverage. Critical: weak DB credentials and exposed "
                   "secrets (hardcoded MySQL password, useSSL=false).")),
]

MODEL = "gemini-2.5-flash-lite"


def placeholder_issue(repo: dict) -> dict:
    return {
        "category": "data-recovery",
        "severity": "low",
        "confidence": "low",
        "remediation_minutes": 0,
        "description": (
            f"Original per-issue detail for this analysis ({repo['issues']} findings, "
            f"{repo['score']} min total) was lost to hardware damage and could not be "
            "recovered from notes. This placeholder replaces those findings rather than "
            "fabricating them; the aggregate score, issue count, and severity breakdown "
            "above are real."
        ),
        "location": "",
        "suggestion": "",
        "why_debt": "",
        "is_cross_service_pattern": False,
    }


def build_row(repo: dict) -> dict:
    sev = repo["severity"]
    return {
        "commit_hash": "unknown-data-recovery",
        "commit_short_hash": "unknown",
        "commit_date": f"{repo['date']}T00:00:00",
        "commit_message": "[data-recovery] original commit metadata lost; see summary field",
        "model": MODEL,
        "ai_debt_score": repo["score"],
        "issue_count": repo["issues"],
        "files_analyzed": 0,
        "category_breakdown": json.dumps({repo["top_category"]: repo["score"]}),
        "severity_breakdown": json.dumps(sev),
        "issues": json.dumps([placeholder_issue(repo)]),
        "overall_assessment": DISCLAIMER,
        "summary": DISCLAIMER + repo["summary"],
        "duplicates_removed": 0,
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for repo in REPOS:
        path = DATA_DIR / f"{repo['name']}_ai_results.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
            writer.writeheader()
            writer.writerow(build_row(repo))
        written.append(path)
        print(f"wrote {path}")

    summary_path = DATA_DIR / "ai_comparison_summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "repo", "ai_debt_score", "issue_count", "model", "date",
            "top_category", "critical", "high", "medium", "low", "summary",
        ])
        for repo in REPOS:
            sev = repo["severity"]
            writer.writerow([
                repo["name"], repo["score"], repo["issues"], MODEL, repo["date"],
                repo["top_category"], sev["critical"], sev["high"], sev["medium"], sev["low"],
                repo["summary"],
            ])
    print(f"wrote {summary_path}")
    print(f"\n{len(written)} repo CSVs + 1 comparison summary written to {DATA_DIR}")


if __name__ == "__main__":
    main()
