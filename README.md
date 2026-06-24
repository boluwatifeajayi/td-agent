# TD Agent

![Tests](https://github.com/boluaj16/td-agent/actions/workflows/tests.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Free tier](https://img.shields.io/badge/Gemini%20API-free%20tier-orange)

**AI-powered technical debt detection that speaks the same language as SonarQube.**

TD Agent analyses a git repository's commit history by sending source-code snapshots to Google Gemini and asking it to identify technical debt. Every issue gets a realistic remediation estimate in minutes, which are summed into an **AI Technical Debt Score** — the same unit SonarQube uses for its [SQALE index](https://docs.sonarsource.com/sonarqube/latest/user-guide/metric-definitions/). This makes the two tools directly comparable, and is the core empirical contribution of an MSc Computer Science dissertation investigating whether LLM-based analysis can surface debt that static analysis misses.

> **Dissertation context** — this tool was built as part of an MSc project at [University], comparing AI-detected technical debt against SonarQube across real open-source microservice repositories. The initial results show the AI score is ~73% higher than the SonarQube SQALE index on the same codebase (piggymetrics: AI 2,130 min vs SonarQube 1,229 min), suggesting the LLM captures architectural and cross-cutting concerns that pattern-matching rules cannot.

---

## Features

- Analyses any local git repository at configurable commit intervals
- Detects **10 debt categories**: code smells, architectural issues, complexity, security, performance, duplication, maintainability, documentation, testing, dependencies
- Assigns **severity** (low / medium / high / critical) and realistic **remediation estimates** per issue
- Outputs results to **CSV** for longitudinal analysis
- **Web dashboard** (Flask + Chart.js) with timeline charts, category/severity breakdowns, and a filterable issue table
- **SonarQube comparison** — overlays AI score against SQALE index on the same timeline when both CSVs are present
- Standalone **HTML report** generation
- Built-in **rate limiter** for Gemini free tier (14 req/min to stay inside the 15 req/min quota)

---

## Demo

![Dashboard screenshot](docs/screenshot-dashboard.png)
<!-- Replace with an actual screenshot once the dashboard is running -->

---

## Requirements

- Python 3.10+
- A free [Gemini API key](https://aistudio.google.com) — no credit card required

### Free-tier limits (`gemini-2.5-flash-lite`)

| Limit | Value |
|-------|-------|
| Requests per minute | 15 (tool uses 14) |
| Requests per day | 1,500 |
| Tokens per minute | 1,000,000 |

Enough to analyse ~1,500 commits per day at zero cost.

---

## Installation

```bash
git clone https://github.com/boluaj16/td-agent
cd td-agent

# Create and activate a virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install the package and all dependencies
pip install -e .

# Set up your API key
cp .env.example .env
# then open .env and paste your GEMINI_API_KEY
```

### Getting a free Gemini API key

1. Go to [https://aistudio.google.com](https://aistudio.google.com)
2. Sign in with a Google account
3. Click **Get API key → Create API key**
4. Paste the key into `.env`:
   ```
   GEMINI_API_KEY=AIza...your_key_here...
   ```

---

## Usage

### CLI

```bash
# Quick smoke-test on the latest commit only
td-agent analyze --repo /path/to/repo --test

# Sample every 20th commit (good for large repos)
td-agent analyze --repo /path/to/repo --sample-every 20

# Sample 50 evenly-spaced commits across the full history
td-agent analyze --repo /path/to/repo --commits 50

# Generate a standalone HTML report
td-agent report --repo myproject --output report.html
```

### Web Dashboard

```bash
python web/app.py
# Open http://localhost:5000
```

The dashboard shows all analysed repositories with their latest AI debt scores. If a matching SonarQube CSV is present at `~/dissertation/results/{repo}_results.csv`, the comparison panel appears automatically.

---

## Output format

Results are saved to `data/<repo_name>_ai_results.csv`:

| Column | Description |
|--------|-------------|
| `commit_hash` | Full SHA |
| `commit_date` | ISO 8601 timestamp |
| `ai_debt_score` | Sum of remediation minutes (SQALE-comparable) |
| `issue_count` | Number of issues detected |
| `category_breakdown` | JSON: minutes per category |
| `severity_breakdown` | JSON: count per severity |
| `issues` | JSON: full issue list with description, location, suggestion |
| `files_analyzed` | Source files included in the analysis |
| `overall_assessment` | Gemini's plain-language summary |

---

## Architecture

```
src/td_agent/
  git_utils.py   — commit history traversal + file reading at commit (no checkout)
  sampler.py     — commit sampling strategies (every-n, evenly-spaced, latest)
  analyzer.py    — Gemini API integration, JSON parsing, sliding-window rate limiter
  report.py      — CSV persistence (error-safe dedup) + standalone HTML report
  cli.py         — Click CLI entry point
web/
  app.py         — Flask dashboard with SonarQube comparison loader
  templates/     — Jinja2 HTML templates (dark theme, Chart.js)
data/            — CSV output files (gitignored)
tests/           — 20 unit tests (all mocked; no real API calls)
```

### Methodology

For each sampled commit, TD Agent:

1. Lists all source files at that commit (using GitPython — no checkout required)
2. Reads up to 80 files / 400,000 characters of source code
3. Sends a single prompt to `gemini-2.5-flash-lite` requesting a structured JSON analysis
4. Parses the response into typed `TechnicalDebtIssue` objects
5. Sums `remediation_minutes` across all issues to produce the AI Debt Score

The score is intentionally defined to match SonarQube's SQALE metric so both can be plotted on the same axis and compared statistically.

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

All 20 tests mock the Gemini API — no real key or network access needed.

---

## Suggested repo name & GitHub description

**Repo name:** `td-agent`

**GitHub About:** *AI-powered technical debt analyser that scores git history with Gemini and compares against SonarQube's SQALE index. Free tier. CLI + web dashboard. MSc dissertation project.*

**Topics:** `technical-debt` `gemini-ai` `sonarqube` `code-quality` `python` `flask` `git-analysis` `msc-dissertation`

---

## License

MIT
