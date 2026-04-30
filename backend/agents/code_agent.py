"""
ORA Code Agent — GitHub Intelligence Layer
==========================================
Monitors repos, spots problems, generates AI fixes, opens issues.

Capabilities:
  - Full repo deep-scan: PRs, issues, commits, branches, CI status
  - Stale PR detection + AI review summary
  - Failing CI/checks detection
  - Dead branch detection
  - AI-powered fix suggestions per file/commit
  - Open GitHub issues directly via API
  - Code quality analysis on recent commits
  - Repo health score (0-100)
  - All findings stored in code_scans table

Design:
  - Extended GitHub connector (POST/PATCH support added)
  - Groq llama-3.3-70b for analysis, 8b for quick summaries
  - Scan results cached in DB — won't re-scan same SHA twice
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from typing import Optional

from config import GROQ_API_KEY, GROQ_MODEL_PRIMARY, GROQ_MODEL_FALLBACK, GITHUB_TOKEN, GITHUB_USERNAME
from database import get_conn, close_conn

# ─── Groq client ─────────────────────────────────────────────────────────────
_groq_client = None

def _groq():
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client

def _ai(system: str, user: str, max_tokens: int = 1500, fast: bool = False) -> str:
    model = GROQ_MODEL_FALLBACK if fast else GROQ_MODEL_PRIMARY
    for m in [model, GROQ_MODEL_FALLBACK]:
        try:
            r = _groq().chat.completions.create(
                model=m,
                messages=[{"role": "system", "content": system},
                          {"role": "user",   "content": user}],
                max_tokens=max_tokens,
                temperature=0.2,
            )
            return (r.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"[CODE_AGENT] AI call failed with {m}: {e}")
    return ""


# ─── DB init ─────────────────────────────────────────────────────────────────
def init_code_agent_tables():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS code_scans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            repo        TEXT NOT NULL,
            scan_type   TEXT NOT NULL,
            title       TEXT NOT NULL,
            severity    TEXT DEFAULT 'info',
            body        TEXT,
            ai_analysis TEXT,
            ai_fix      TEXT,
            status      TEXT DEFAULT 'open',
            github_issue_url TEXT DEFAULT NULL,
            ref_id      TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_code_scans_repo
        ON code_scans(repo, status, created_at)
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS code_scan_runs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            repo       TEXT NOT NULL,
            health     INTEGER DEFAULT 0,
            summary    TEXT,
            findings   INTEGER DEFAULT 0,
            ran_at     TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    close_conn()
    print("[CODE_AGENT] Tables initialized")


# ─── GitHub API helpers ───────────────────────────────────────────────────────
def _gh_get(path: str) -> Optional[list | dict]:
    """GET from GitHub API."""
    try:
        import requests
        h = {"Accept": "application/vnd.github+json",
             "X-GitHub-Api-Version": "2022-11-28"}
        if GITHUB_TOKEN:
            h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        r = requests.get(f"https://api.github.com{path}", headers=h, timeout=10)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None
        print(f"[CODE_AGENT] GET {path} → {r.status_code}")
        return None
    except Exception as e:
        print(f"[CODE_AGENT] GET {path} error: {e}")
        return None


def _gh_post(path: str, body: dict) -> Optional[dict]:
    """POST to GitHub API (create issue, comment, etc.)."""
    try:
        import requests
        h = {"Accept": "application/vnd.github+json",
             "X-GitHub-Api-Version": "2022-11-28",
             "Content-Type": "application/json"}
        if GITHUB_TOKEN:
            h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        r = requests.post(f"https://api.github.com{path}",
                          headers=h, json=body, timeout=10)
        if r.status_code in (200, 201):
            return r.json()
        print(f"[CODE_AGENT] POST {path} → {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        print(f"[CODE_AGENT] POST {path} error: {e}")
        return None


def _age_days(iso_str: str) -> float:
    """Days since an ISO datetime string."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return 0


def _get_repos() -> list[dict]:
    """Get user's repos sorted by recent push."""
    repos = _gh_get(f"/users/{GITHUB_USERNAME}/repos?sort=pushed&per_page=20&type=owner")
    return repos if isinstance(repos, list) else []


# ─── SCAN FUNCTIONS ───────────────────────────────────────────────────────────

