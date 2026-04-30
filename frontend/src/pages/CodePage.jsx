import { useState, useEffect, useCallback } from "react";
import {
  getCodeStats, getCodeRepos, getCodeRuns, getCodeScans,
  resolveCodeScan, openCodeIssue, scanRepo, askCodeAgent,
} from "../api";

/* ── constants ──────────────────────────────────────────────── */
const SCAN_TYPES = {
  stale_pr:    { label: "Stale PR",       icon: "⌀" },
  failing_ci:  { label: "Failing CI",     icon: "✕" },
  stale_issue: { label: "Stale Issue",    icon: "△" },
  dead_branch: { label: "Dead Branch",    icon: "⊘" },
  large_commit:{ label: "Large Commit",   icon: "◈" },
};

const SEV_META = {
  high:   { color: "var(--red)",    bg: "rgba(255,68,68,0.08)",   label: "HIGH"   },
  medium: { color: "var(--yellow)", bg: "rgba(255,180,0,0.08)",   label: "MED"    },
  low:    { color: "var(--blue)",   bg: "rgba(68,136,255,0.08)",  label: "LOW"    },
  info:   { color: "var(--text-4)", bg: "var(--bg-3)",            label: "INFO"   },
};

const HEALTH_COLOR = (h) =>
  h >= 80 ? "var(--green)" : h >= 50 ? "var(--yellow)" : "var(--red)";

function fmtAge(ts) {
  if (!ts) return "";
  try {
    const diff = (Date.now() - new Date(ts).getTime()) / 1000;
    if (diff < 3600)   return `${Math.round(diff / 60)}m ago`;
    if (diff < 86400)  return `${Math.round(diff / 3600)}h ago`;
    return `${Math.round(diff / 86400)}d ago`;
  } catch { return ""; }
}

/* ── Toast ──────────────────────────────────────────────────── */
function Toast({ msg, type, onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3200);
    return () => clearTimeout(t);
  }, [onDone]);
  const bg = type === "error" ? "var(--red)" : "var(--green)";
  return (
    <div style={{
      position: "fixed", bottom: 28, right: 28, zIndex: 9999,
      background: bg, color: "#fff", padding: "10px 18px",
      borderRadius: 6, fontSize: 13, fontFamily: "monospace",
      boxShadow: "0 4px 16px rgba(0,0,0,0.4)", maxWidth: 340,
    }}>{msg}</div>
  );
}

