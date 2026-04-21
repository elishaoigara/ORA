import { useState, useEffect, useRef } from "react"

const API = "http://localhost:8000"

const FILE_TYPES = {
  pdf: { icon: "PDF", color: "#ff6584" },
  txt: { icon: "TXT", color: "#43e97b" },
  md: { icon: "MD", color: "#6c63ff" },
  csv: { icon: "CSV", color: "#f7b731" },
  json: { icon: "JSON", color: "#fd9644" },
  png: { icon: "IMG", color: "#a29bfe" },
  jpg: { icon: "IMG", color: "#a29bfe" },
  jpeg: { icon: "IMG", color: "#a29bfe" },
  docx: { icon: "DOC", color: "#74b9ff" },
}

function FileTypeBadge({ filename }) {
  const ext = filename.split(".").pop().toLowerCase()
  const type = FILE_TYPES[ext] || { icon: "FILE", color: "var(--muted)" }
  return (
    <div style={{
      background: `${type.color}22`, border: `1px solid ${type.color}44`,
      color: type.color, borderRadius: "6px", padding: "2px 8px",
      fontSize: "0.6rem", fontWeight: 700, letterSpacing: "0.1em",
      minWidth: "40px", textAlign: "center"
    }}>
      {type.icon}
    </div>
  )
}

