"""FastAPI backend for td-agent — async analysis jobs + results API.

Run with:  cd web-api && uvicorn main:app --reload --port 8000
"""

import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Literal, Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))
load_dotenv(_ROOT / ".env")

from td_agent.analyzer import TechnicalDebtAnalyzer  # noqa: E402
from td_agent.git_utils import get_churn_data, get_commits  # noqa: E402
from td_agent.report import (  # noqa: E402
    average_confidence,
    list_analyzed_repos,
    load_results,
    select_latest,
    latest_by_provider,
    provider_from_model,
    save_results,
)
from td_agent.sampler import sample_evenly, sample_latest  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger("td-agent-api")

DATA_DIR = _ROOT / "data"
HISTORY_SAMPLE_COUNT = 10

app = FastAPI(title="TD Agent API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # local dev only
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store — fine for MVP, lost on restart.
_jobs: dict = {}


class AnalyseRequest(BaseModel):
    repo_url: str
    mode: Literal["latest", "history"] = "latest"
    provider: Literal["gemini", "claude"] = "gemini"


def _repo_name_from_url(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    return name.removesuffix(".git")


def _valid_repo_url(url: str) -> bool:
    return bool(re.match(r"^https?://[\w.\-]+/[\w.\-]+/[\w.\-]+/?$", url.rstrip("/")))


def _set_progress(job_id: str, stage: str, current: int = 0, total: int = 0) -> None:
    _jobs[job_id]["progress"] = {"current": current, "total": total, "stage": stage}


def _churn_path(repo_name: str) -> Path:
    return DATA_DIR / f"{repo_name}_churn.json"


def _meta_path(repo_name: str) -> Path:
    return DATA_DIR / f"{repo_name}_meta.json"


def _run_analysis_job(job_id: str, repo_url: str, mode: str, provider: str) -> None:
    job = _jobs[job_id]
    job["status"] = "running"
    repo_name = _repo_name_from_url(repo_url)
    tmp_dir = tempfile.mkdtemp(prefix="td-agent-")
    try:
        # 1. Clone
        _set_progress(job_id, "cloning")
        clone_path = str(Path(tmp_dir) / repo_name)
        subprocess.run(
            ["git", "clone", "--quiet", repo_url, clone_path],
            check=True, capture_output=True, text=True, timeout=600,
        )

        # 2. Churn analysis
        _set_progress(job_id, "churn")
        churn = get_churn_data(clone_path)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _churn_path(repo_name).write_text(json.dumps(churn, indent=2), encoding="utf-8")
        _meta_path(repo_name).write_text(json.dumps({"repo_url": repo_url}), encoding="utf-8")

        # 3. Select commits
        _set_progress(job_id, "selecting")
        all_commits = get_commits(clone_path)
        if mode == "history":
            sampled = sample_evenly(all_commits, HISTORY_SAMPLE_COUNT)
        else:
            sampled = sample_latest(all_commits)

        # 4. Analyse
        analyzer = TechnicalDebtAnalyzer(provider=provider)
        results = []
        for i, commit in enumerate(sampled, 1):
            _set_progress(job_id, "analysing", current=i, total=len(sampled))
            logger.info(
                "[%s] analysing %s (%d/%d) with %s",
                repo_name, commit.short_hash, i, len(sampled), analyzer.model,
            )
            results.append(analyzer.analyze_commit(clone_path, commit))

        errors = [r.analysis_error for r in results if r.analysis_error]
        if errors and len(errors) == len(results):
            raise RuntimeError(f"All commit analyses failed. First error: {errors[0]}")

        # 5. Save
        save_results(results, repo_name, DATA_DIR)
        _set_progress(job_id, "done", current=len(sampled), total=len(sampled))
        job["status"] = "done"
        job["result_id"] = repo_name
        if errors:
            job["error"] = f"{len(errors)}/{len(results)} commits failed and were skipped."
    except subprocess.CalledProcessError as exc:
        job["status"] = "failed"
        job["error"] = f"git clone failed: {exc.stderr or exc}"
        logger.error("Job %s failed: %s", job_id, job["error"])
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        logger.exception("Job %s failed", job_id)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.post("/api/analyse")
def analyse(req: AnalyseRequest, background_tasks: BackgroundTasks):
    if not _valid_repo_url(req.repo_url):
        raise HTTPException(status_code=422, detail="repo_url must be an https git URL like https://github.com/owner/repo")
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "status": "pending",
        "progress": {"current": 0, "total": 0, "stage": "queued"},
        "result_id": None,
        "error": None,
        "repo_url": req.repo_url,
        "repo_name": _repo_name_from_url(req.repo_url),
        "mode": req.mode,
        "provider": req.provider,
    }
    background_tasks.add_task(_run_analysis_job, job_id, req.repo_url, req.mode, req.provider)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return {
        "status": job["status"],
        "progress": job["progress"],
        "result_id": job["result_id"],
        "error": job["error"],
        "repo_name": job["repo_name"],
        "mode": job["mode"],
        "provider": job.get("provider", "gemini"),
    }


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _top_category(category_breakdown: dict) -> Optional[str]:
    if not category_breakdown:
        return None
    return max(category_breakdown.items(), key=lambda kv: kv[1])[0]


def _comparison_entry(row: dict) -> dict:
    return {
        "model": row.get("model", ""),
        "ai_debt_score": row["ai_debt_score"],
        "issue_count": row["issue_count"],
        "top_category": _top_category(row["category_breakdown"]),
        "severity_breakdown": row["severity_breakdown"],
        "avg_confidence": average_confidence(row["issues"]),
        "commit_date": row["commit_date"],
    }


@app.get("/api/results/{repo_name}")
def results(repo_name: str):
    rows = load_results(repo_name, DATA_DIR)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No results for '{repo_name}'")
    latest = select_latest(rows)
    meta = _load_json(_meta_path(repo_name)) or {}

    # Best row per provider, powering the Gemini-vs-Claude comparison card when
    # both have analysed this repo. This previously kept whichever row was
    # written last for each provider, which on train-ticket meant a superseded
    # model's result was compared instead of the authoritative one.
    by_provider: Dict[str, dict] = latest_by_provider(rows, provider_from_model)
    comparison = (
        {p: _comparison_entry(r) for p, r in by_provider.items()}
        if len(by_provider) > 1
        else None
    )

    return {
        "repo_name": repo_name,
        "repo_url": meta.get("repo_url"),
        "commit": {
            "hash": latest["commit_hash"],
            "short_hash": latest["commit_short_hash"],
            "date": latest["commit_date"],
            "message": latest["commit_message"],
        },
        "model": latest.get("model", ""),
        "provider": provider_from_model(latest.get("model", "")),
        "ai_debt_score": latest["ai_debt_score"],
        "issue_count": latest["issue_count"],
        "files_analyzed": latest["files_analyzed"],
        "summary": latest.get("summary") or latest.get("overall_assessment", ""),
        "category_breakdown": latest["category_breakdown"],
        "severity_breakdown": latest["severity_breakdown"],
        "issues": latest["issues"],
        "avg_confidence": average_confidence(latest["issues"]),
        "duplicates_removed": latest.get("duplicates_removed", 0),
        "churn_data": _load_json(_churn_path(repo_name)),
        "commits_analyzed": len(rows),
        "comparison": comparison,
    }


@app.get("/api/results/{repo_name}/history")
def history(repo_name: str):
    rows = load_results(repo_name, DATA_DIR)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No results for '{repo_name}'")
    return [
        {
            "commit_hash": r["commit_hash"],
            "commit_date": r["commit_date"],
            "ai_debt_score": r["ai_debt_score"],
            "issue_count": r["issue_count"],
        }
        for r in rows
    ]


DISSERTATION_RESULTS = Path.home() / "Documents" / "dissertation" / "results"


@app.get("/api/sonar/{repo_name}/history")
def sonar_history(repo_name: str):
    """Return the SonarQube SQALE time series from the dissertation pipeline CSV.

    Always returns 200; callers check the `available` field.
    """
    import csv as _csv

    csv_path = DISSERTATION_RESULTS / f"{repo_name}_results.csv"
    if not csv_path.exists():
        return {"available": False, "data": None}

    rows = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                if row.get("build_status") in ("ANALYSIS_FAILED", "SCAN_FAILED", "CHECKOUT_FAILED"):
                    continue
                sqale = row.get("sqale_index", "")
                if not sqale:
                    continue
                try:
                    sqale_val = int(float(sqale))
                except ValueError:
                    continue
                ncloc = row.get("ncloc", "")
                ncloc_val = int(float(ncloc)) if ncloc else None
                rows.append({
                    "commit_date": row.get("commit_date", ""),
                    "sqale_index": sqale_val,
                    "ncloc": ncloc_val,
                    "build_status": row.get("build_status", ""),
                })
    except Exception as exc:
        logger.warning("sonar_history: failed to read %s: %s", csv_path, exc)
        return {"available": False, "data": None}

    rows.sort(key=lambda r: r["commit_date"])
    return {"available": True, "data": rows}


@app.get("/api/repos")
def repos():
    out = []
    for name in sorted(list_analyzed_repos(DATA_DIR)):
        rows = load_results(name, DATA_DIR)
        if not rows:
            continue
        latest = select_latest(rows)
        out.append({
            "name": name,
            "latest_score": latest["ai_debt_score"],
            "issue_count": latest["issue_count"],
            "last_analysed": latest["commit_date"][:10],
            "model": latest.get("model", ""),
            "provider": provider_from_model(latest.get("model", "")),
            "commit_count": len(rows),
        })
    return out