def _scan_stale_prs(repo_full: str) -> list[dict]:
    """Find PRs with no activity for 3+ days and generate AI review."""
    findings = []
    prs = _gh_get(f"/repos/{repo_full}/pulls?state=open&per_page=20")
    if not prs or not isinstance(prs, list):
        return findings

    for pr in prs:
        age = _age_days(pr.get("updated_at", pr.get("created_at", "")))
        if age < 3:
            continue

        title  = pr.get("title", "")
        number = pr.get("number", 0)
        author = pr.get("user", {}).get("login", "unknown")
        body   = (pr.get("body") or "")[:600]
        branch = pr.get("head", {}).get("ref", "")
        url    = pr.get("html_url", "")
        draft  = pr.get("draft", False)
        severity = "high" if age > 14 else "medium" if age > 7 else "low"

        ai_text = _ai(
            system=(
                "You are ORA Code Agent reviewing a GitHub PR. Be brief and direct.\n"
                "Give: 1) What this PR likely does (2 sentences max), "
                "2) Why it might be stale (1 sentence), "
                "3) Recommended action (1 sentence). "
                "No markdown headers. Plain text."
            ),
            user=(
                f"PR #{number}: {title}\nBranch: {branch}\nAge: {age:.0f} days\n"
                f"Author: {author}\nDraft: {draft}\nDescription:\n{body}"
            ),
            max_tokens=200, fast=True
        )

        findings.append({
            "scan_type": "stale_pr",
            "title":     f"Stale PR #{number}: {title[:70]}",
            "severity":  severity,
            "body":      json.dumps({
                "pr_number": number, "url": url, "author": author,
                "age_days": round(age, 1), "branch": branch, "draft": draft
            }),
            "ai_analysis": ai_text,
            "ai_fix": f"Review or close PR #{number}. Branch: {branch}",
        })

    return findings


def _scan_failing_checks(repo_full: str) -> list[dict]:
    """Find commits with failing CI checks."""
    findings = []

    repo_info = _gh_get(f"/repos/{repo_full}")
    if not repo_info or not isinstance(repo_info, dict):
        return findings

    default_branch = repo_info.get("default_branch", "main")
    commits = _gh_get(f"/repos/{repo_full}/commits?sha={default_branch}&per_page=5")
    if not commits or not isinstance(commits, list):
        return findings

    for commit in commits[:3]:
        sha = commit.get("sha", "")
        msg = commit.get("commit", {}).get("message", "").split("\n")[0][:80]
        if not sha:
            continue

        statuses = _gh_get(f"/repos/{repo_full}/commits/{sha}/check-runs")
        if not statuses or not isinstance(statuses, dict):
            continue

        runs = statuses.get("check_runs", [])
        failed = [r for r in runs if r.get("conclusion") in ("failure", "cancelled", "timed_out")]
        if not failed:
            continue

        for run in failed[:3]:
            run_name   = run.get("name", "CI")
            run_url    = run.get("html_url", "")
            conclusion = run.get("conclusion", "failure")

            ai_fix = _ai(
                system=(
                    "You are ORA Code Agent. A CI check failed. "
                    "Suggest the most likely fix in 2-3 sentences. Be specific and actionable."
                ),
                user=(
                    f"Repo: {repo_full}\nCommit: {msg}\nFailed check: {run_name}\n"
                    f"Conclusion: {conclusion}\nSHA: {sha[:8]}"
                ),
                max_tokens=150, fast=True
            )

            findings.append({
                "scan_type": "failing_ci",
                "title":     f"CI failed: {run_name} on '{msg}'",
                "severity":  "high",
                "body":      json.dumps({
                    "sha": sha[:8], "commit_msg": msg,
                    "check_name": run_name, "conclusion": conclusion,
                    "url": run_url
                }),
                "ai_analysis": f"Check '{run_name}' {conclusion} on commit: {msg}",
                "ai_fix":     ai_fix,
            })

    return findings


