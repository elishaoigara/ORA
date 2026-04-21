import { useState, useEffect, useRef } from "react"

const API = "http://localhost:8000"

export default function KnowledgePage() {
  const [docs, setDocs] = useState([])
  const [uploading, setUploading] = useState(false)
  const [tags, setTags] = useState("")
  const [message, setMessage] = useState("")
  const fileRef = useRef()

  const loadDocs = async () => {
    try {
      const data = await fetch(`${API}/api/knowledge/documents`).then(r => r.json())
      setDocs(data)
    } catch {}
  }

  useEffect(() => { loadDocs() }, [])

  const upload = async () => {
    const file = fileRef.current?.files[0]
    if (!file) return
    setUploading(true)
    setMessage("")

    const form = new FormData()
    form.append("file", file)
    form.append("tags", tags)

    try {
      const res = await fetch(`${API}/api/knowledge/upload`, { method: "POST", body: form })
      const data = await res.json()
      setMessage(`✅ Stored "${data.filename}" — ${data.chunks} chunks indexed`)
      fileRef.current.value = ""
      setTags("")
      loadDocs()
    } catch {
      setMessage("❌ Upload failed.")
    }
    setUploading(false)
  }

  const remove = async (filename) => {
    await fetch(`${API}/api/knowledge/documents/${encodeURIComponent(filename)}`, { method: "DELETE" })
    loadDocs()
  }

  const typeIcon = { pdf: "📄", image: "🖼️", text: "📝" }

  return (
    <div style={s.page}>
      <h1 style={s.title}>🗂️ Knowledge Base</h1>
      <p style={s.sub}>Upload docs, notes, and images — ORA will remember them and use them in conversation</p>

      <div style={s.uploadBox}>
        <h2 style={s.sectionTitle}>Upload a File</h2>
        <div style={s.uploadRow}>
          <input ref={fileRef} type="file" accept=".pdf,.txt,.md,.png,.jpg,.jpeg" style={s.fileInput} />
          <input
            value={tags}
            onChange={e => setTags(e.target.value)}
            placeholder="Tags (optional): work, personal, finance..."
            style={s.tagInput}
          />
          <button onClick={upload} disabled={uploading} style={s.uploadBtn}>
            {uploading ? "Uploading..." : "Upload"}
          </button>
        </div>
        {message && <p style={s.message}>{message}</p>}
        <p style={s.hint}>Supported: PDF, TXT, MD, PNG, JPG · After upload, ask ORA about the content in Chat</p>
      </div>

      <div style={s.docsSection}>
        <h2 style={s.sectionTitle}>Stored Documents ({docs.length})</h2>
        {docs.length === 0
          ? <p style={s.empty}>No documents yet. Upload something above.</p>
          : docs.map((doc, i) => (
            <div key={i} style={s.docRow}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: "1.5rem" }}>{typeIcon[doc.doc_type] || "📄"}</span>
                <div>
                  <p style={s.docName}>{doc.filename}</p>
                  <p style={s.docMeta}>{doc.chunks} chunks · {doc.tags || "no tags"} · {doc.uploaded_at?.slice(0, 10)}</p>
                </div>
              </div>
              <button onClick={() => remove(doc.filename)} style={s.deleteBtn}>Delete</button>
            </div>
          ))
        }
      </div>
    </div>
  )
}

const s = {
  page: { padding: "2rem", maxWidth: 800, margin: "0 auto" },
  title: { color: "#7c6af7", fontSize: "1.3rem", fontWeight: 700, marginBottom: 4 },
  sub: { color: "#333", fontSize: "0.8rem", marginBottom: "2rem" },
  uploadBox: { background: "#0d0d1a", border: "1px solid #1a1a2e", borderRadius: 16, padding: "1.5rem", marginBottom: "2rem" },
  sectionTitle: { color: "#7c6af7", fontSize: "0.85rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: 1, marginBottom: "1rem" },
  uploadRow: { display: "flex", gap: 10, flexWrap: "wrap" },
  fileInput: { flex: 2, background: "#0f0f1a", border: "1px solid #1a1a2e", borderRadius: 8, padding: "0.5rem", color: "#e0e0e0", fontSize: "0.85rem" },
  tagInput: { flex: 2, background: "#0f0f1a", border: "1px solid #1a1a2e", borderRadius: 8, padding: "0.5rem 1rem", color: "#e0e0e0", fontSize: "0.85rem", outline: "none" },
  uploadBtn: { background: "#7c6af7", border: "none", borderRadius: 8, color: "#fff", padding: "0.5rem 1.5rem", cursor: "pointer", fontWeight: 600 },
  message: { color: "#34d399", marginTop: "0.75rem", fontSize: "0.85rem" },
  hint: { color: "#333", fontSize: "0.75rem", marginTop: "0.75rem" },
  docsSection: {},
  empty: { color: "#444", textAlign: "center", padding: "2rem" },
  docRow: { display: "flex", justifyContent: "space-between", alignItems: "center", background: "#0d0d1a", border: "1px solid #1a1a2e", borderRadius: 12, padding: "1rem 1.25rem", marginBottom: "0.75rem" },
  docName: { color: "#e0e0e0", fontSize: "0.9rem" },
  docMeta: { color: "#444", fontSize: "0.75rem", marginTop: 2 },
  deleteBtn: { background: "none", border: "1px solid #2a2a3e", color: "#555", borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: "0.8rem" }
}