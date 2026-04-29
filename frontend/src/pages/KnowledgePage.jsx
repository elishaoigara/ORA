import { useState, useEffect, useRef, useCallback } from "react"
import { uploadDocument, deleteDocument, searchKnowledge } from "../api"
import BASE_URL from "../api"

const TYPE_ICON = { pdf: "◈", image: "◉", text: "◻", docx: "◆" }

export default function KnowledgePage() {
  const [docs,      setDocs]      = useState([])
  const [tags,      setTags]      = useState("")
  const [uploading, setUploading] = useState(false)
  const [deleting,  setDeleting]  = useState(null)
  const [toast,     setToast]     = useState(null)
  const [dragging,  setDragging]  = useState(false)
  const [tab,       setTab]       = useState("docs")
  const [query,     setQuery]     = useState("")
  const [results,   setResults]   = useState([])
  const [searching, setSearching] = useState(false)
  const fileRef = useRef()

  const showToast = (text, type = "success") => {
    setToast({ text, type })
    setTimeout(() => setToast(null), 3500)
  }

  const loadDocs = useCallback(async () => {
    try {
      const res = await fetch(BASE_URL + "/api/knowledge/documents")
      if (!res.ok) throw new Error()
      setDocs((await res.json()) || [])
    } catch { setDocs([]) }
  }, [])

  useEffect(() => { loadDocs() }, [loadDocs])

  const upload = async (file) => {
    if (!file) return
    setUploading(true)
    try {
      const data = await uploadDocument(file, tags)
      showToast((data.filename || file.name) + " uploaded — indexing in background")
      setTags("")
      setTimeout(loadDocs, 3000)
    } catch (e) {
      showToast(e.message || "Upload failed", "error")
    }
    setUploading(false)
  }

  const remove = async (filename) => {
    setDeleting(filename)
    try {
      await deleteDocument(filename)
      showToast(filename + " deleted")
      loadDocs()
    } catch {
      showToast("Delete failed", "error")
    }
    setDeleting(null)
  }

  const search = async () => {
    if (!query.trim()) return
    setSearching(true)
    try {
      const res = await searchKnowledge(query, 6)
      setResults(Array.isArray(res) ? res : (res?.results || []))
    } catch (e) {
      showToast(e.message || "Search failed", "error")
      setResults([])
    }
    setSearching(false)
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) upload(file)
  }

  const totalChunks = docs.reduce((s, d) => s + (d.chunks || 0), 0)

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">KNOWLEDGE BASE</div>
          <div className="page-subtitle">SEMANTIC DOCUMENT STORE · {totalChunks} CHUNKS</div>
        </div>
        <button className="btn" onClick={loadDocs}>↺ REFRESH</button>
      </div>

      <div className="metrics-row">
        <div className="metric-card">
          <div className="metric-label">DOCUMENTS</div>
          <div className="metric-value">{docs.length}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">CHUNKS</div>
          <div className="metric-value" style={{ color: "#00ff9d" }}>{totalChunks}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">STATUS</div>
          <div className="metric-value" style={{ fontSize: 13, color: uploading ? "#ff9900" : "#00ff9d" }}>
            {uploading ? "INDEXING" : "READY"}
          </div>
        </div>
      </div>

      <div className="filter-tabs" style={{ marginBottom: 14 }}>
        {["docs", "upload", "search"].map(t => (
          <button key={t} className={"filter-tab" + (tab === t ? " active" : "")} onClick={() => setTab(t)}>
            {t === "docs" ? "DOCUMENTS" : t === "upload" ? "UPLOAD" : "SEARCH"}
          </button>
        ))}
      </div>

      {/* DOCUMENTS TAB */}
      {tab === "docs" && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">INDEXED DOCUMENTS</span>
            <span className="card-badge">{docs.length}</span>
          </div>
          {docs.length === 0 ? (
            <div className="card-body">
              <div className="empty-state">
                <div className="empty-icon">◆</div>
                <div className="empty-title">No documents yet</div>
                <div className="empty-body">Upload PDFs, DOCX, TXT, or images</div>
                <button className="btn btn-green" style={{ marginTop: 12 }} onClick={() => setTab("upload")}>
                  UPLOAD FIRST DOC →
                </button>
              </div>
            </div>
          ) : (
            <div style={{ padding: 0 }}>
              {docs.map((doc, i) => {
                const icon = TYPE_ICON[doc.doc_type?.toLowerCase()] || "◻"
                const isDel = deleting === doc.filename
                return (
                  <div key={i} className="doc-row" style={{ opacity: isDel ? 0.4 : 1 }}>
                    <div className="doc-icon" style={{ fontFamily: "var(--mono)", fontSize: 14, color: "var(--text-3)" }}>{icon}</div>
                    <div className="doc-info">
                      <div className="doc-name">{doc.filename}</div>
                      <div className="doc-meta">
                        {doc.chunks || 0} chunks
                        {doc.created_at && " · " + doc.created_at.slice(0, 10)}
                        {doc.tags && " · " + doc.tags}
                      </div>
                      {doc.summary && <div className="doc-summary">{doc.summary}</div>}
                    </div>
                    <button
                      className="btn btn-sm btn-red"
                      onClick={() => remove(doc.filename)}
                      disabled={isDel}
                    >
                      {isDel ? "..." : "DELETE"}
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* UPLOAD TAB */}
      {tab === "upload" && (
        <>
          <div
            className={"upload-zone" + (dragging ? " dragging" : "")}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
          >
            <div className="upload-icon">{uploading ? "⋯" : "↑"}</div>
            <div className="upload-label">{uploading ? "Uploading..." : "Drag files here or click to browse"}</div>
            <div className="upload-hint">PDF · DOCX · TXT · IMAGES</div>
            <input ref={fileRef} type="file" onChange={(e) => upload(e.target.files?.[0])} disabled={uploading} style={{ display: "none" }} />
          </div>

          <div className="card">
            <div className="card-header"><span className="card-title">TAGS (OPTIONAL)</span></div>
            <div className="card-body">
              <input
                className="input"
                placeholder="finance, q3, important..."
                value={tags}
                onChange={(e) => setTags(e.target.value)}
              />
            </div>
          </div>

          <div className="card" style={{ borderColor: "rgba(0,255,157,0.15)" }}>
            <div className="card-header"><span className="card-title">HOW IT WORKS</span></div>
            <div className="card-body">
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {[
                  ["⚡", "Upload returns instantly", "indexing runs in the background"],
                  ["◈", "Searchable in seconds", "once indexing completes (~10s)"],
                  ["◉", "Hybrid search", "semantic + keyword matching"],
                  ["◻", "Delete removes all chunks", "file and index cleared together"],
                ].map(([icon, title, desc]) => (
                  <div key={title} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                    <span className="mono" style={{ color: "var(--green)", width: 18, flexShrink: 0 }}>{icon}</span>
                    <div>
                      <div style={{ fontSize: 12, color: "var(--text-2)", fontWeight: 600 }}>{title}</div>
                      <div className="mono text-xs" style={{ color: "var(--text-4)", marginTop: 2 }}>{desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}

      {/* SEARCH TAB */}
      {tab === "search" && (
        <>
          <div className="card">
            <div className="card-header"><span className="card-title">SEMANTIC SEARCH</span></div>
            <div className="card-body">
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  className="input"
                  placeholder="Ask anything about your documents..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && search()}
                  style={{ flex: 1 }}
                />
                <button className="btn btn-green" onClick={search} disabled={searching || !query.trim()}>
                  {searching ? <span className="spinner" style={{ width: 14, height: 14 }} /> : "SEARCH"}
                </button>
              </div>
            </div>
          </div>

          {results.length > 0 && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">RESULTS</span>
                <span className="card-badge">{results.length}</span>
              </div>
              <div style={{ padding: 0 }}>
                {results.map((r, i) => (
                  <div key={i} style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                      <span className="mono text-xs" style={{ color: "var(--green)" }}>{r.filename || r.source || "Document"}</span>
                      {r.score != null && (
                        <span className="mono text-xs" style={{ color: "var(--text-4)" }}>
                          {Math.round(r.score * 100)}% match
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.6 }}>{r.content || r.text}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {results.length === 0 && !searching && query && (
            <div className="card">
              <div className="card-body">
                <div className="empty-state">
                  <div className="empty-icon">◎</div>
                  <div className="empty-title">No results</div>
                  <div className="empty-body">Try a different query or upload more documents</div>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {toast && (
        <div className={"toast" + (toast.type === "error" ? " error" : " success")}>
          {toast.type === "error" ? "⚠" : "✓"} {toast.text}
        </div>
      )}
    </div>
  )
}