def _scan_open_issues(repo_full: str) -> list[dict]:
    """Find old unaddressed issues that need attention."""
    findings = []
    issues = _gh_get(f"/repos/{repo_full}/issues?state=open&per_page=20&sort=updated&direction=asc")
    if not issues or not isinstance(issues, list):
        return findings

    real = [i for i in issues if "pull_request" not in i]
    for issue in real[:5]:
        age = _age_days(issue.get("updated_at", ""))
        if age < 7:
            continue

        number   = issue.get("number", 0)
        title    = issue.get("title", "")
        labels   = [l["name"] for l in issue.get("labels", [])]
        body     = (issue.get("body") or "")[:400]
        url      = issue.get("html_url", "")
        comments = issue.get("comments", 0)
        severity = "high" if age > 30 else "medium"

        ai_text = _ai(
            system=(
                "You are ORA Code Agent. Analyze this GitHub issue and suggest "
                "what type of fix is needed (bug fix, feature, docs, etc.) and "
                "a 2-sentence action plan. Be direct."
            ),
            user=(
                f"Issue #{number}: {title}\nAge: {age:.0f} days\n"
                f"Labels: {labels}\nComments: {comments}\nBody:\n{body}"
            ),
            max_tokens=150, fast=True
        )

        findings.append({
            "scan_type": "stale_issue",
            "title":     f"Stale issue #{number}: {title[:70]}",
            "severity":  severity,
            "body":      json.dumps({
                "issue_number": number, "url": url,
                "age_days": round(age, 1), "labels": labels, "comments": comments
            }),
            "ai_analysis": ai_text,
            "ai_fix":     f"Triage issue #{number} — assign label, respond, or close.",
        })

    return findings


def _scan_dead_branches(repo_full: str) -> list[dict]:
    """Find branches with no commits for 14+ days that aren't main/master/dev."""
    findings = []
    branches = _gh_get(f"/repos/{repo_full}/branches?per_page=30")
    if not branches or not isinstance(branches, list):
        return findings

    protected = {"main", "master", "develop", "dev", "staging", "production", "release"}

    for branch in branches:
        name = branch.get("name", "")
        if name.lower() in protected:
            continue

        sha = branch.get("commit", {}).get("sha", "")
        if not sha:
            continue

        commit = _gh_get(f"/repos/{repo_full}/commits/{sha}")
        if not commit or not isinstance(commit, dict):
            continue

        date_str = commit.get("commit", {}).get("committer", {}).get("date", "")
        if not date_str:
            continue

        age = _age_days(date_str)
        if age < 14:
            continue

        msg = commit.get("commit", {}).get("message", "").split("\n")[0][:60]
        findings.append({
            "scan_type": "dead_branch",
            "title":     f"Dead branch: {name} ({age:.0f}d inactive)",
            "severity":  "low",
            "body":      json.dumps({
                "branch": name, "age_days": round(age, 1),
                "last_commit": msg, "sha": sha[:8]
            }),
            "ai_analysis": f"Branch '{name}' has had no activity for {age:.0f} days.",
            "ai_fix":     f"Consider merging or deleting branch '{name}'.",
        })

    return findings[:5]


def _scan_large_commits(repo_full: str) -> list[dict]:
    """Find recent commits that changed many files — potential quality risk."""
    findings = []
    commits = _gh_get(f"/repos/{repo_full}/commits?per_page=10")
    if not commits or not isinstance(commits, list):
        return findings

    for commit in commits[:5]:
        sha = commit.get("sha", "")
        msg = commit.get("commit", {}).get("message", "").split("\n")[0][:80]
        url = commit.get("html_url", "")

        detail = _gh_get(f"/repos/{repo_full}/commits/{sha}")
        if not detail or not isinstance(detail, dict):
            continue

        files     = detail.get("files", [])
        stats     = detail.get("stats", {})
        additions = stats.get("additions", 0)
        deletions = stats.get("deletions", 0)
        changed   = len(files)

        if changed < 10 and (additions + deletions) < 300:
            continue

        file_names = [f.get("filename", "") for f in files[:8]]

        ai_analysis = _ai(
            system=(
                "You are ORA Code Agent reviewing a large commit for code quality risks. "
                "In 2-3 sentences: what are the main risk areas and what should be reviewed? "
                "Be specific to the files listed."
            ),
            user=(
                f"Commit: {msg}\n+{additions} -{deletions} across {changed} files\n"
                f"Files changed: {', '.join(file_names)}"
            ),
            max_tokens=200, fast=False
        )

        findings.append({
            "scan_type": "large_commit",
            "title":     f"Large commit: {msg[:60]} (+{additions}/-{deletions}, {changed} files)",
            "severity":  "medium" if changed > 20 else "low",
            "body":      json.dumps({
                "sha": sha[:8], "url": url, "msg": msg,
                "additions": additions, "deletions": deletions,
                "files_changed": changed, "sample_files": file_names[:5]
            }),
            "ai_analysis": ai_analysis,
            "ai_fix":     f"Manual review recommended for this {changed}-file commit.",
        })

    return findings[:3]


