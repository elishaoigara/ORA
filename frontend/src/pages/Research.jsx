import { useState, useEffect, useRef } from "react";
import BASE_URL from "../api";
import "./research.css";

// ─── API helpers ──────────────────────────────────────────────────────────────
const R_BASE = `${BASE_URL}/api/research`;

async function rApi(method, path, body = null, timeout = 90000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeout);
  try {
    const opts = {
      method,
      headers: { "Content-Type": "application/json" },
      signal: ctrl.signal,
    };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(`${R_BASE}${path}`, opts);
    clearTimeout(t);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  } catch (e) {
    clearTimeout(t);
    throw e;
  }
}

async function rUpload(fd, timeout = 120000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeout);
  try {
    const res = await fetch(`${R_BASE}/upload`, {
      method: "POST",
      body: fd,
      signal: ctrl.signal,
    });
    clearTimeout(t);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  } catch (e) {
    clearTimeout(t);
    throw e;
  }
}

// ─── Markdown renderer ────────────────────────────────────────────────────────
function renderMd(text = "") {
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>")
    .replace(/^\[Source: (.+?)\]/gm, '<span class="r-citation">[SRC: $1]</span>')
    .replace(/^[-•] (.+)$/gm, "<li>$1</li>")
    .replace(/^(\d+)\. (.+)$/gm, "<li>$2</li>")
    .replace(/(<li>[\s\S]*?<\/li>)/g, m => `<ul>${m}</ul>`)
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br>");
}

function fmtSize(b) {
  if (b < 1024) return b + "B";
  if (b < 1048576) return (b / 1024).toFixed(1) + "KB";
  return (b / 1048576).toFixed(1) + "MB";
}

