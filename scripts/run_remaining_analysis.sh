#!/usr/bin/env bash
# Run AI analysis for the two repos that hit Gemini quota on first attempt,
# then append their results to data/ai_comparison_summary.csv.
#
# Usage: ./scripts/run_remaining_analysis.sh
# Prerequisites: FastAPI server running on localhost:8000

set -euo pipefail

API="http://localhost:8000"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="$REPO_ROOT/data"
SUMMARY_CSV="$DATA_DIR/ai_comparison_summary.csv"

REPOS=(
    "spring-petclinic-microservices|https://github.com/spring-petclinic/spring-petclinic-microservices"
    "robot-shop|https://github.com/instana/robot-shop"
)

# ── 1. Wait for API ───────────────────────────────────────────────────────────
echo "Checking FastAPI server at $API ..."
for i in $(seq 1 30); do
    if curl -sf "$API/api/repos" > /dev/null 2>&1; then
        echo "  Server up (attempt $i)"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: FastAPI server not reachable after 30 attempts. Start it with:" >&2
        echo "  cd $REPO_ROOT/web-api && uvicorn main:app --port 8000" >&2
        exit 1
    fi
    echo "  Waiting ... ($i/30)"
    sleep 10
done

# ── 2. Analyse each repo ──────────────────────────────────────────────────────
declare -A RESULTS  # repo_name → json result blob

for entry in "${REPOS[@]}"; do
    REPO_NAME="${entry%%|*}"
    REPO_URL="${entry##*|}"

    echo ""
    echo "════════════════════════════════════════════════════"
    echo "Analysing: $REPO_NAME"
    echo "════════════════════════════════════════════════════"

    JOB_RESP=$(curl -sf -X POST "$API/api/analyse" \
        -H "Content-Type: application/json" \
        -d "{\"repo_url\": \"$REPO_URL\", \"mode\": \"latest\"}")
    JOB_ID=$(echo "$JOB_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
    echo "  Job ID: $JOB_ID"

    # Poll until done or failed
    for i in $(seq 1 120); do
        JOB=$(curl -sf "$API/api/jobs/$JOB_ID")
        STATUS=$(echo "$JOB" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['status'])")
        STAGE=$(echo  "$JOB" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['progress']['stage'])")
        echo "  [$i] $STATUS / $STAGE"

        if [ "$STATUS" = "done" ]; then
            break
        elif [ "$STATUS" = "failed" ]; then
            ERR=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error',''))")
            echo "  FAILED: $ERR" >&2
            # Don't exit — try the next repo
            break
        fi
        sleep 20
    done

    if [ "$STATUS" != "done" ]; then
        echo "  Skipping $REPO_NAME — did not complete." >&2
        RESULTS["$REPO_NAME"]=""
        continue
    fi

    RESULT=$(curl -sf "$API/api/results/$REPO_NAME")
    RESULTS["$REPO_NAME"]="$RESULT"
    echo "  Result fetched."
done

# ── 3. Append to summary CSV ──────────────────────────────────────────────────
echo ""
echo "Updating $SUMMARY_CSV ..."

python3 - "$SUMMARY_CSV" "${!RESULTS[@]}" << 'PYEOF'
import sys, csv, json, subprocess
from pathlib import Path

summary_path = Path(sys.argv[1])
repo_names = sys.argv[2:]  # names of repos to update

# Read existing rows
with open(summary_path, newline="", encoding="utf-8") as f:
    fieldnames = None
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

# Build result map from API
results = {}
for name in repo_names:
    raw = subprocess.run(
        ["curl", "-sf", f"http://localhost:8000/api/results/{name}"],
        capture_output=True, text=True,
    )
    if raw.returncode != 0 or not raw.stdout.strip():
        continue
    try:
        r = json.loads(raw.stdout)
    except json.JSONDecodeError:
        continue
    score  = r["ai_debt_score"]
    issues = r["issue_count"]
    dups   = r.get("duplicates_removed", 0)
    sevs   = r.get("severity_breakdown", {})
    cats   = r.get("category_breakdown", {})
    top_cat = max(cats, key=cats.get) if cats else ""
    avg    = round(score / issues, 1) if issues else 0
    issue_list = r.get("issues", [])
    cross = sum(1 for i in issue_list if i.get("is_cross_service_pattern"))
    results[name] = {
        "repo_name":           name,
        "ai_debt_score":       score,
        "issue_count":         issues,
        "avg_min_per_issue":   avg,
        "top_category":        top_cat,
        "duplicates_removed":  dups,
        "severity_critical":   sevs.get("critical", 0),
        "severity_high":       sevs.get("high", 0),
        "severity_medium":     sevs.get("medium", 0),
        "severity_low":        sevs.get("low", 0),
        "cross_service_patterns": cross,
        "model":               r.get("model", ""),
        "analysed_date":       r.get("commit", {}).get("date", "")[:10],
    }

# Update rows in-place; append new ones not yet present
repo_order = {r["repo_name"]: i for i, r in enumerate(rows)}
for name, data in results.items():
    if name in repo_order:
        rows[repo_order[name]] = data
    else:
        rows.append(data)

with open(summary_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Updated {summary_path} — {len(results)} repo(s) written")
PYEOF

# ── 4. Final summary ──────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════"
echo "Final summary — all repos"
echo "════════════════════════════════════════════════════"
python3 - "$SUMMARY_CSV" << 'PYEOF'
import sys, csv

path = sys.argv[1]
with open(path, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

print(f"{'Repo':<36} {'Score':>7} {'Issues':>7} {'Avg':>7} {'Top Category':<20} {'CSP':>4}")
print("─" * 86)
for r in rows:
    score = r.get("ai_debt_score", "")
    issues = r.get("issue_count", "")
    avg = r.get("avg_min_per_issue", "")
    top = r.get("top_category", "—")
    csp = r.get("cross_service_patterns", "")
    if score:
        print(f"{r['repo_name']:<36} {int(score):>7,} {int(issues):>7} {float(avg):>7.1f} {top:<20} {csp:>4}")
    else:
        print(f"{r['repo_name']:<36} {'PENDING':>7}")
PYEOF

echo ""
echo "Done."