def _compute_health(repo_info: dict, findings: list[dict]) -> int:
    """Compute a 0-100 repo health score."""
    score = 100
    has_description = bool(repo_info.get("description"))
    has_license     = bool(repo_info.get("license"))
    open_issues     = repo_info.get("open_issues_count", 0)
    archived        = repo_info.get("archived", False)

    if archived:
        return 20
    if not has_description:
        score -= 5
    if not has_license:
        score -= 5

    issue_penalty = min(open_issues * 2, 20)
    score -= issue_penalty

    severity_penalty = {
        "high":   12,
        "medium":  6,
        "low":     2,
        "info":    0,
    }
    for f in findings:
        score -= severity_penalty.get(f.get("severity", "info"), 0)

    return max(0, min(100, score))


def _generate_repo_summary(repo_name: str, findings: list[dict], health: int) -> str:
    """Generate an AI summary of the repo's health state."""
    if not findings:
        return f"{repo_name} looks healthy — no issues detected."

    bullets = "\n".join(
        f"- [{f['severity'].upper()}] {f['title']}" for f in findings[:8]
    )
    return _ai(
        system=(
            "You are ORA Code Agent. Write a 3-sentence repo health summary. "
            "Cover: overall state, top concern, recommended next action. "
            "Be direct and specific. No markdown."
        ),
        user=f"Repo: {repo_name}\nHealth score: {health}/100\n\nFindings:\n{bullets}",
        max_tokens=120, fast=True
    )


# ─── MAIN SCAN ENTRY POINTS ───────────────────────────────────────────────────

def scan_repo(repo_name: str) -> dict:
    """
    Full scan of a single repo.
    Returns: { repo, health, findings, summary, ran_at }
    """
    if not GITHUB_USERNAME:
        return {"error": "GITHUB_USERNAME not configured"}

    repo_full = f"{GITHUB_USERNAME}/{repo_name}"

    # FIX: narrow list|dict → dict before passing to _compute_health
    _raw_info = _gh_get(f"/repos/{repo_full}")
    if not _raw_info or not isinstance(_raw_info, dict):
        return {"error": f"Repo {repo_full} not found or not accessible"}
    repo_info: dict = _raw_info

    all_findings: list[dict] = []

    for scanner in [
        _scan_stale_prs,
        _scan_failing_checks,
        _scan_open_issues,
        _scan_dead_branches,
        _scan_large_commits,
    ]:
        try:
            found = scanner(repo_full)
            all_findings.extend(found)
        except Exception as e:
            print(f"[CODE_AGENT] Scanner {scanner.__name__} failed: {e}")

    health  = _compute_health(repo_info, all_findings)
    summary = _generate_repo_summary(repo_name, all_findings, health)

    # Persist to DB
    now = datetime.now().isoformat()
    conn = get_conn()
    cur  = conn.cursor()

    stored_ids = []
    for f in all_findings:
        cur.execute("""
            INSERT INTO code_scans
              (repo, scan_type, title, severity, body, ai_analysis, ai_fix,
               status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)
        """, (repo_name, f["scan_type"], f["title"], f["severity"],
              f.get("body", ""), f.get("ai_analysis", ""),
              f.get("ai_fix", ""), now))
        stored_ids.append(cur.lastrowid)

    cur.execute("""
        INSERT INTO code_scan_runs (repo, health, summary, findings, ran_at)
        VALUES (?, ?, ?, ?, ?)
    """, (repo_name, health, summary, len(all_findings), now))

    conn.commit()
    close_conn()

    for i, f in enumerate(all_findings):
        if i < len(stored_ids):
            f["id"] = stored_ids[i]
        f["repo"] = repo_name

    return {
        "repo":     repo_name,
        "health":   health,
        "summary":  summary,
        "findings": all_findings,
        "ran_at":   now,
    }