/* ── Health Ring ────────────────────────────────────────────── */
function HealthRing({ value, size = 56 }) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const fill = circ - (circ * value) / 100;
  const color = HEALTH_COLOR(value);
  return (
    <svg width={size} height={size} style={{ display: "block" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none"
        stroke="var(--bg-3)" strokeWidth={4} />
      <circle cx={size/2} cy={size/2} r={r} fill="none"
        stroke={color} strokeWidth={4}
        strokeDasharray={circ} strokeDashoffset={fill}
        strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`} />
      <text x={size/2} y={size/2 + 4}
        textAnchor="middle" fill={color}
        fontSize={12} fontFamily="monospace" fontWeight="bold">
        {value}
      </text>
    </svg>
  );
}

/* ── Scan Card ──────────────────────────────────────────────── */
function ScanCard({ scan, onResolve, onIssue, actionLoading }) {
  const [expanded, setExpanded] = useState(false);
  const sev  = SEV_META[scan.severity] || SEV_META.info;
  const type = SCAN_TYPES[scan.scan_type] || { label: scan.scan_type, icon: "◻" };

  return (
    <div style={{
      background: "var(--bg-2)", border: "1px solid var(--border)",
      borderLeft: `3px solid ${sev.color}`, borderRadius: 6,
      padding: "12px 14px", marginBottom: 8,
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <span style={{ fontSize: 16, lineHeight: 1, marginTop: 2 }}>{type.icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{
              fontSize: 10, fontFamily: "monospace", fontWeight: "bold",
              color: sev.color, background: sev.bg,
              padding: "1px 6px", borderRadius: 3,
            }}>{sev.label}</span>
            <span style={{
              fontSize: 10, fontFamily: "monospace", color: "var(--text-4)",
              background: "var(--bg-3)", padding: "1px 6px", borderRadius: 3,
            }}>{type.label}</span>
            <span style={{ fontSize: 10, color: "var(--text-5)", fontFamily: "monospace" }}>
              {scan.repo} · {fmtAge(scan.created_at)}
            </span>
          </div>
          <div style={{
            fontSize: 13, color: "var(--text-2)", marginTop: 4,
            fontFamily: "monospace", lineHeight: 1.4,
          }}>{scan.title}</div>

          {expanded && (
            <div style={{ marginTop: 10 }}>
              {scan.ai_analysis && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 10, color: "var(--text-5)", fontFamily: "monospace", marginBottom: 3 }}>
                    AI ANALYSIS
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-3)", lineHeight: 1.5 }}>
                    {scan.ai_analysis}
                  </div>
                </div>
              )}
              {scan.ai_fix && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 10, color: "var(--text-5)", fontFamily: "monospace", marginBottom: 3 }}>
                    SUGGESTED FIX
                  </div>
                  <div style={{ fontSize: 12, color: "var(--green)", lineHeight: 1.5 }}>
                    {scan.ai_fix}
                  </div>
                </div>
              )}
              {scan.github_issue_url && (
                <a href={scan.github_issue_url} target="_blank" rel="noreferrer"
                  style={{ fontSize: 11, color: "var(--blue)", fontFamily: "monospace" }}>
                  ↗ View GitHub Issue
                </a>
              )}
            </div>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 5, flexShrink: 0 }}>
          <button onClick={() => setExpanded(v => !v)} style={btnStyle("var(--bg-3)")}>
            {expanded ? "▲" : "▼"}
          </button>
          {scan.status === "open" && (
            <>
              <button
                disabled={actionLoading === `resolve-${scan.id}`}
                onClick={() => onResolve(scan.id)}
                style={btnStyle("var(--bg-3)", "var(--green)")}
                title="Mark resolved"
              >✓</button>
              {!scan.github_issue_url && (
                <button
                  disabled={actionLoading === `issue-${scan.id}`}
                  onClick={() => onIssue(scan.id)}
                  style={btnStyle("var(--bg-3)", "var(--blue)")}
                  title="Open GitHub issue"
                >{actionLoading === `issue-${scan.id}` ? "…" : "⊕"}</button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function btnStyle(bg, color = "var(--text-3)") {
  return {
    background: bg, border: "1px solid var(--border)", color,
    borderRadius: 4, padding: "3px 7px", fontSize: 11,
    fontFamily: "monospace", cursor: "pointer", lineHeight: 1.2,
  };
}

/* ── Repo Row ────────────────────────────────────────────────── */
function RepoRow({ repo, run, onScan, scanning }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "10px 14px", background: "var(--bg-2)",
      border: "1px solid var(--border)", borderRadius: 6, marginBottom: 6,
    }}>
      {run ? <HealthRing value={run.health} size={48} /> :
        <div style={{ width: 48, height: 48, display: "flex", alignItems: "center",
          justifyContent: "center", color: "var(--text-5)", fontSize: 11 }}>—</div>
      }
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontFamily: "monospace", fontSize: 13, color: "var(--text-1)", fontWeight: "bold" }}>
            {repo.name}
          </span>
          {repo.private && (
            <span style={{ fontSize: 9, color: "var(--text-5)", background: "var(--bg-3)",
              padding: "1px 5px", borderRadius: 3, fontFamily: "monospace" }}>PRIVATE</span>
          )}
          {repo.language && (
            <span style={{ fontSize: 9, color: "var(--blue)", background: "rgba(68,136,255,0.08)",
              padding: "1px 5px", borderRadius: 3, fontFamily: "monospace" }}>{repo.language}</span>
          )}
        </div>
        {run?.summary ? (
          <div style={{ fontSize: 11, color: "var(--text-4)", marginTop: 3, lineHeight: 1.4 }}>
            {run.summary.slice(0, 120)}{run.summary.length > 120 ? "…" : ""}
          </div>
        ) : (
          <div style={{ fontSize: 11, color: "var(--text-5)", marginTop: 3 }}>Not scanned yet</div>
        )}
        {run && (
          <div style={{ fontSize: 10, color: "var(--text-5)", fontFamily: "monospace", marginTop: 2 }}>
            {run.findings} finding{run.findings !== 1 ? "s" : ""} · {fmtAge(run.ran_at)}
          </div>
        )}
      </div>
      <button
        onClick={() => onScan(repo.name)}
        disabled={scanning === repo.name}
        style={{
          ...btnStyle("var(--bg-3)", scanning === repo.name ? "var(--text-5)" : "var(--text-2)"),
          padding: "5px 12px", fontSize: 11,
        }}
      >
        {scanning === repo.name ? "SCANNING…" : "SCAN"}
      </button>
    </div>
  );
}

/* ── Main Page ───────────────────────────────────────────────── */
export default function CodePage() {
  const [tab, setTab]           = useState("overview");   // overview | findings | ask
  const [stats, setStats]       = useState(null);
  const [repos, setRepos]       = useState([]);
  const [runs, setRuns]         = useState([]);
  const [scans, setScans]       = useState([]);
  const [scanFilter, setScanFilter] = useState({ repo: "", status: "open" });
  const [loading, setLoading]   = useState(false);
  const [scanning, setScanning] = useState("");           // repo name being scanned
  const [actionLoading, setActionLoading] = useState(""); // "resolve-ID" | "issue-ID"
  const [toast, setToast]       = useState(null);
  const [askQ, setAskQ]         = useState("");
  const [askRepo, setAskRepo]   = useState("");
  const [askAnswer, setAskAnswer] = useState("");
  const [askLoading, setAskLoading] = useState(false);

  const showToast = (msg, type = "ok") => setToast({ msg, type });

  const loadStats = useCallback(async () => {
    try { setStats(await getCodeStats()); } catch {}
  }, []);

  const loadRepos = useCallback(async () => {
    try {
      const [r, ru] = await Promise.all([getCodeRepos(), getCodeRuns()]);
      setRepos(Array.isArray(r) ? r : []);
      setRuns(Array.isArray(ru) ? ru : []);
    } catch {}
  }, []);

  const loadScans = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getCodeScans(scanFilter.repo, scanFilter.status, 60);
      setScans(Array.isArray(data) ? data : []);
    } catch { setScans([]); }
    finally { setLoading(false); }
  }, [scanFilter]);

  useEffect(() => { loadStats(); loadRepos(); }, [loadStats, loadRepos]);
  useEffect(() => { if (tab === "findings") loadScans(); }, [tab, loadScans]);

  const handleScan = async (repoName) => {
    setScanning(repoName);
    try {
      const result = await scanRepo(repoName);
      showToast(`Scanned ${repoName}: health ${result.health}/100, ${result.findings?.length || 0} findings`);
      loadStats(); loadRepos();
    } catch (e) {
      showToast(`Scan failed: ${e.message}`, "error");
    } finally { setScanning(""); }
  };

  const handleResolve = async (id) => {
    setActionLoading(`resolve-${id}`);
    try {
      await resolveCodeScan(id);
      setScans(s => s.filter(x => x.id !== id));
      loadStats();
      showToast("Finding resolved");
    } catch { showToast("Resolve failed", "error"); }
    finally { setActionLoading(""); }
  };

  const handleIssue = async (id) => {
    setActionLoading(`issue-${id}`);
    try {
      const r = await openCodeIssue(id);
      showToast(`Issue opened: #${r.number}`);
      setScans(s => s.map(x => x.id === id ? { ...x, github_issue_url: r.url } : x));
    } catch (e) { showToast(`Issue failed: ${e.message}`, "error"); }
    finally { setActionLoading(""); }
  };

  const handleAsk = async () => {
    if (!askQ.trim()) return;
    setAskLoading(true);
    setAskAnswer("");
    try {
      const r = await askCodeAgent(askQ, askRepo);
      setAskAnswer(r.answer || "No answer.");
    } catch (e) { setAskAnswer(`Error: ${e.message}`); }
    finally { setAskLoading(false); }
  };

  const runMap = Object.fromEntries(runs.map(r => [r.repo, r]));
  const highCount = stats?.critical || 0;
  const avgHealth = stats?.avg_health || 0;

  return (
    <div style={{ padding: "24px 28px", maxWidth: 900, margin: "0 auto" }}>
      {toast && <Toast msg={toast.msg} type={toast.type} onDone={() => setToast(null)} />}

      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, color: "var(--text-5)", fontFamily: "monospace", letterSpacing: 2, marginBottom: 4 }}>
            ORA / CODE AGENT
          </div>
          <h1 style={{ fontSize: 22, color: "var(--text-1)", fontFamily: "monospace", margin: 0 }}>
            Code Intelligence
          </h1>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {["overview", "findings", "ask"].map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              background: tab === t ? "var(--accent)" : "var(--bg-2)",
              color: tab === t ? "#000" : "var(--text-3)",
              border: "1px solid var(--border)", borderRadius: 5,
              padding: "6px 14px", fontFamily: "monospace", fontSize: 11,
              cursor: "pointer", textTransform: "uppercase", letterSpacing: 1,
            }}>{t}</button>
          ))}
        </div>
      </div>

      {/* ── Stat bar ── */}
      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 24 }}>
          {[
            { label: "OPEN FINDINGS",  value: stats.open,      color: "var(--text-1)" },
            { label: "CRITICAL",       value: highCount,       color: highCount > 0 ? "var(--red)" : "var(--text-1)" },
            { label: "RESOLVED",       value: stats.resolved,  color: "var(--green)" },
            { label: "AVG HEALTH",     value: `${avgHealth}/100`, color: HEALTH_COLOR(avgHealth) },
          ].map(s => (
            <div key={s.label} style={{
              background: "var(--bg-2)", border: "1px solid var(--border)",
              borderRadius: 6, padding: "12px 14px",
            }}>
              <div style={{ fontSize: 9, color: "var(--text-5)", fontFamily: "monospace", letterSpacing: 1, marginBottom: 4 }}>
                {s.label}
              </div>
              <div style={{ fontSize: 22, fontFamily: "monospace", fontWeight: "bold", color: s.color }}>
                {s.value}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ══ OVERVIEW TAB ══ */}
      {tab === "overview" && (
        <div>
          <div style={{ fontSize: 11, color: "var(--text-5)", fontFamily: "monospace",
            letterSpacing: 2, marginBottom: 12 }}>REPOSITORIES</div>
          {repos.length === 0 ? (
            <div style={{ color: "var(--text-5)", fontSize: 13, fontFamily: "monospace", padding: 20, textAlign: "center" }}>
              No repos found — check GITHUB_USERNAME in config.
            </div>
          ) : (
            repos.map(r => (
              <RepoRow key={r.name} repo={r} run={runMap[r.name]}
                onScan={handleScan} scanning={scanning} />
            ))
          )}
        </div>
      )}

      {/* ══ FINDINGS TAB ══ */}
      {tab === "findings" && (
        <div>
          {/* Filters */}
          <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
            <select
              value={scanFilter.repo}
              onChange={e => setScanFilter(f => ({ ...f, repo: e.target.value }))}
              style={selectStyle}
            >
              <option value="">All repos</option>
              {repos.map(r => <option key={r.name} value={r.name}>{r.name}</option>)}
            </select>
            <select
              value={scanFilter.status}
              onChange={e => setScanFilter(f => ({ ...f, status: e.target.value }))}
              style={selectStyle}
            >
              <option value="open">Open</option>
              <option value="resolved">Resolved</option>
              <option value="all">All</option>
            </select>
            <button onClick={loadScans} style={{
              ...btnStyle("var(--bg-2)"), padding: "6px 14px", fontSize: 11
            }}>↻ REFRESH</button>
          </div>

          {loading ? (
            <div style={{ color: "var(--text-5)", fontFamily: "monospace", fontSize: 12, padding: 20 }}>
              Loading findings…
            </div>
          ) : scans.length === 0 ? (
            <div style={{ color: "var(--text-5)", fontFamily: "monospace", fontSize: 12, padding: 20, textAlign: "center" }}>
              No findings — run a scan from the Overview tab.
            </div>
          ) : (
            scans.map(s => (
              <ScanCard key={s.id} scan={s}
                onResolve={handleResolve} onIssue={handleIssue}
                actionLoading={actionLoading} />
            ))
          )}
        </div>
      )}

      {/* ══ ASK TAB ══ */}
      {tab === "ask" && (
        <div>
          <div style={{ fontSize: 11, color: "var(--text-5)", fontFamily: "monospace",
            letterSpacing: 2, marginBottom: 12 }}>ASK ABOUT YOUR CODEBASE</div>

          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <select value={askRepo} onChange={e => setAskRepo(e.target.value)} style={selectStyle}>
              <option value="">All repos</option>
              {repos.map(r => <option key={r.name} value={r.name}>{r.name}</option>)}
            </select>
          </div>

          <textarea
            value={askQ}
            onChange={e => setAskQ(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleAsk())}
            placeholder="e.g. What are my biggest code quality risks? / Which repo needs attention most?"
            style={{
              width: "100%", background: "var(--bg-2)", border: "1px solid var(--border)",
              borderRadius: 6, color: "var(--text-2)", fontFamily: "monospace", fontSize: 13,
              padding: "12px 14px", resize: "vertical", minHeight: 80,
              outline: "none", boxSizing: "border-box",
            }}
          />
          <button
            onClick={handleAsk}
            disabled={askLoading || !askQ.trim()}
            style={{
              marginTop: 8, background: "var(--accent)", color: "#000",
              border: "none", borderRadius: 5, padding: "8px 20px",
              fontFamily: "monospace", fontSize: 12, fontWeight: "bold",
              cursor: askLoading ? "not-allowed" : "pointer", letterSpacing: 1,
            }}
          >{askLoading ? "THINKING…" : "ASK AGENT"}</button>

          {askAnswer && (
            <div style={{
              marginTop: 16, background: "var(--bg-2)", border: "1px solid var(--border)",
              borderLeft: "3px solid var(--accent)", borderRadius: 6,
              padding: "14px 16px", fontSize: 13, color: "var(--text-2)",
              fontFamily: "monospace", lineHeight: 1.6, whiteSpace: "pre-wrap",
            }}>{askAnswer}</div>
          )}

          {/* Canned questions */}
          <div style={{ marginTop: 20 }}>
            <div style={{ fontSize: 10, color: "var(--text-5)", fontFamily: "monospace",
              letterSpacing: 2, marginBottom: 8 }}>QUICK QUESTIONS</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {[
                "Which repo has the worst health?",
                "What are my open high-severity findings?",
                "Are there any failing CI checks?",
                "Which branches should I clean up?",
                "Summarize my stale PRs",
              ].map(q => (
                <button key={q} onClick={() => { setAskQ(q); }}
                  style={{
                    background: "var(--bg-2)", border: "1px solid var(--border)",
                    color: "var(--text-4)", borderRadius: 4, padding: "5px 10px",
                    fontFamily: "monospace", fontSize: 11, cursor: "pointer",
                  }}>{q}</button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const selectStyle = {
  background: "var(--bg-2)", border: "1px solid var(--border)",
  color: "var(--text-2)", borderRadius: 5, padding: "6px 10px",
  fontFamily: "monospace", fontSize: 11, cursor: "pointer",
};