function timeAgo(iso) {
  if (!iso) return "";
  const d = Date.now() - new Date(iso).getTime();
  const m = Math.floor(d / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  if (m < 1440) return `${Math.floor(m / 60)}h ago`;
  return `${Math.floor(m / 1440)}d ago`;
}

// ─── MAIN COMPONENT ───────────────────────────────────────────────────────────
export default function Research() {
  const [mode, setMode] = useState("research"); // research|analyze|essay|presentation|kb
  const [loading, setLoading] = useState(false);
  const [loadMsg, setLoadMsg] = useState("PROCESSING...");
  const [result, setResult] = useState(null);  // { type, title, content, meta }
  const [sessions, setSessions] = useState([]);
  const [stats, setStats] = useState({});
  const [toast, setToast] = useState(null);

  // form state
  const [query, setQuery] = useState("");
  const [essayStyle, setEssayStyle] = useState("analytical");
  const [essayLength, setEssayLength] = useState("medium");
  const [analyzeMode, setAnalyzeMode] = useState("analyze");
  const [summaryStyle, setSummaryStyle] = useState("executive");
  const [pptxSlides, setPptxSlides] = useState(10);
  const [file, setFile] = useState(null);
  const [nSources, setNSources] = useState(8);

  // pptx viewer
  const [pptxData, setPptxData] = useState(null);
  const [slideIdx, setSlideIdx] = useState(0);

  // kb
  const [kbDocs, setKbDocs] = useState([]);

  const fileRef = useRef();
  const outputRef = useRef();
  const toastRef = useRef();

  // ── load on mount ──
  useEffect(() => {
    loadStats();
    loadSessions();
  }, []);

  // ── scroll output to top when result changes ──
  useEffect(() => {
    if (result && outputRef.current) outputRef.current.scrollTop = 0;
  }, [result]);

  // ── toast ──
  function showToast(msg, type = "") {
    setToast({ msg, type });
    clearTimeout(toastRef.current);
    toastRef.current = setTimeout(() => setToast(null), 3200);
  }

  // ── data loading ──
  async function loadStats() {
    try { setStats(await rApi("GET", "/stats")); } catch {}
  }
  async function loadSessions() {
    try { setSessions(await rApi("GET", "/sessions?limit=15")); } catch {}
  }
  async function loadKB() {
    try { setKbDocs(await rApi("GET", "/documents")); } catch {}
  }

  // ── mode switch ──
  function switchMode(m) {
    setMode(m);
    setResult(null);
    setPptxData(null);
    if (m === "kb") loadKB();
  }

  // ── ACTIONS ──
  async function runResearch() {
    if (!query.trim()) { showToast("Enter a research query", "error"); return; }
    setLoading(true);
    setResult(null);
    const msgs = ["SEARCHING KNOWLEDGE BASE...", "SYNTHESIZING INSIGHTS...", "CROSS-REFERENCING SOURCES..."];
    let mi = 0;
    const ticker = setInterval(() => setLoadMsg(msgs[mi++ % msgs.length]), 1800);
    try {
      const r = await rApi("POST", "/search", { query: query.trim(), n_sources: nSources });
      setResult({ type: "text", title: r.title || query, content: r.result, meta: r });
      loadSessions(); loadStats();
      showToast("Research complete", "success");
    } catch (e) { showToast(e.message || "Research failed", "error"); }
    finally { clearInterval(ticker); setLoading(false); }
  }

  async function runAnalyze() {
    if (!file) { showToast("Select a file first", "error"); return; }
    setLoading(true);
    setResult(null);
    const msgs = ["READING DOCUMENT...", "EXTRACTING STRUCTURE...", "BUILDING ANALYSIS..."];
    let mi = 0;
    const ticker = setInterval(() => setLoadMsg(msgs[mi++ % msgs.length]), 1600);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("mode", analyzeMode);
      fd.append("query", query.trim());
      fd.append("summary_style", summaryStyle);
      fd.append("tags", "research");
      const r = await rUpload(fd);
      const a = r.analysis;
      if (analyzeMode === "extract" && a?.extracted) {
        setResult({ type: "extract", title: `Extraction: ${file.name}`, extracted: a.extracted, meta: a });
      } else {
        setResult({ type: "text", title: a?.title || `Analysis: ${file.name}`, content: a?.result, meta: a });
      }
      loadSessions(); loadStats();
      showToast("Analysis complete", "success");
    } catch (e) { showToast(e.message || "Analysis failed", "error"); }
    finally { clearInterval(ticker); setLoading(false); }
  }

  async function runEssay() {
    if (!query.trim()) { showToast("Enter a topic", "error"); return; }
    setLoading(true);
    setResult(null);
    const msgs = ["PLANNING STRUCTURE...", "BUILDING ARGUMENT...", "WRITING ESSAY..."];
    let mi = 0;
    const ticker = setInterval(() => setLoadMsg(msgs[mi++ % msgs.length]), 1800);
    try {
      const r = await rApi("POST", "/essay", { topic: query.trim(), style: essayStyle, length: essayLength });
      setResult({ type: "text", title: r.title || query, content: r.result, meta: r });
      loadSessions(); loadStats();
      showToast("Essay complete", "success");
    } catch (e) { showToast(e.message || "Essay failed", "error"); }
    finally { clearInterval(ticker); setLoading(false); }
  }

  async function runPresentation() {
    if (!query.trim()) { showToast("Enter a topic", "error"); return; }
    setLoading(true);
    setResult(null);
    setLoadMsg("GENERATING SLIDE DECK...");
    try {
      const r = await rApi("POST", "/presentation", { topic: query.trim(), slides: pptxSlides });
      if (r.pptx_data) {
        setPptxData(r.pptx_data);
        setSlideIdx(0);
        setResult({ type: "pptx", title: r.title || query, meta: r });
      } else { showToast("Generation failed — retry", "error"); }
      loadSessions(); loadStats();
      showToast("Deck ready", "success");
    } catch (e) { showToast(e.message || "Presentation failed", "error"); }
    finally { setLoading(false); }
  }

  async function loadSession(id) {
    setLoading(true);
    setLoadMsg("LOADING SESSION...");
    try {
      const s = await rApi("GET", `/sessions/${id}`);
      const m = s.mode?.split("_")[0] || "research";
      switchMode(m);
      if (m === "presentation" && s.result) {
        try {
          const pd = JSON.parse(s.result);
          setPptxData(pd); setSlideIdx(0);
          setResult({ type: "pptx", title: s.title, meta: s });
        } catch { setResult({ type: "text", title: s.title, content: s.result, meta: s }); }
      } else if (s.mode === "extract" && s.result) {
        try {
          setResult({ type: "extract", title: s.title, extracted: JSON.parse(s.result), meta: s });
        } catch { setResult({ type: "text", title: s.title, content: s.result, meta: s }); }
      } else {
        setResult({ type: "text", title: s.title, content: s.result, meta: s });
      }
    } catch (e) { showToast("Failed to load session", "error"); }
    finally { setLoading(false); }
  }

  function copyOutput() {
    const el = outputRef.current;
    if (!el) return;
    navigator.clipboard.writeText(el.innerText || "").then(() => showToast("Copied", "success"));
  }

  function downloadTxt() {
    const text = outputRef.current?.innerText || "";
    const blob = new Blob([text], { type: "text/plain" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `${(result?.title || "research").replace(/[^a-z0-9]/gi, "_")}.txt`; a.click();
  }

  // ─── RENDER ────────────────────────────────────────────────────────────────
  const MODES = [
    { id: "research",     icon: "◎", label: "DEEP RESEARCH" },
    { id: "analyze",      icon: "◈", label: "DOC ANALYSIS" },
    { id: "essay",        icon: "✦", label: "ESSAY WRITER" },
    { id: "presentation", icon: "▣", label: "PRESENTATION" },
    { id: "kb",           icon: "≡", label: "KNOWLEDGE BASE" },
  ];

  return (
    <div className="r-page">
      {/* ── HEADER ── */}
      <div className="r-header">
        <div className="r-header-left">
          <div className="r-logo-mark">ORA</div>
          <div>
            <div className="r-title">RESEARCH AGENT</div>
            <div className="r-subtitle">ANALYTICAL · AUTONOMOUS · GROUNDED</div>
          </div>
        </div>
        <div className="r-header-stats">
          <div className="r-stat"><span className="r-stat-num">{stats.total_sessions ?? "—"}</span><span className="r-stat-label">SESSIONS</span></div>
          <div className="r-stat-div" />
          <div className="r-stat"><span className="r-stat-num">{stats.documents_indexed ?? "—"}</span><span className="r-stat-label">DOCS</span></div>
          <div className="r-stat-div" />
          <div className="r-stat"><span className="r-stat-num">{stats.total_chunks ?? "—"}</span><span className="r-stat-label">CHUNKS</span></div>
          <div className="r-stat-div" />
          <div className="r-stat"><span className="r-stat-num r-model">70B</span><span className="r-stat-label">MODEL</span></div>
        </div>
      </div>

      {/* ── MODE TABS ── */}
      <div className="r-tabs">
        {MODES.map(m => (
          <button key={m.id} className={`r-tab ${mode === m.id ? "active" : ""}`} onClick={() => switchMode(m.id)}>
            <span className="r-tab-icon">{m.icon}</span>{m.label}
          </button>
        ))}
      </div>

      {/* ── BODY ── */}
      <div className="r-body">

        {/* LEFT PANEL */}
        <div className="r-left">

          {/* Sessions */}
          {sessions.length > 0 && (
            <div className="r-sessions">
              <div className="r-section-label">RECENT SESSIONS</div>
              {sessions.slice(0, 8).map(s => (
                <div key={s.session_id} className="r-session-row" onClick={() => loadSession(s.session_id)}>
                  <div className="r-session-title">{s.title}</div>
                  <div className="r-session-meta">{s.mode} · {s.word_count || 0}w · {timeAgo(s.created_at)}</div>
                </div>
              ))}
            </div>
          )}

          {/* Config panel per mode */}
          {mode === "research" && (
            <div className="r-config">
              <div className="r-section-label">DEEP RESEARCH</div>
              <label className="r-label">QUERY</label>
              <textarea className="r-textarea" rows={4} value={query} onChange={e => setQuery(e.target.value)}
                placeholder="What do you want to research? Be specific — e.g. 'Impact of AI on employment in East Africa'" />
              <label className="r-label">SOURCES TO PULL</label>
              <select className="r-select" value={nSources} onChange={e => setNSources(+e.target.value)}>
                <option value={6}>6 sources</option>
                <option value={8}>8 sources (recommended)</option>
                <option value={12}>12 sources (thorough)</option>
              </select>
              <button className="r-run-btn" disabled={loading || !query.trim()} onClick={runResearch}>
                {loading ? "PROCESSING..." : "▶ RUN RESEARCH"}
              </button>
            </div>
          )}

          {mode === "analyze" && (
            <div className="r-config">
              <div className="r-section-label">DOCUMENT ANALYSIS</div>
              <label className="r-label">UPLOAD FILE</label>
              <div className={`r-upload-zone ${file ? "has-file" : ""}`} onClick={() => !file && fileRef.current?.click()}>
                <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.md" style={{ display: "none" }}
                  onChange={e => setFile(e.target.files[0] || null)} />
                {file ? (
                  <div className="r-file-pill">
                    <span className="r-file-name">📄 {file.name}</span>
                    <span className="r-file-size">{fmtSize(file.size)}</span>
                    <button className="r-file-rm" onClick={e => { e.stopPropagation(); setFile(null); if (fileRef.current) fileRef.current.value = ""; }}>×</button>
                  </div>
                ) : (
                  <>
                    <div className="r-upload-icon">◈</div>
                    <div className="r-upload-text">DROP FILE OR CLICK</div>
                    <div className="r-upload-hint">PDF · DOCX · TXT · MD — max 15MB</div>
                  </>
                )}
              </div>
              <label className="r-label">ANALYSIS MODE</label>
              <select className="r-select" value={analyzeMode} onChange={e => setAnalyzeMode(e.target.value)}>
                <option value="analyze">Deep Analysis</option>
                <option value="summarize">Summarize</option>
                <option value="extract">Extract Key Points</option>
              </select>
              {analyzeMode === "summarize" ? (
                <>
                  <label className="r-label">SUMMARY STYLE</label>
                  <select className="r-select" value={summaryStyle} onChange={e => setSummaryStyle(e.target.value)}>
                    <option value="executive">Executive</option>
                    <option value="detailed">Detailed</option>
                    <option value="bullet">Bullet Points</option>
                    <option value="tldr">TL;DR</option>
                  </select>
                </>
              ) : (
                <>
                  <label className="r-label">FOCUS (optional)</label>
                  <textarea className="r-textarea" rows={2} value={query} onChange={e => setQuery(e.target.value)}
                    placeholder="e.g. 'critique the methodology'" />
                </>
              )}
              <button className="r-run-btn" disabled={loading || !file} onClick={runAnalyze}>
                {loading ? "PROCESSING..." : "▶ ANALYZE"}
              </button>
            </div>
          )}

          {mode === "essay" && (
            <div className="r-config">
              <div className="r-section-label">ESSAY WRITER</div>
              <label className="r-label">TOPIC / THESIS</label>
              <textarea className="r-textarea" rows={4} value={query} onChange={e => setQuery(e.target.value)}
                placeholder="e.g. 'The geopolitical implications of AI dominance in East Africa'" />
              <label className="r-label">STYLE</label>
              <select className="r-select" value={essayStyle} onChange={e => setEssayStyle(e.target.value)}>
                <option value="analytical">Analytical</option>
                <option value="argumentative">Argumentative</option>
                <option value="expository">Expository</option>
                <option value="critical">Critical</option>
                <option value="comparative">Comparative</option>
              </select>
              <label className="r-label">LENGTH</label>
              <select className="r-select" value={essayLength} onChange={e => setEssayLength(e.target.value)}>
                <option value="short">Short (~400 words)</option>
                <option value="medium">Medium (~800 words)</option>
                <option value="long">Long (~1500 words)</option>
              </select>
              <button className="r-run-btn" disabled={loading || !query.trim()} onClick={runEssay}>
                {loading ? "PROCESSING..." : "▶ WRITE ESSAY"}
              </button>
            </div>
          )}

          {mode === "presentation" && (
            <div className="r-config">
              <div className="r-section-label">PRESENTATION BUILDER</div>
              <label className="r-label">TOPIC</label>
              <textarea className="r-textarea" rows={3} value={query} onChange={e => setQuery(e.target.value)}
                placeholder="e.g. 'Introduction to Large Language Models'" />
              <label className="r-label">SLIDE COUNT</label>
              <select className="r-select" value={pptxSlides} onChange={e => setPptxSlides(+e.target.value)}>
                <option value={6}>6 slides</option>
                <option value={8}>8 slides</option>
                <option value={10}>10 slides</option>
                <option value={14}>14 slides</option>
              </select>
              <button className="r-run-btn" disabled={loading || !query.trim()} onClick={runPresentation}>
                {loading ? "PROCESSING..." : "▶ GENERATE DECK"}
              </button>
            </div>
          )}

          {mode === "kb" && (
            <div className="r-config">
              <div className="r-section-label">KNOWLEDGE BASE</div>
              <button className="r-run-btn" style={{ marginBottom: 12 }} onClick={() => switchMode("analyze")}>
                + UPLOAD DOCUMENT
              </button>
              {kbDocs.length === 0 ? (
                <div className="r-empty-small">No documents indexed yet</div>
              ) : (
                kbDocs.map(d => (
                  <div key={d.filename} className="r-kb-row">
                    <div className="r-kb-icon">📄</div>
                    <div className="r-kb-info">
                      <div className="r-kb-name">{d.filename}</div>
                      <div className="r-kb-meta">{d.chunks || 0} chunks · {timeAgo(d.indexed_at)}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* RIGHT OUTPUT */}
        <div className="r-right">
          {loading ? (
            <div className="r-loading">
              <div className="r-spinner" />
              <div className="r-load-msg">{loadMsg}</div>
              <div className="r-load-sub">GROQ · LLAMA-3.3-70B · ORA RESEARCH</div>
            </div>
          ) : !result ? (
            <div className="r-empty">
              <div className="r-empty-icon">◈</div>
              <div className="r-empty-title">RESEARCH AGENT READY</div>
              <div className="r-empty-sub">Select a mode and run a query to begin</div>
              <div className="r-empty-caps">
                {["DEEP SYNTHESIS", "PDF ANALYSIS", "ESSAY WRITING", "SLIDE GENERATION", "KNOWLEDGE BASE"].map(c => (
                  <span key={c} className="r-empty-cap">{c}</span>
                ))}
              </div>
            </div>
          ) : result.type === "pptx" && pptxData ? (
            <PptxViewer data={pptxData} slideIdx={slideIdx} setSlideIdx={setSlideIdx} title={result.title} />
          ) : result.type === "extract" ? (
            <ExtractionView data={result.extracted} title={result.title} onCopy={copyOutput} onDownload={downloadTxt} outputRef={outputRef} />
          ) : (
            <TextOutput result={result} outputRef={outputRef} onCopy={copyOutput} onDownload={downloadTxt} />
          )}
        </div>
      </div>

      {/* TOAST */}
      {toast && <div className={`r-toast ${toast.type}`}>{toast.msg}</div>}
    </div>
  );
}

// ─── TEXT OUTPUT ──────────────────────────────────────────────────────────────
function TextOutput({ result, outputRef, onCopy, onDownload }) {
  const meta = result.meta || {};
  const modeIcon = { analyze: "◈", research: "◎", essay: "✦", presentation: "▣", qa: "❓" };
  return (
    <div className="r-output-wrap">
      <div className="r-output-header">
        <div className="r-output-title">{result.title}</div>
        <div className="r-output-tags">
          {meta.mode && <span className="r-tag amber">{modeIcon[meta.mode?.split("_")[0]] || "·"} {meta.mode}</span>}
          {meta.word_count > 0 && <span className="r-tag green">{meta.word_count} WORDS</span>}
          {(meta.sources || []).map(s => <span key={s} className="r-tag">{s}</span>)}
        </div>
      </div>
      <div className="r-output-body" ref={outputRef}
        dangerouslySetInnerHTML={{ __html: `<p>${renderMd(result.content || "")}</p>` }} />
      <div className="r-output-actions">
        <button className="r-act-btn primary" onClick={onCopy}>⎘ COPY</button>
        <button className="r-act-btn" onClick={onDownload}>↓ DOWNLOAD</button>
      </div>
    </div>
  );
}

// ─── EXTRACTION VIEW ─────────────────────────────────────────────────────────
function ExtractionView({ data, title, onCopy, onDownload, outputRef }) {
  const e = data.named_entities || {};
  return (
    <div className="r-output-wrap">
      <div className="r-output-header">
        <div className="r-output-title">{title}</div>
        <div className="r-output-tags">
          <span className="r-tag green">STRUCTURED EXTRACTION</span>
          {data.confidence_level && <span className="r-tag amber">{data.confidence_level.toUpperCase()} CONFIDENCE</span>}
        </div>
      </div>
      <div className="r-extract-grid" ref={outputRef}>
        <ExtCard title="KEY ARGUMENTS" items={data.key_arguments} />
        <ExtCard title="KEY FACTS" items={data.key_facts} />
        <ExtCard title="PEOPLE & ORGS" items={[...(e.people || []), ...(e.organizations || [])]} />
        <ExtCard title="CONCEPTS" items={e.concepts || []} />
        {data.overall_stance && (
          <div className="r-ext-card full">
            <div className="r-ext-title">OVERALL STANCE</div>
            <div className="r-ext-text">{data.overall_stance}</div>
          </div>
        )}
        {data.recommended_followup && (
          <div className="r-ext-card full highlight">
            <div className="r-ext-title">RECOMMENDED FOLLOW-UP</div>
            <div className="r-ext-text">{data.recommended_followup}</div>
          </div>
        )}
      </div>
      <div className="r-output-actions">
        <button className="r-act-btn primary" onClick={onCopy}>⎘ COPY</button>
        <button className="r-act-btn" onClick={onDownload}>↓ DOWNLOAD</button>
      </div>
    </div>
  );
}

function ExtCard({ title, items = [] }) {
  return (
    <div className="r-ext-card">
      <div className="r-ext-title">{title}</div>
      {items.length === 0 ? <div className="r-ext-empty">—</div> :
        items.map((item, i) => <div key={i} className="r-ext-item">{item}</div>)}
    </div>
  );
}

// ─── PPTX VIEWER ─────────────────────────────────────────────────────────────
function PptxViewer({ data, slideIdx, setSlideIdx, title }) {
  const slides = data.slides || [];
  const s = slides[slideIdx] || {};

  function copyOutline() {
    const text = slides.map(sl =>
      `[${sl.index}] ${sl.title || sl.quote || ""}\n${(sl.points || []).map(p => "  • " + p).join("\n")}`
    ).join("\n\n");
    navigator.clipboard.writeText(text);
  }

  function downloadJson() {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `presentation-${Date.now()}.json`; a.click();
  }

  return (
    <div className="r-output-wrap">
      <div className="r-output-header">
        <div className="r-output-title">{title}</div>
        <div className="r-output-tags">
          <span className="r-tag green">PRESENTATION</span>
          <span className="r-tag">{slides.length} SLIDES</span>
        </div>
      </div>

      {/* Slide viewer */}
      <div className="r-pptx">
        <div className="r-pptx-controls">
          <button className="r-pptx-nav" disabled={slideIdx === 0} onClick={() => setSlideIdx(i => i - 1)}>←</button>
          <span className="r-pptx-counter">{slideIdx + 1} / {slides.length}</span>
          <button className="r-pptx-nav" disabled={slideIdx === slides.length - 1} onClick={() => setSlideIdx(i => i + 1)}>→</button>
        </div>

        <div className={`r-slide r-slide-${s.type || "bullets"}`}>
          <div className="r-slide-glow" />
          {s.type === "title" && (
            <>
              <div className="r-slide-title">{s.title}</div>
              {s.subtitle && <div className="r-slide-subtitle">{s.subtitle}</div>}
            </>
          )}
          {s.type === "quote" && (
            <>
              <div className="r-slide-quote">"{s.quote}"</div>
              {s.attribution && <div className="r-slide-attr">— {s.attribution}</div>}
            </>
          )}
          {(s.type === "bullets" || s.type === "conclusion") && (
            <>
              <div className="r-slide-heading">{s.title}</div>
              <div className="r-slide-points">
                {(s.points || []).map((p, i) => (
                  <div key={i} className="r-slide-point">
                    <span className="r-point-dot">▸</span>
                    <span>{p}</span>
                  </div>
                ))}
              </div>
            </>
          )}
          {s.type === "two_column" && (
            <>
              <div className="r-slide-heading">{s.title}</div>
              <div className="r-slide-cols">
                <div>
                  {s.left?.heading && <div className="r-col-head">{s.left.heading}</div>}
                  {(s.left?.points || []).map((p, i) => (
                    <div key={i} className="r-slide-point"><span className="r-point-dot">▸</span><span>{p}</span></div>
                  ))}
                </div>
                <div>
                  {s.right?.heading && <div className="r-col-head">{s.right.heading}</div>}
                  {(s.right?.points || []).map((p, i) => (
                    <div key={i} className="r-slide-point"><span className="r-point-dot">▸</span><span>{p}</span></div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Thumbnails */}
        <div className="r-pptx-thumbs">
          {slides.map((sl, i) => (
            <div key={i} className={`r-pptx-thumb ${i === slideIdx ? "active" : ""}`} onClick={() => setSlideIdx(i)}>
              <div className="r-thumb-num">{i + 1}</div>
              <div className="r-thumb-title">{sl.title || sl.quote || ""}</div>
            </div>
          ))}
        </div>

        {/* Speaker notes */}
        {s.notes && (
          <div className="r-pptx-notes">
            <span className="r-notes-label">NOTES:</span> {s.notes}
          </div>
        )}
      </div>

      <div className="r-output-actions">
        <button className="r-act-btn primary" onClick={copyOutline}>⎘ COPY OUTLINE</button>
        <button className="r-act-btn" onClick={downloadJson}>↓ JSON</button>
      </div>
    </div>
  );
}