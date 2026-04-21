import { useState, useEffect, useRef } from "react"

const API = "http://localhost:8000"

export default function KnowledgePage() {
  const [docs, setDocs] = useState([])
  const [tags, setTags] = useState("")
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState("")
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef()

  const loadDocs = () => {
    fetch(`${API}/api/knowledge/documents`).then(r => r.json()).then(setDocs).catch(() => {})
  }

  useEffect(() => { loadDocs() }, [])

  const upload = async (file) => {
    if (!file) return
    setUploading(true)
    setMessage("")
    const form = new FormData()
    form.append("file", file)
    form.append("tags", tags)
    try {
      const res = await fetch(`${API}/api/knowledge/upload`, { method: "POST", body: form })
      const data = await res.json()
      setMessage(`STORED: ${data.filename} · ${data.chunks} chunks indexed`)
      setTags("")
      loadDocs()
    } catch {
      setMessage("ERROR: Upload failed")
    }
    setUploading(false)
  }

  const remove = async (filename) => {
    await fetch(`${API}/api/knowledge/documents/${encodeURIComponent(filename)}`, { method: "DELETE" })
    loadDocs()
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) upload(file)
  }

  const typeIcon = { pdf: "◈ PDF", image: "◉ IMG", text: "◆ TXT" }

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">// Knowledge Base</div>
        <div className="page-sub">Upload files · ORA indexes and remembers them · Ask in Neural Link</div>
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <div className="card-title">Upload Data Source</div>
        <div
          className={`drop-zone ${dragging ? "dragging" : ""}`}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current.click()}
        >
          <div style={{ fontSize: "1.5rem", marginBottom: 8, color: "var(--text3)" }}>◈</div>
          <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.8rem", color: "var(--amber)", marginBottom: 4 }}>
            {dragging ? "DROP TO UPLOAD" : "DRAG & DROP OR CLICK"}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text3)" }}>PDF · TXT · MD · PNG · JPG</div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt,.md,.png,.jpg,.jpeg"
            style={{ display: "none" }}
            onChange={e => upload(e.target.files[0])}
          />
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <input
            className="input"
            value={tags}
            onChange={e => setTags(e.target.value)}
            placeholder="Tags: work, finance, personal..."
          />
          {uploading && (
            <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.75rem", color: "var(--amber)", padding: "0.5rem", whiteSpace: "nowrap" }}>
              INDEXING<span className="blink">_</span>
            </div>
          )}
        </div>

        {message && (
          <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.75rem", color: "var(--green)", marginTop: 8, padding: "0.5rem", background: "var(--bg2)", borderRadius: 4 }}>
            ✓ {message}
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-title">Indexed Files ({docs.length})</div>
        {docs.length === 0 ? (
          <div className="empty"><div className="empty-icon">◈</div>No files indexed yet</div>
        ) : (
          docs.map((doc, i) => (
            <div key={i} className="doc-row">
              <div>
                <div className="doc-name">{typeIcon[doc.doc_type] || "◆ FILE"} · {doc.filename}</div>
                <div className="doc-meta">
                  {doc.chunks} chunks · {doc.tags || "no tags"} · {doc.uploaded_at?.slice(0, 10)}
                </div>
              </div>
              <button className="btn btn-ghost" onClick={() => remove(doc.filename)}>DELETE</button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}