export default function KnowledgePage() {
  const [docs, setDocs] = useState([])
  const [uploading, setUploading] = useState(false)
  const [tags, setTags] = useState("")
  const [message, setMessage] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const fileRef = useRef()

  const loadDocs = async () => {
    try {
      const data = await fetch(`${API}/api/knowledge/documents`).then(r => r.json())
      setDocs(data)
    } catch {}
  }

  useEffect(() => { loadDocs() }, [])

  const handleFile = (file) => { if (file) setSelectedFile(file) }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  const upload = async () => {
    const file = selectedFile || fileRef.current?.files[0]
    if (!file) { setMessage({ type: "error", text: "Select a file first." }); return }
    setUploading(true)
    setMessage(null)
    const form = new FormData()
    form.append("file", file)
    form.append("tags", tags)
    try {
      const res = await fetch(`${API}/api/knowledge/upload`, { method: "POST", body: form })
      const data = await res.json()
      setMessage({ type: "success", text: `Stored "${data.filename}" — ${data.chunks} chunks indexed` })
      setSelectedFile(null)
      setTags("")
      if (fileRef.current) fileRef.current.value = ""
      loadDocs()
    } catch {
      setMessage({ type: "error", text: "Upload failed. Is the backend running?" })
    }
    setUploading(false)
  }

  const remove = async (filename) => {
    await fetch(`${API}/api/knowledge/documents/${encodeURIComponent(filename)}`, { method: "DELETE" })
    loadDocs()
  }

  return (
    <div>
      <div style={{ marginBottom: "2.5rem" }}>
        <h1 style={{ fontFamily: "Syne, sans-serif", fontSize: "2rem", fontWeight: 800, letterSpacing: "-0.02em" }}>
          Knowledge Base
        </h1>
        <div style={{ color: "var(--muted)", fontSize: "0.75rem", marginTop: "0.25rem" }}>
          Upload documents — ORA reads, indexes, and uses them in conversation
        </div>
      </div>

      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <div className="tag">Upload Data Source</div>
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
          style={{
            border: `2px dashed ${dragging ? "var(--accent)" : "var(--border)"}`,
            borderRadius: "12px", padding: "2.5rem", textAlign: "center",
            cursor: "pointer", transition: "all 0.2s",
            background: dragging ? "rgba(108,99,255,0.06)" : "transparent",
            marginBottom: "1rem"
          }}
        >
          <input ref={fileRef} type="file"
            accept=".pdf,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.docx"
            style={{ display: "none" }}
            onChange={(e) => handleFile(e.target.files[0])}
          />
          <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>{selectedFile ? "📎" : "⬆"}</div>
          <div style={{ fontSize: "0.8rem", color: selectedFile ? "var(--text)" : "var(--muted)" }}>
            {selectedFile ? selectedFile.name : "Drag & drop or click to select"}
          </div>
          <div style={{ fontSize: "0.65rem", color: "var(--muted)", marginTop: "0.5rem", letterSpacing: "0.05em" }}>
            PDF · TXT · MD · CSV · JSON · DOCX · PNG · JPG
          </div>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <input
            value={tags}
            onChange={e => setTags(e.target.value)}
            placeholder="Tags: work, finance, personal..."
            style={{
              flex: 1, background: "var(--bg2)", border: "1px solid var(--border)",
              borderRadius: "8px", padding: "0.6rem 1rem", color: "var(--text)",
              fontSize: "0.8rem", outline: "none", fontFamily: "Space Mono, monospace"
            }}
          />
          <button onClick={upload} disabled={uploading} style={{
            background: uploading ? "var(--border)" : "var(--accent)",
            border: "none", borderRadius: "8px", color: "#fff",
            padding: "0.6rem 1.5rem", cursor: uploading ? "not-allowed" : "pointer",
            fontWeight: 700, fontSize: "0.8rem", fontFamily: "Space Mono, monospace",
            letterSpacing: "0.05em", whiteSpace: "nowrap",
            boxShadow: uploading ? "none" : "0 0 16px rgba(108,99,255,0.3)"
          }}>
            {uploading ? "Indexing..." : "Upload"}
          </button>
        </div>

        {message && (
          <div style={{
            marginTop: "0.75rem", padding: "0.5rem 1rem", borderRadius: "8px", fontSize: "0.75rem",
            background: message.type === "success" ? "rgba(67,233,123,0.1)" : "rgba(255,101,132,0.1)",
            border: `1px solid ${message.type === "success" ? "rgba(67,233,123,0.2)" : "rgba(255,101,132,0.2)"}`,
            color: message.type === "success" ? "#43e97b" : "#ff6584"
          }}>
            {message.text}
          </div>
        )}
      </div>

      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <div className="tag">Stored Documents ({docs.length})</div>
        {docs.length === 0 ? (
          <div style={{ textAlign: "center", padding: "2rem", color: "var(--muted)", fontSize: "0.8rem" }}>
            No documents yet. Upload something above.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {docs.map((doc, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "0.75rem 1rem", background: "var(--bg2)",
                border: "1px solid var(--border)", borderRadius: "10px",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <FileTypeBadge filename={doc.filename} />
                  <div>
                    <div style={{ fontSize: "0.8rem", color: "var(--text)" }}>{doc.filename}</div>
                    <div style={{ fontSize: "0.65rem", color: "var(--muted)", marginTop: "2px" }}>
                      {doc.chunks} chunks{doc.tags ? ` · ${doc.tags}` : ""}{doc.uploaded_at ? ` · ${doc.uploaded_at.slice(0, 10)}` : ""}
                    </div>
                  </div>
                </div>
                <button onClick={() => remove(doc.filename)} style={{
                  background: "none", border: "1px solid var(--border)", color: "var(--muted)",
                  borderRadius: "6px", padding: "4px 12px", cursor: "pointer",
                  fontSize: "0.7rem", fontFamily: "Space Mono, monospace"
                }}>Delete</button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <div className="tag">Supported Formats</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem" }}>
          {[["pdf","Documents"],["txt","Plain text"],["md","Markdown"],["csv","Spreadsheets"],
            ["json","Data"],["docx","Word docs"],["png","Images"],["jpg","Photos"]].map(([ext, label]) => {
            const type = FILE_TYPES[ext] || { color: "var(--muted)" }
            return (
              <div key={ext} style={{
                padding: "0.75rem", background: `${type.color}11`,
                border: `1px solid ${type.color}22`, borderRadius: "8px", textAlign: "center"
              }}>
                <div style={{ fontSize: "0.7rem", fontWeight: 700, color: type.color, letterSpacing: "0.1em" }}>.{ext}</div>
                <div style={{ fontSize: "0.6rem", color: "var(--muted)", marginTop: "2px" }}>{label}</div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}