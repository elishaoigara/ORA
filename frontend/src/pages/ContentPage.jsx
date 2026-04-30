import { useState, useEffect, useRef, useCallback } from "react";
import {
  createContentDraft, getContentDrafts, updateDraftStatus,
  editDraftText, regenerateDraft, deleteDraft, getContentStats,
} from "../api";

/* ── constants ─────────────────────────────────────────────── */
const TYPES = [
  { value: "post",       label: "General Post",    icon: "◈" },
  { value: "linkedin",   label: "LinkedIn",         icon: "in" },
  { value: "twitter",    label: "Twitter/X Thread", icon: "✕" },
  { value: "instagram",  label: "Instagram",        icon: "◎" },
  { value: "email",      label: "Email",            icon: "✉" },
  { value: "blog",       label: "Blog Post",        icon: "≡" },
  { value: "script",     label: "Video Script",     icon: "▶" },
  { value: "caption",    label: "Caption",          icon: "◻" },
  { value: "newsletter", label: "Newsletter",       icon: "⊡" },
];

const TONES = [
  { value: "professional",  label: "Professional" },
  { value: "casual",        label: "Casual & Friendly" },
  { value: "inspirational", label: "Inspirational" },
  { value: "technical",     label: "Technical / Founder" },
  { value: "humorous",      label: "Humorous" },
  { value: "storytelling",  label: "Storytelling" },
];

const LENGTHS = [
  { value: "short",  label: "Short" },
  { value: "medium", label: "Medium" },
  { value: "long",   label: "Long" },
];

const STATUS_META = {
  draft:    { label: "DRAFT",    color: "var(--text-4)", bg: "var(--bg-3)" },
  approved: { label: "APPROVED", color: "var(--green)",  bg: "rgba(0,255,157,0.08)" },
  sent:     { label: "SENT",     color: "var(--blue)",   bg: "rgba(68,136,255,0.08)" },
  rejected: { label: "REJECTED", color: "var(--red)",    bg: "rgba(255,68,68,0.08)" },
  archived: { label: "ARCHIVED", color: "var(--text-5)", bg: "var(--bg-2)" },
};

function fmtDate(ts) {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleDateString("en-KE", { day: "numeric", month: "short" });
  } catch { return ts.slice(0, 10); }
}

/* ── Toast ─────────────────────────────────────────────────── */
function useToast() {
  const [toast, setToast] = useState(null);
  const t = useRef();
  const show = useCallback((msg, type = "info") => {
    setToast({ msg, type });
    clearTimeout(t.current);
    t.current = setTimeout(() => setToast(null), 3000);
  }, []);
  return { toast, show };
}