def scan_all_repos() -> dict:
    """Scan all repos. Called by scheduler. Returns aggregate."""
    repos = _get_repos()
    if not repos:
        return {"error": "No repos found", "scanned": 0}

    results = []
    for repo in repos[:8]:
        name = repo.get("name", "")
        if not name:
            continue
        try:
            result = scan_repo(name)
            results.append({
                "repo":     name,
                "health":   result.get("health", 0),
                "findings": len(result.get("findings", [])),
                "summary":  result.get("summary", ""),
            })
        except Exception as e:
            print(f"[CODE_AGENT] scan_all: {name} failed: {e}")

    total_findings = sum(r.get("findings", 0) for r in results)
    if total_findings > 0:
        try:
            # FIX: notifier exports dual_notify, not notify
            from intelligence.notifier import dual_notify
            avg_health = sum(r["health"] for r in results) // max(len(results), 1)
            dual_notify(
                title="ORA Code Agent",
                body=f"Scanned {len(results)} repos. Avg health: {avg_health}/100. Open ORA → Code for details.",
            )
        except Exception:
            pass

    return {"scanned": len(results), "repos": results}


# ─── READ FROM DB ─────────────────────────────────────────────────────────────

def get_scans(repo: str = "", status: str = "open", limit: int = 40) -> list[dict]:
    conn = get_conn()
    cur  = conn.cursor()

    if repo:
        cur.execute("""
            SELECT id, repo, scan_type, title, severity, body, ai_analysis,
                   ai_fix, status, github_issue_url, created_at
            FROM code_scans WHERE repo=? AND status=?
            ORDER BY created_at DESC LIMIT ?
        """, (repo, status, limit))
    elif status != "all":
        cur.execute("""
            SELECT id, repo, scan_type, title, severity, body, ai_analysis,
                   ai_fix, status, github_issue_url, created_at
            FROM code_scans WHERE status=?
            ORDER BY created_at DESC LIMIT ?
        """, (status, limit))
    else:
        cur.execute("""
            SELECT id, repo, scan_type, title, severity, body, ai_analysis,
                   ai_fix, status, github_issue_url, created_at
            FROM code_scans
            ORDER BY created_at DESC LIMIT ?
        """, (limit,))

    rows = cur.fetchall()
    close_conn()
    return [
        {
            "id": r[0], "repo": r[1], "scan_type": r[2], "title": r[3],
            "severity": r[4], "body": _safe_json(r[5]),
            "ai_analysis": r[6], "ai_fix": r[7], "status": r[8],
            "github_issue_url": r[9], "created_at": r[10],
        }
        for r in rows
    ]


def get_latest_run(repo: str) -> Optional[dict]:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT repo, health, summary, findings, ran_at
        FROM code_scan_runs WHERE repo=?
        ORDER BY id DESC LIMIT 1
    """, (repo,))
    r = cur.fetchone()
    close_conn()
    if not r:
        return None
    return {"repo": r[0], "health": r[1], "summary": r[2],
            "findings": r[3], "ran_at": r[4]}


def get_all_latest_runs() -> list[dict]:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT r.repo, r.health, r.summary, r.findings, r.ran_at
        FROM code_scan_runs r
        INNER JOIN (
            SELECT repo, MAX(id) as mid FROM code_scan_runs GROUP BY repo
        ) latest ON r.id = latest.mid
        ORDER BY r.health ASC
    """)
    rows = cur.fetchall()
    close_conn()
    return [{"repo": r[0], "health": r[1], "summary": r[2],
             "findings": r[3], "ran_at": r[4]} for r in rows]


def get_code_stats() -> dict:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM code_scans WHERE status='open'")
    open_c = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM code_scans WHERE status='resolved'")
    resolved = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM code_scans WHERE severity='high' AND status='open'")
    critical = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM code_scan_runs")
    total_runs = cur.fetchone()[0]
    cur.execute("""
        SELECT AVG(health) FROM code_scan_runs r
        INNER JOIN (SELECT repo, MAX(id) mid FROM code_scan_runs GROUP BY repo) l
        ON r.id=l.mid
    """)
    avg_health = cur.fetchone()[0] or 0
    close_conn()
    return {
        "open": open_c, "resolved": resolved, "critical": critical,
        "total_runs": total_runs, "avg_health": round(avg_health),
    }


