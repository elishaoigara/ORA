import { useState, useEffect, useRef, useCallback } from "react"
import BASE from "../api"

const TYPE_INFO = {
  pdf:   { icon: "📄", label: "PDF",   color: "var(--red)" },
  image: { icon: "🖼", label: "IMAGE", color: "var(--green)" },
  text:  { icon: "📝", label: "TEXT",  color: "var(--amber)" },
  docx:  { icon: "📝", label: "DOCX",  color: "var(--amber)" },
}

function HowItWorks() {
  return (
    <div className="card" style={{ marginBottom: "1rem", borderColor: "rgba(245,158,11,0.3)" }}>
      <div className="card-title">How ORA Uses Your Files</div>
      <div style={{ marginTop: 8, fontSize: "0.8rem", color: "var(--text3)", lineHeight: 1.6 }}>
        ORA uses a <b>hybrid semantic + keyword engine</b>.
        <br />• ⚡ Upload returns instantly — indexing runs in the background
        <br />• 💬 File is searchable once indexing completes (usually under 10s)
        <br />• 🗑 Delete removes the file and all its indexed chunks
      </div>
    </div>
  )
}

export default function KnowledgePage() {
  const [docs, setDocs]           = useState([])
  const [tags, setTags]           = useState("")
  const [uploading, setUploading] = useState(false)
  const [message, setMessage]     = useState(null)
  const [dragging, setDragging]   = useState(false)
  const [deleting, setDeleting]   = useState(null)
  const [showGuide, setShowGuide] = useState(false)
  const fileRef = useRef()

  const loadDocs = useCallback(async () => {
    try {
      const res = await fetch(`${BASE}/api/knowledge/documents`)
      if (!res.ok) throw new Error()
      setDocs(await res.json() || [])
    } catch {
      setDocs([])
    }
  }, [])

  useEffect(() => { loadDocs() }, [loadDocs])

  const upload = async (file) => {
    if (!file) return
    setUploading(true)
    setMessage(null)

    const form = new FormData()
    form.append("file", file)
    form.append("tags", tags)

    try {
      const res = await fetch(`${BASE}/api/knowledge/upload`, { method: "POST", body: form })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.error || err.detail || "Upload failed")
      }
      const data = await res.json()
      setMessage({
        text: `${data.filename || file.name} accepted — indexing in background. Refresh in a moment.`,
        type: "success",
      })
      setTags("")
      // Reload docs after a short delay to let background indexing start
      setTimeout(loadDocs, 3000)
    } catch (e) {
      setMessage({ text: e.message || "Upload failed. Try again.", type: "error" })
    }
    setUploading(false)
  }

  const remove = async (filename) => {
    setDeleting(filename)
    try {
      await fetch(`${BASE}/api/knowledge/documents/${encodeURIComponent(filename)}`, { method: "DELETE" })
      setMessage({ text: `${filename} removed`, type: "success" })
      loadDocs()
    } catch {
      setMessage({ text: "Delete failed", type: "error" })
    }
    setDeleting(null)
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) upload(file)
  }

  const totalChunks = docs.reduce((sum, d) => sum + (d.chunks || 0), 0)

  return (
    <div className="page">
      <div className="page-header">
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <div>
            <div className="page-title">// Knowledge Base</div>
            <div className="page-sub">{docs.length} files · {totalChunks} chunks indexed</div>
          </div>
          <button className="btn btn-ghost" onClick={() => setShowGuide(!showGuide)}>
            {showGuide ? "HIDE" : "HOW IT WORKS"}
          </button>
        </div>
      </div>

      {showGuide && <HowItWorks />}

      <div className="card" style={{ marginBottom: "1rem" }}>
        <div className="card-title">Upload Files</div>

        <div
          className={`drop-zone ${dragging ? "dragging" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !uploading && fileRef.current.click()}
        >
          <input
            ref={fileRef}
            type="file"
            style={{ display: "none" }}
            accept=".pdf,.docx,.txt,.md"
            onChange={(e) => upload(e.target.files[0])}
          />
          {uploading ? "Uploading…" : "Drag & Drop or Click · PDF, DOCX, TXT, MD"}
        </div>

        <input
          className="input"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="tags (optional, comma-separated)"
          style={{ marginTop: 8 }}
          disabled={uploading}
        />

        {message && (
          <div style={{
            marginTop: 10,
            padding: "0.5rem 0.75rem",
            borderRadius: 6,
            fontSize: "0.8rem",
            color: message.type === "success" ? "var(--green)" : "var(--red)",
            background: message.type === "success"
              ? "rgba(0,255,157,.06)"
              : "rgba(255,80,80,.06)",
          }}>
            {message.text}
          </div>
        )}
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: ".75rem" }}>
          <div className="card-title" style={{ marginBottom: 0 }}>Files ({docs.length})</div>
          <button className="btn btn-ghost" style={{ fontSize: ".6rem" }} onClick={loadDocs}>
            REFRESH
          </button>
        </div>

        {docs.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">▣</div>
            No files yet — upload a document above
          </div>
        ) : (
          docs.map((doc, i) => {
            const info = TYPE_INFO[doc.doc_type] || TYPE_INFO.text
            return (
              <div key={i} style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "0.6rem 0.5rem",
                borderBottom: "1px solid var(--border)",
                gap: 8,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: ".82rem", color: "var(--text1)", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>{info.icon}</span>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {doc.filename}
                    </span>
                  </div>
                  <div style={{ fontSize: ".65rem", color: "var(--text3)", marginTop: 2 }}>
                    {doc.chunks || 0} chunks
                    {doc.tags ? ` · ${doc.tags}` : ""}
                    {doc.created_at ? ` · ${doc.created_at.slice(0, 10)}` : ""}
                  </div>
                </div>
                <button
                  className="btn btn-danger"
                  style={{ fontSize: ".6rem", flexShrink: 0 }}
                  onClick={() => remove(doc.filename)}
                  disabled={deleting === doc.filename}
                >
                  {deleting === doc.filename ? "…" : "DELETE"}
                </button>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}