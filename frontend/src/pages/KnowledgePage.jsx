import { useState, useEffect, useRef } from "react"
import API from "../api"

const TYPE_INFO = {
  pdf:   { icon: "📄", label: "PDF",   color: "var(--red)" },
  image: { icon: "🖼", label: "IMAGE", color: "var(--green)" },
  text:  { icon: "📝", label: "TEXT",  color: "var(--amber)" },
}

function HowItWorks() {
  return (
    <div className="card" style={{ marginBottom: "1rem", borderColor: "rgba(245,158,11,0.3)" }}>
      <div className="card-title">How ORA Uses Your Files</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", marginTop: 8 }}>
        {[
          { step: "01", title: "Upload", desc: "Add any PDF, text, or image file. ORA breaks it into searchable chunks." },
          { step: "02", title: "Index", desc: "Content is stored in ORA's semantic memory — it understands meaning, not just keywords." },
          { step: "03", title: "Answer", desc: "When you ask a question, ORA searches your files FIRST before using general AI knowledge." },
          { step: "04", title: "Train", desc: "The more files you add, the more personalised ORA becomes to you specifically." },
        ].map(s => (
          <div key={s.step} style={{ padding: "0.75rem", background: "var(--bg2)", borderRadius: 4, border: "1px solid var(--border)" }}>
            <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.65rem", color: "var(--amber)", marginBottom: 4 }}>STEP {s.step}</div>
            <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.8rem", color: "var(--text2)", marginBottom: 4 }}>{s.title}</div>
            <div style={{ fontSize: "0.78rem", color: "var(--text3)", lineHeight: 1.5 }}>{s.desc}</div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: "1rem", padding: "0.75rem", background: "rgba(245,158,11,0.05)", border: "1px solid rgba(245,158,11,0.2)", borderRadius: 4 }}>
        <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.7rem", color: "var(--amber)", marginBottom: 4 }}>WHAT TO UPLOAD</div>
        <div style={{ fontSize: "0.8rem", color: "var(--text3)", lineHeight: 1.8 }}>
          CVs · contracts · notes · reports · study material · meeting minutes · 
          project docs · personal journals · financial records · anything you want ORA to know about
        </div>
      </div>
    </div>
  )
}

export default function KnowledgePage() {
  const [docs, setDocs] = useState([])
  const [tags, setTags] = useState("")
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState("")
  const [message, setMessage] = useState(null) // { text, type: 'success'|'error' }
  const [dragging, setDragging] = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [showGuide, setShowGuide] = useState(false)
  const fileRef = useRef()

  const loadDocs = () => {
    fetch(`${API}/api/knowledge/documents`)
      .then(r => r.json())
      .then(setDocs)
      .catch(() => {})
  }

  useEffect(() => { loadDocs() }, [])

  const upload = async (file) => {
    if (!file) return
    setUploading(true)
    setMessage(null)
    setUploadProgress(`Processing ${file.name}...`)

    const form = new FormData()
    form.append("file", file)
    form.append("tags", tags)

    try {
      const res = await fetch(`${API}/api/knowledge/upload`, { method: "POST", body: form })
      const data = await res.json()
      setMessage({
        text: `${data.filename} uploaded — ${data.chunks} chunks indexed into ORA's memory`,
        type: "success"
      })
      setTags("")
      loadDocs()
    } catch {
      setMessage({ text: "Upload failed. Check your connection and try again.", type: "error" })
    }
    setUploading(false)
    setUploadProgress("")
  }

  const remove = async (filename) => {
    setDeleting(filename)
    try {
      await fetch(`${API}/api/knowledge/documents/${encodeURIComponent(filename)}`, { method: "DELETE" })
      setMessage({ text: `${filename} removed from ORA's memory`, type: "success" })
      loadDocs()
    } catch {
      setMessage({ text: "Delete failed.", type: "error" })
    }
    setDeleting(null)
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) upload(file)
  }

  const totalChunks = docs.reduce((sum, d) => sum + d.chunks, 0)

  return (
    <div className="page">
      <div className="page-header">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div className="page-title">// Knowledge Base</div>
            <div className="page-sub">
              {docs.length} files · {totalChunks} chunks indexed · ORA searches this before answering
            </div>
          </div>
          <button
            className="btn btn-ghost"
            onClick={() => setShowGuide(g => !g)}
            style={{ marginTop: 4, fontSize: "0.65rem" }}
          >
            {showGuide ? "HIDE GUIDE" : "HOW IT WORKS"}
          </button>
        </div>
      </div>

      {showGuide && <HowItWorks />}

      {/* Upload Section */}
      <div className="card" style={{ marginBottom: "1rem" }}>
        <div className="card-title">Upload to ORA's Memory</div>

        <div
          className={`drop-zone ${dragging ? "dragging" : ""}`}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !uploading && fileRef.current.click()}
          style={{ cursor: uploading ? "wait" : "pointer" }}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.docx"
            style={{ display: "none" }}
            onChange={e => upload(e.target.files[0])}
          />

          {uploading ? (
            <>
              <div style={{ fontSize: "1.5rem", marginBottom: 8 }}>⏳</div>
              <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.8rem", color: "var(--amber)", marginBottom: 4 }}>
                {uploadProgress}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text3)" }}>Indexing into memory...</div>
            </>
          ) : (
            <>
              <div style={{ fontSize: "1.5rem", marginBottom: 8, color: "var(--text3)" }}>
                {dragging ? "⬇" : "◈"}
              </div>
              <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.8rem", color: "var(--amber)", marginBottom: 4 }}>
                {dragging ? "DROP FILE HERE" : "DRAG & DROP OR CLICK TO SELECT"}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text3)" }}>
                PDF · TXT · MD · PNG · JPG — max recommended 10MB
              </div>
            </>
          )}
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <input
            className="input"
            value={tags}
            onChange={e => setTags(e.target.value)}
            placeholder="Tags (optional): work, finance, personal, health..."
            style={{ flex: 1 }}
          />
          <button
            className="btn btn-amber"
            onClick={() => fileRef.current.click()}
            disabled={uploading}
            style={{ whiteSpace: "nowrap" }}
          >
            SELECT FILE
          </button>
        </div>

        <div style={{ marginTop: 8, fontSize: "0.72rem", color: "var(--text3)", fontFamily: "Share Tech Mono, monospace" }}>
          TIP: Add tags to organise files — e.g. "finance" or "work" — ORA will use them when searching
        </div>

        {message && (
          <div style={{
            marginTop: 10,
            padding: "0.6rem 0.75rem",
            background: message.type === "success" ? "rgba(16,185,129,0.08)" : "rgba(239,68,68,0.08)",
            border: `1px solid ${message.type === "success" ? "var(--green)" : "var(--red)"}`,
            borderRadius: 4,
            fontFamily: "Share Tech Mono, monospace",
            fontSize: "0.75rem",
            color: message.type === "success" ? "var(--green)" : "var(--red)",
          }}>
            {message.type === "success" ? "✓ " : "✗ "}{message.text}
          </div>
        )}
      </div>

      {/* Indexed Files */}
      <div className="card">
        <div className="card-title">
          Indexed Files
          <span style={{ color: "var(--text3)", fontWeight: 400, marginLeft: 8 }}>
            ({docs.length} files · {totalChunks} total chunks)
          </span>
        </div>

        {docs.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">◈</div>
            <div style={{ marginBottom: 8 }}>No files indexed yet</div>
            <div style={{ fontSize: "0.75rem", color: "var(--text3)", maxWidth: 300, margin: "0 auto", lineHeight: 1.6 }}>
              Upload your first file above. ORA will index it and use it to answer your questions more accurately.
            </div>
          </div>
        ) : (
          <div>
            {/* Column headers */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "1fr auto auto auto",
              gap: 8,
              padding: "0.4rem 0.75rem",
              fontFamily: "Share Tech Mono, monospace",
              fontSize: "0.65rem",
              color: "var(--text3)",
              letterSpacing: 1,
              borderBottom: "1px solid var(--border)",
              marginBottom: 4,
            }}>
              <span>FILE</span>
              <span>CHUNKS</span>
              <span>UPLOADED</span>
              <span>ACTION</span>
            </div>

            {docs.map((doc, i) => {
              const info = TYPE_INFO[doc.doc_type] || { icon: "📁", label: "FILE", color: "var(--text3)" }
              return (
                <div key={i} style={{
                  display: "grid",
                  gridTemplateColumns: "1fr auto auto auto",
                  gap: 8,
                  alignItems: "center",
                  padding: "0.65rem 0.75rem",
                  borderRadius: 4,
                  marginBottom: 4,
                  background: "var(--bg2)",
                  border: "1px solid var(--border)",
                  transition: "border-color 0.2s",
                }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{
                        fontFamily: "Share Tech Mono, monospace",
                        fontSize: "0.62rem",
                        padding: "1px 5px",
                        border: `1px solid ${info.color}`,
                        color: info.color,
                        borderRadius: 2,
                      }}>
                        {info.label}
                      </span>
                      <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.8rem", color: "var(--text2)" }}>
                        {doc.filename}
                      </span>
                    </div>
                    {doc.tags && (
                      <div style={{ fontSize: "0.7rem", color: "var(--text3)", marginTop: 3, fontFamily: "Share Tech Mono, monospace" }}>
                        tags: {doc.tags}
                      </div>
                    )}
                  </div>

                  <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.75rem", color: "var(--amber)", textAlign: "center" }}>
                    {doc.chunks}
                  </div>

                  <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.7rem", color: "var(--text3)", whiteSpace: "nowrap" }}>
                    {doc.uploaded_at?.slice(0, 10) || "—"}
                  </div>

                  <button
                    className="btn btn-ghost"
                    onClick={() => remove(doc.filename)}
                    disabled={deleting === doc.filename}
                    style={{ fontSize: "0.65rem", color: deleting === doc.filename ? "var(--text3)" : "var(--red)", borderColor: deleting === doc.filename ? "var(--border)" : "rgba(239,68,68,0.3)" }}
                  >
                    {deleting === doc.filename ? "..." : "REMOVE"}
                  </button>
                </div>
              )
            })}

            <div style={{ marginTop: 12, padding: "0.6rem 0.75rem", background: "rgba(245,158,11,0.04)", border: "1px solid var(--border)", borderRadius: 4, fontSize: "0.75rem", color: "var(--text3)", fontFamily: "Share Tech Mono, monospace" }}>
              ORA searches all {docs.length} files when answering questions. Ask in Neural Link or Telegram.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