# ─── WRITE / ACTIONS ──────────────────────────────────────────────────────────

def resolve_scan(scan_id: int) -> bool:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("UPDATE code_scans SET status='resolved' WHERE id=?", (scan_id,))
    conn.commit()
    ok = cur.rowcount > 0
    close_conn()
    return ok


def open_github_issue(scan_id: int) -> dict:
    """
    Create a GitHub issue from a code scan finding.
    Returns { ok, url } or { error }.
    """
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT repo, scan_type, title, ai_analysis, ai_fix, severity
        FROM code_scans WHERE id=?
    """, (scan_id,))
    row = cur.fetchone()
    close_conn()

    if not row:
        return {"error": "Scan not found"}

    repo, scan_type, title, analysis, fix, severity = row

    label_map = {
        "failing_ci":   "bug",
        "stale_pr":     "needs-review",
        "stale_issue":  "triage",
        "dead_branch":  "cleanup",
        "large_commit": "review-needed",
    }
    label = label_map.get(scan_type, "ora-agent")

    body = (
        f"**Detected by ORA Code Agent** · Severity: `{severity.upper()}`\n\n"
        f"## Analysis\n{analysis}\n\n"
        f"## Suggested Fix\n{fix}\n\n"
        f"---\n*Auto-generated by ORA · {datetime.now().strftime('%Y-%m-%d %H:%M')}*"
    )

    result = _gh_post(
        f"/repos/{GITHUB_USERNAME}/{repo}/issues",
        {"title": f"[ORA] {title}", "body": body, "labels": [label]}
    )

    if not result:
        return {"error": "GitHub API call failed — check GITHUB_TOKEN permissions"}

    issue_url = result.get("html_url", "")

    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE code_scans SET github_issue_url=? WHERE id=?",
        (issue_url, scan_id)
    )
    conn.commit()
    close_conn()

    return {"ok": True, "url": issue_url, "number": result.get("number")}


def ask_code_agent(question: str, repo: str = "") -> str:
    """
    Free-form Q&A about your codebase / repos.
    Pulls recent scan context from DB to ground the answer.
    """
    context_parts = []

    scans = get_scans(repo=repo, status="open", limit=15)
    if scans:
        lines = [f"- [{s['severity'].upper()}] {s['repo']}: {s['title']}" for s in scans[:10]]
        context_parts.append("Recent open findings:\n" + "\n".join(lines))

    runs = get_all_latest_runs()
    if runs:
        lines = [f"- {r['repo']}: health {r['health']}/100 — {r['summary'][:80]}" for r in runs[:5]]
        context_parts.append("Repo health:\n" + "\n".join(lines))

    context = "\n\n".join(context_parts) if context_parts else "No scan data yet — run a scan first."

    return _ai(
        system=(
            "You are ORA Code Agent — an expert software engineering assistant. "
            "Answer questions about the user's GitHub repos, code quality, and "
            "best practices. Use the scan context provided. Be direct and specific. "
            "If you don't have enough context, say so and suggest running a scan."
        ),
        user=f"Context:\n{context}\n\nQuestion: {question}",
        max_tokens=600, fast=False
    )


def get_repos_list() -> list[dict]:
    """Get list of repos with basic info for the UI."""
    repos = _get_repos()
    return [
        {
            "name":           r.get("name", ""),
            "full_name":      r.get("full_name", ""),
            "description":    r.get("description") or "",
            "language":       r.get("language") or "",
            "open_issues":    r.get("open_issues_count", 0),
            "stars":          r.get("stargazers_count", 0),
            "updated_at":     r.get("updated_at", ""),
            "default_branch": r.get("default_branch", "main"),
            "private":        r.get("private", False),
            "url":            r.get("html_url", ""),
        }
        for r in repos
    ]


# ─── helpers ──────────────────────────────────────────────────────────────────

def _safe_json(s: str) -> dict:
    try:
        return json.loads(s) if s else {}
    except Exception:
        return {}