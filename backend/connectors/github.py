"""
ORA GitHub Connector — Phase 4
Polls your repos every hour for open PRs, issues, recent commits.
Free tier: 5000 requests/hour authenticated.
Uses conditional requests to avoid burning quota when nothing changed.
"""

from __future__ import annotations

import os
import traceback
import time
from typing import Optional

GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")
BASE_URL        = "https://api.github.com"

_cache: dict = {}
CACHE_TTL = 3600  # 1 hour


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _get(path: str, etag_key: Optional[str] = None) -> Optional[dict | list]:
    """
    GET with optional ETag conditional request.
    Returns None if 304 Not Modified (use cache).
    """
    try:
        import requests
        headers = _headers()

        if etag_key and _cache.get(f"etag:{etag_key}"):
            headers["If-None-Match"] = _cache[f"etag:{etag_key}"]

        resp = requests.get(f"{BASE_URL}{path}", headers=headers, timeout=8)

        if resp.status_code == 304:
            return _cache.get(f"data:{etag_key}")

        if resp.status_code == 200:
            if etag := resp.headers.get("ETag"):
                _cache[f"etag:{etag_key}"] = etag
            data = resp.json()
            if etag_key:
                _cache[f"data:{etag_key}"] = data
            return data

    except Exception as e:
        print(f"[GITHUB] GET {path} failed: {e}")
    return None


def get_github_summary() -> dict:
    """
    Lightweight summary for agent context.
    Cached 1 hour — called from gather_context().
    """
    if not GITHUB_USERNAME:
        return {}

    now = time.time()
    cached = _cache.get("summary")
    if cached and now - _cache.get("summary_ts", 0) < CACHE_TTL:
        return cached

    try:
        summary: dict = {
            "open_prs":     0,
            "open_issues":  0,
            "recent_pushes": [],
            "repos":        [],
        }

        # Get user repos (top 10 by last push)
        repos = _get(
            f"/users/{GITHUB_USERNAME}/repos?sort=pushed&per_page=10",
            etag_key="repos"
        )
        if not repos:
            return summary

        summary["repos"] = [r["name"] for r in repos[:5]]

        # Check PRs and issues across repos
        for repo in repos[:5]:
            repo_name = repo["full_name"]

            # Open PRs
            prs = _get(f"/repos/{repo_name}/pulls?state=open&per_page=5",
                       etag_key=f"prs:{repo_name}")
            if prs:
                summary["open_prs"] += len(prs)

            # Open issues (exclude PRs)
            issues = _get(f"/repos/{repo_name}/issues?state=open&per_page=5",
                          etag_key=f"issues:{repo_name}")
            if issues:
                real_issues = [i for i in issues if "pull_request" not in i]
                summary["open_issues"] += len(real_issues)

            # Recent commits
            commits = _get(f"/repos/{repo_name}/commits?per_page=3",
                           etag_key=f"commits:{repo_name}")
            if commits:
                for c in commits[:2]:
                    msg = c.get("commit", {}).get("message", "").split("\n")[0]
                    summary["recent_pushes"].append(
                        f"{repo['name']}: {msg[:60]}"
                    )

        summary["recent_pushes"] = summary["recent_pushes"][:5]

        _cache["summary"]    = summary
        _cache["summary_ts"] = now
        return summary

    except Exception:
        print("[GITHUB] get_github_summary failed:")
        print(traceback.format_exc())
        return {}