/* ═══════════════════════════════════════════════════════════ */
export default function ContentPage() {
  const [tab, setTab]             = useState("generate");
  const [loading, setLoading]     = useState(false);
  const [drafts, setDrafts]       = useState([]);
  const [stats, setStats]         = useState(null);
  const [result, setResult]       = useState(null);   // freshly generated draft
  const [selected, setSelected]   = useState(null);   // draft open in modal
  const [filterStatus, setFilter] = useState("all");
  const [search, setSearch]       = useState("");
  const [editing, setEditing]     = useState(false);
  const [editText, setEditText]   = useState("");
  const [regenModal, setRegenModal] = useState(false);
  const [regenFeedback, setRegenFeedback] = useState("");

  // form
  const [topic, setTopic]   = useState("");
  const [type, setType]     = useState("post");
  const [tone, setTone]     = useState("professional");
  const [length, setLength] = useState("medium");
  const [extraCtx, setExtra] = useState("");
  const [showExtra, setShowExtra] = useState(false);

  const { toast, show: showToast } = useToast();

  /* ── loaders ── */
  const loadDrafts = useCallback(async () => {
    try {
      const data = await getContentDrafts(filterStatus, 30, search);
      setDrafts(Array.isArray(data) ? data : []);
    } catch { setDrafts([]); }
  }, [filterStatus, search]);

  const loadStats = useCallback(async () => {
    try { setStats(await getContentStats()); } catch {}
  }, []);

  useEffect(() => { loadDrafts(); }, [loadDrafts]);
  useEffect(() => { if (tab === "drafts") loadStats(); }, [tab, loadStats]);

  // search debounce
  const searchRef = useRef();
  const handleSearch = (v) => {
    setSearch(v);
    clearTimeout(searchRef.current);
    searchRef.current = setTimeout(() => loadDrafts(), 400);
  };

  /* ── generate ── */
  const generate = async () => {
    if (!topic.trim()) return;
    setLoading(true); setResult(null);
    try {
      const data = await createContentDraft({
        topic: topic.trim(), content_type: type, tone,
        length, extra_context: extraCtx,
      });
      if (data.status === "error") {
        showToast(data.error || "Generation failed", "error");
      } else {
        setResult(data);
        loadDrafts();
        showToast("Draft generated ✓", "success");
      }
    } catch (e) {
      showToast(e.message || "Backend unreachable", "error");
    } finally { setLoading(false); }
  };

  /* ── draft actions ── */
  const changeStatus = async (id, status) => {
    try {
      await updateDraftStatus(id, status);
      showToast(`Marked as ${status}`, "success");
      if (selected?.id === id) setSelected(s => ({ ...s, status }));
      loadDrafts();
    } catch { showToast("Failed to update", "error"); }
  };

  const handleDelete = async (id) => {
    if (!confirm("Delete this draft permanently?")) return;
    try {
      await deleteDraft(id);
      showToast("Deleted", "success");
      if (selected?.id === id) setSelected(null);
      loadDrafts();
    } catch { showToast("Delete failed", "error"); }
  };

  const saveEdit = async () => {
    try {
      await editDraftText(selected.id, editText);
      showToast("Saved ✓", "success");
      setSelected(s => ({ ...s, draft: editText, word_count: editText.split(/\s+/).length }));
      setEditing(false);
      loadDrafts();
    } catch { showToast("Save failed", "error"); }
  };

  const handleRegen = async () => {
    setRegenModal(false);
    setLoading(true);
    try {
      const data = await regenerateDraft(selected.id, regenFeedback);
      if (data.status === "error") { showToast(data.error, "error"); return; }
      showToast("New version generated ✓", "success");
      setSelected(null);
      loadDrafts();
    } catch { showToast("Regeneration failed", "error"); }
    finally { setLoading(false); setRegenFeedback(""); }
  };

  const copy = (text) => {
    navigator.clipboard.writeText(text || "")
      .then(() => showToast("Copied to clipboard ✓", "success"))
      .catch(() => showToast("Copy failed", "error"));
  };

  const openDraft = (d) => {
    setSelected(d); setEditing(false); setEditText(d.draft || "");
  };

  /* ── RENDER ─────────────────────────────────────────────── */
  return (
    <div className="page" style={{ display: "flex", flexDirection: "column", gap: 0, paddingBottom: 48 }}>

      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">CONTENT STUDIO</div>
          <div className="page-subtitle">AI-powered drafts · generate → edit → publish</div>
        </div>
        {stats && (
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            <StatPill label="TOTAL" value={stats.total} />
            <StatPill label="APPROVED" value={stats.by_status?.approved || 0} color="var(--green)" />
            <StatPill label="SENT" value={stats.by_status?.sent || 0} color="var(--blue)" />
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="filter-tabs" style={{ marginBottom: 20 }}>
        <button className={`filter-tab ${tab === "generate" ? "active" : ""}`} onClick={() => setTab("generate")}>
          ✦ GENERATE
        </button>
        <button className={`filter-tab ${tab === "drafts" ? "active" : ""}`} onClick={() => { setTab("drafts"); loadStats(); }}>
          ≡ DRAFTS {drafts.length > 0 && `(${drafts.length})`}
        </button>
      </div>

      {/* ── GENERATE TAB ── */}
      {tab === "generate" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

          {/* LEFT: form */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

            <div className="card">
              <div className="card-header">
                <span className="card-title">WHAT TO WRITE ABOUT</span>
              </div>
              <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <textarea
                  className="textarea"
                  rows={3}
                  placeholder="e.g. Launching ORA v2 — autonomous AI agent for personal productivity"
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                  style={{ width: "100%", resize: "vertical" }}
                />

                {/* Content type */}
                <div>
                  <div className="mono text-xs" style={{ color: "var(--text-4)", letterSpacing: 2, fontSize: 9, marginBottom: 8 }}>CONTENT TYPE</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {TYPES.map(t_ => (
                      <button
                        key={t_.value}
                        onClick={() => setType(t_.value)}
                        style={{
                          fontFamily: "var(--mono)", fontSize: 10, letterSpacing: 1,
                          padding: "5px 11px", borderRadius: 6, cursor: "pointer",
                          border: type === t_.value ? "1px solid var(--green)" : "1px solid var(--border-2)",
                          background: type === t_.value ? "rgba(0,255,157,0.08)" : "transparent",
                          color: type === t_.value ? "var(--green)" : "var(--text-4)",
                          transition: "all 0.12s",
                        }}
                      >
                        {t_.icon} {t_.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Tone */}
                <div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text-4)", letterSpacing: 2, marginBottom: 6 }}>TONE</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {TONES.map(t_ => (
                      <button key={t_.value} onClick={() => setTone(t_.value)}
                        style={{
                          fontFamily: "var(--mono)", fontSize: 9, letterSpacing: 1,
                          padding: "4px 10px", borderRadius: 6, cursor: "pointer",
                          border: tone === t_.value ? "1px solid var(--orange)" : "1px solid var(--border)",
                          background: tone === t_.value ? "var(--orange-dim)" : "transparent",
                          color: tone === t_.value ? "var(--orange)" : "var(--text-5)",
                          transition: "all 0.12s",
                        }}
                      >
                        {t_.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Length */}
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text-4)", letterSpacing: 2, flexShrink: 0 }}>LENGTH</div>
                  {LENGTHS.map(l_ => (
                    <button key={l_.value} onClick={() => setLength(l_.value)}
                      style={{
                        fontFamily: "var(--mono)", fontSize: 9, letterSpacing: 1,
                        padding: "4px 12px", borderRadius: 6, cursor: "pointer",
                        border: length === l_.value ? "1px solid var(--blue)" : "1px solid var(--border)",
                        background: length === l_.value ? "var(--blue-dim)" : "transparent",
                        color: length === l_.value ? "var(--blue)" : "var(--text-5)",
                        transition: "all 0.12s",
                      }}
                    >
                      {l_.label}
                    </button>
                  ))}
                </div>

                {/* Extra context toggle */}
                <div>
                  <button
                    className="btn btn-sm"
                    onClick={() => setShowExtra(x => !x)}
                    style={{ marginBottom: showExtra ? 8 : 0 }}
                  >
                    {showExtra ? "− HIDE" : "+ ADD"} CONTEXT
                  </button>
                  {showExtra && (
                    <textarea
                      className="textarea"
                      rows={3}
                      placeholder="Additional context, talking points, audience, links..."
                      value={extraCtx}
                      onChange={e => setExtra(e.target.value)}
                      style={{ width: "100%", resize: "vertical" }}
                    />
                  )}
                </div>

                <button
                  className="btn btn-green"
                  onClick={generate}
                  disabled={loading || !topic.trim()}
                  style={{ padding: "13px", fontSize: 13, letterSpacing: 2 }}
                >
                  {loading ? "✦ GENERATING..." : "✦ GENERATE DRAFT"}
                </button>
              </div>
            </div>
          </div>

          {/* RIGHT: output */}
          <div>
            {!result && !loading && (
              <div className="card" style={{ height: "100%", minHeight: 320 }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", padding: 48, gap: 10, minHeight: 280 }}>
                  <div style={{ fontSize: 32, opacity: 0.15 }}>✦</div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-5)", letterSpacing: 3 }}>DRAFT WILL APPEAR HERE</div>
                  <div style={{ fontSize: 12, color: "var(--text-5)", textAlign: "center" }}>Fill out the form and click Generate</div>
                </div>
              </div>
            )}

            {loading && (
              <div className="card" style={{ minHeight: 320 }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 48, gap: 16, minHeight: 280 }}>
                  <div style={{ width: 36, height: 36, border: "2px solid var(--border-2)", borderTopColor: "var(--green)", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                  <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--green)", letterSpacing: 3 }}>GENERATING...</div>
                  <div style={{ fontSize: 11, color: "var(--text-5)" }}>GROQ · {type.toUpperCase()} · {tone}</div>
                </div>
              </div>
            )}

            {result && !loading && (
              <div className="card">
                <div className="card-header">
                  <span className="card-title">GENERATED DRAFT</span>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text-5)" }}>
                      {result.word_count}w · {result.char_count}c
                    </span>
                    <button className="btn btn-sm" onClick={() => copy(result.draft)}>⎘ COPY</button>
                    <button className="btn btn-sm btn-green" onClick={() => changeStatus(result.id, "approved")}>✓ APPROVE</button>
                  </div>
                </div>
                <div className="card-body">
                  {/* Type / tone tags */}
                  <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
                    <Tag>{result.type}</Tag>
                    <Tag>{result.tone}</Tag>
                    <Tag>{result.length}</Tag>
                  </div>
                  <div style={{
                    whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.8,
                    background: "rgba(0,0,0,0.25)", padding: "18px 20px",
                    borderRadius: 8, maxHeight: 480, overflowY: "auto",
                    border: "1px solid var(--border)", color: "var(--text-2)",
                  }}>
                    {result.draft}
                  </div>
                  <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
                    <button className="btn btn-sm" onClick={() => openDraft(result)}>⊡ OPEN FULL</button>
                    <button className="btn btn-sm" onClick={() => changeStatus(result.id, "rejected")}>✕ REJECT</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── DRAFTS TAB ── */}
      {tab === "drafts" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Stats row */}
          {stats && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8, marginBottom: 4 }}>
              {Object.entries(STATUS_META).map(([k, m]) => (
                <div key={k} className="card" style={{ border: `1px solid var(--border)`, cursor: "pointer", transition: "border-color 0.15s" }}
                  onClick={() => setFilter(filterStatus === k ? "all" : k)}>
                  <div style={{ padding: "10px 14px", textAlign: "center" }}>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 16, fontWeight: 700, color: m.color }}>
                      {stats.by_status?.[k] || 0}
                    </div>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 8, color: "var(--text-5)", letterSpacing: 2, marginTop: 2 }}>{m.label}</div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Search + filter */}
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <input
              className="input"
              placeholder="Search drafts..."
              value={search}
              onChange={e => handleSearch(e.target.value)}
              style={{ flex: 1 }}
            />
            <div className="filter-tabs">
              {["all", "draft", "approved", "sent", "rejected"].map(s => (
                <button key={s} className={`filter-tab ${filterStatus === s ? "active" : ""}`}
                  onClick={() => setFilter(s)}>
                  {s.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Draft list */}
          <div className="card">
            {drafts.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">✦</div>
                <div className="empty-title">No drafts found</div>
                <div className="empty-body">
                  {search ? "Try a different search" : "Generate your first draft in the Generate tab"}
                </div>
              </div>
            ) : (
              drafts.map((d, i) => (
                <div key={d.id} className="doc-row"
                  style={{ cursor: "pointer", borderBottom: i < drafts.length - 1 ? "1px solid var(--border)" : "none" }}
                  onClick={() => openDraft(d)}>
                  <div className="doc-info" style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                      <span className="doc-name" style={{ flex: 1 }}>{d.title}</span>
                      <StatusBadge status={d.status} />
                    </div>
                    <div className="doc-meta">
                      {d.type} · {d.tone} · {d.word_count || 0}w · {fmtDate(d.ts)}
                      {d.version > 1 && ` · v${d.version}`}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-4)", marginTop: 5, lineHeight: 1.5,
                      overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                      {d.draft}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 5, flexShrink: 0 }}
                    onClick={e => e.stopPropagation()}>
                    <button className="btn btn-sm" onClick={() => copy(d.draft)}>⎘</button>
                    <button className="btn btn-sm btn-red" onClick={() => handleDelete(d.id)}>✕</button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* ── DRAFT MODAL ── */}
      {selected && (
        <div className="modal-overlay" onClick={() => { setSelected(null); setEditing(false); }}>
          <div style={{
            background: "var(--bg-3)", border: "1px solid var(--border-2)",
            borderRadius: "var(--radius-lg)", padding: 24, width: "min(720px, 94vw)",
            maxHeight: "88vh", display: "flex", flexDirection: "column", gap: 14,
            overflowY: "auto", margin: "auto",
          }} onClick={e => e.stopPropagation()}>

            {/* Modal header */}
            <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text-4)", letterSpacing: 3, marginBottom: 4 }}>DRAFT</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)", lineHeight: 1.4 }}>{selected.title}</div>
              </div>
              <StatusBadge status={selected.status} />
              <button className="btn btn-sm" onClick={() => setSelected(null)}>✕</button>
            </div>

            {/* Meta tags */}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <Tag>{selected.type}</Tag>
              <Tag>{selected.tone}</Tag>
              {selected.length && <Tag>{selected.length}</Tag>}
              {selected.word_count > 0 && <Tag color="var(--blue)">{selected.word_count} words</Tag>}
              {selected.char_count > 0 && <Tag>{selected.char_count} chars</Tag>}
            </div>

            {/* Draft text / editor */}
            {editing ? (
              <textarea
                className="textarea"
                value={editText}
                onChange={e => setEditText(e.target.value)}
                style={{ width: "100%", minHeight: 320, resize: "vertical", fontSize: 14, lineHeight: 1.8 }}
                autoFocus
              />
            ) : (
              <div style={{
                whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.85,
                background: "rgba(0,0,0,0.3)", padding: "18px 20px",
                borderRadius: 8, maxHeight: 400, overflowY: "auto",
                border: "1px solid var(--border)", color: "var(--text-2)",
              }}>
                {selected.draft}
              </div>
            )}

            {/* Live word count while editing */}
            {editing && (
              <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text-5)", textAlign: "right" }}>
                {editText.split(/\s+/).filter(Boolean).length} words · {editText.length} chars
              </div>
            )}

            {/* Actions */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", paddingTop: 4, borderTop: "1px solid var(--border)" }}>
              <button className="btn btn-sm btn-green" onClick={() => copy(editing ? editText : selected.draft)}>⎘ COPY</button>

              {!editing ? (
                <button className="btn btn-sm" onClick={() => { setEditing(true); setEditText(selected.draft); }}>✏ EDIT</button>
              ) : (
                <>
                  <button className="btn btn-sm btn-green" onClick={saveEdit}>✓ SAVE</button>
                  <button className="btn btn-sm" onClick={() => setEditing(false)}>✕ CANCEL</button>
                </>
              )}

              {!editing && (
                <button className="btn btn-sm" onClick={() => { setRegenModal(true); }}>↻ REGENERATE</button>
              )}

              {selected.status !== "approved" && (
                <button className="btn btn-sm" style={{ borderColor: "rgba(0,255,157,0.3)", color: "var(--green)" }}
                  onClick={() => changeStatus(selected.id, "approved")}>✓ APPROVE</button>
              )}
              {selected.status !== "sent" && selected.status === "approved" && (
                <button className="btn btn-sm" style={{ borderColor: "rgba(68,136,255,0.3)", color: "var(--blue)" }}
                  onClick={() => changeStatus(selected.id, "sent")}>▶ MARK SENT</button>
              )}
              {selected.status !== "archived" && (
                <button className="btn btn-sm" onClick={() => { changeStatus(selected.id, "archived"); setSelected(null); }}>⊞ ARCHIVE</button>
              )}
              <button className="btn btn-sm btn-red" style={{ marginLeft: "auto" }}
                onClick={() => handleDelete(selected.id)}>✕ DELETE</button>
            </div>
          </div>
        </div>
      )}

      {/* ── REGENERATE FEEDBACK MODAL ── */}
      {regenModal && (
        <div className="modal-overlay" onClick={() => setRegenModal(false)}>
          <div style={{
            background: "var(--bg-3)", border: "1px solid var(--border-2)",
            borderRadius: "var(--radius-lg)", padding: 24, width: "min(480px, 94vw)",
            margin: "auto",
          }} onClick={e => e.stopPropagation()}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text-4)", letterSpacing: 3, marginBottom: 16 }}>REGENERATE DRAFT</div>
            <div style={{ fontSize: 13, color: "var(--text-3)", marginBottom: 12 }}>
              Optional: tell ORA what to improve in the new version.
            </div>
            <textarea
              className="textarea"
              rows={3}
              placeholder="e.g. Make it shorter, more personal, add a CTA..."
              value={regenFeedback}
              onChange={e => setRegenFeedback(e.target.value)}
              style={{ width: "100%", marginBottom: 14 }}
              autoFocus
            />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-green" onClick={handleRegen}>↻ REGENERATE</button>
              <button className="btn" onClick={() => setRegenModal(false)}>CANCEL</button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className="toast" style={{
          borderColor: toast.type === "success" ? "rgba(0,255,157,0.3)"
                     : toast.type === "error"   ? "rgba(255,68,68,0.3)"
                     : "var(--border)",
          color: toast.type === "success" ? "var(--green)"
               : toast.type === "error"   ? "var(--red)"
               : "var(--text-2)",
        }}>
          {toast.msg}
        </div>
      )}

      {/* Spinner keyframe */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

/* ── tiny shared components ──────────────────────────────── */
function Tag({ children, color }) {
  return (
    <span style={{
      fontFamily: "var(--mono)", fontSize: 9, letterSpacing: 1,
      padding: "2px 8px", borderRadius: 4,
      background: color ? `${color}18` : "var(--bg-2)",
      border: `1px solid ${color || "var(--border-2)"}`,
      color: color || "var(--text-4)",
    }}>{children}</span>
  );
}

function StatusBadge({ status }) {
  const m = STATUS_META[status] || STATUS_META.draft;
  return (
    <span style={{
      fontFamily: "var(--mono)", fontSize: 8, letterSpacing: 1.5, fontWeight: 700,
      padding: "2px 7px", borderRadius: 4,
      background: m.bg, color: m.color,
      border: `1px solid ${m.color}44`,
    }}>{m.label}</span>
  );
}

function StatPill({ label, value, color }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontFamily: "var(--mono)", fontSize: 20, fontWeight: 700, color: color || "var(--text-3)", lineHeight: 1 }}>{value}</div>
      <div style={{ fontFamily: "var(--mono)", fontSize: 8, color: "var(--text-5)", letterSpacing: 2, marginTop: 2 }}>{label}</div>
    </div>
  );
}