"""
ORA Code Agent API Routes
=========================
Mount with: app.include_router(code_router)
Prefix: /api/code
"""

from __future__ import annotations

import traceback
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/code", tags=["code-agent"])


# ─── Pydantic models ──────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    repo: str = ""


# ─── Stats & repo list ────────────────────────────────────────────────────────

@router.get("/stats")
def code_stats():
    """Aggregate stats: open findings, resolved, critical, avg health."""
    try:
        from agents.code_agent import get_code_stats
        return get_code_stats()
    except Exception:
        print(traceback.format_exc())
        return {"open": 0, "resolved": 0, "critical": 0, "total_runs": 0, "avg_health": 0}


@router.get("/repos")
def list_repos():
    """List GitHub repos with basic metadata."""
    try:
        from agents.code_agent import get_repos_list
        return get_repos_list()
    except Exception:
        print(traceback.format_exc())
        return []


@router.get("/runs")
def all_runs():
    """Latest scan run per repo (health score + summary)."""
    try:
        from agents.code_agent import get_all_latest_runs
        return get_all_latest_runs()
    except Exception:
        print(traceback.format_exc())
        return []


@router.get("/runs/{repo}")
def repo_run(repo: str):
    """Latest scan run for a specific repo."""
    try:
        from agents.code_agent import get_latest_run
        result = get_latest_run(repo)
        if not result:
            raise HTTPException(404, "No scan found for this repo")
        return result
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Failed to fetch run")


# ─── Findings ────────────────────────────────────────────────────────────────

@router.get("/scans")
def list_scans(repo: str = "", status: str = "open", limit: int = 40):
    """List scan findings, optionally filtered by repo and status."""
    try:
        from agents.code_agent import get_scans
        return get_scans(repo=repo, status=status, limit=limit)
    except Exception:
        print(traceback.format_exc())
        return []


@router.post("/scans/{scan_id}/resolve")
def resolve_finding(scan_id: int):
    """Mark a finding as resolved."""
    try:
        from agents.code_agent import resolve_scan
        ok = resolve_scan(scan_id)
        if not ok:
            raise HTTPException(404, "Scan not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Resolve failed")


@router.post("/scans/{scan_id}/issue")
def create_github_issue(scan_id: int):
    """Open a GitHub issue from a scan finding."""
    try:
        from agents.code_agent import open_github_issue
        result = open_github_issue(scan_id)
        if "error" in result:
            raise HTTPException(400, result["error"])
        return result
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Issue creation failed")


# ─── Scan triggers ────────────────────────────────────────────────────────────

def _do_scan_repo(repo: str):
    try:
        from agents.code_agent import scan_repo
        scan_repo(repo)
    except Exception:
        print(f"[CODE_AGENT] Background scan failed: {traceback.format_exc()}")


def _do_scan_all():
    try:
        from agents.code_agent import scan_all_repos
        scan_all_repos()
    except Exception:
        print(f"[CODE_AGENT] Background scan-all failed: {traceback.format_exc()}")


@router.post("/scan/{repo}")
def trigger_repo_scan(repo: str, background_tasks: BackgroundTasks):
    """Trigger a full scan for a single repo (runs in background)."""
    background_tasks.add_task(_do_scan_repo, repo)
    return {"status": "scan started", "repo": repo}


@router.post("/scan")
def trigger_scan_all(background_tasks: BackgroundTasks):
    """Trigger a scan across all repos (runs in background)."""
    background_tasks.add_task(_do_scan_all)
    return {"status": "scan started", "repos": "all"}


# ─── Synchronous scan (returns results immediately — use for small repos) ─────

@router.post("/scan/{repo}/sync")
def trigger_repo_scan_sync(repo: str):
    """
    Synchronous scan — waits for results and returns them.
    Can take 10-30s depending on repo size.
    """
    try:
        from agents.code_agent import scan_repo
        result = scan_repo(repo)
        if "error" in result:
            raise HTTPException(400, result["error"])
        return result
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Scan failed")


# ─── AI Q&A ───────────────────────────────────────────────────────────────────

@router.post("/ask")
def ask_agent(payload: AskRequest):
    """Free-form Q&A grounded in scan data."""
    try:
        from agents.code_agent import ask_code_agent
        answer = ask_code_agent(payload.question, repo=payload.repo)
        return {"answer": answer}
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Ask failed")
