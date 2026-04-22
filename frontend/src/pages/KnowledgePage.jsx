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

      <div style={{ marginTop: 8, fontSize: "0.8rem", color: "var(--text3)", lineHeight: 1.6 }}>
        ORA uses a <b>lightweight keyword search engine (SQLite FTS5)</b> — not heavy AI embeddings.
        This means:
        <br />• ⚡ Fast responses
        <br />• 💾 Very low memory usage (fits free tier)
        <br />• 🔍 Accurate keyword-based retrieval
      </div>
    </div>
  )
}

export default function KnowledgePage() {
  const [docs, setDocs] = useState([])
  const [tags, setTags] = useState("")
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [showGuide, setShowGuide] = useState(false)
  const fileRef = useRef()

  // -----------------------------
  // LOAD DOCUMENTS
  // -----------------------------
  const loadDocs = async () => {
    try {
      const res = await fetch(`${API}/api/knowledge/documents`)
      if (!res.ok) throw new Error()
      const data = await res.json()
      setDocs(data || [])
    } catch {
      setDocs([])
    }
  }

  useEffect(() => {
    loadDocs()
  }, [])

  // -----------------------------
  // UPLOAD FILE
  // -----------------------------
  const upload = async (file) => {
    if (!file) return

    setUploading(true)
    setMessage(null)

    const form = new FormData()
    form.append("file", file)
    form.append("tags", tags)

    try {
      const res = await fetch(`${API}/api/knowledge/upload`, {
        method: "POST",
        body: form,
      })

      if (!res.ok) throw new Error()

      const data = await res.json()

      setMessage({
        text: `${data.filename} indexed (${data.chunks} chunks)`,
        type: "success",
      })

      setTags("")
      loadDocs()
    } catch {
      setMessage({
        text: "Upload failed. Server may be asleep (free tier). Try again.",
        type: "error",
      })
    }

    setUploading(false)
  }

  // -----------------------------
  // DELETE FILE
  // -----------------------------
  const remove = async (filename) => {
    setDeleting(filename)

    try {
      await fetch(`${API}/api/knowledge/documents/${encodeURIComponent(filename)}`, {
        method: "DELETE",
      })

      setMessage({
        text: `${filename} removed`,
        type: "success",
      })

      loadDocs()
    } catch {
      setMessage({ text: "Delete failed", type: "error" })
    }

    setDeleting(null)
  }

  // -----------------------------
  // DRAG & DROP
  // -----------------------------
  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) upload(file)
  }

  const totalChunks = docs.reduce((sum, d) => sum + (d.chunks || 0), 0)

  return (
    <div className="page">

      {/* HEADER */}
      <div className="page-header">
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <div>
            <div className="page-title">// Knowledge Base</div>
            <div className="page-sub">
              {docs.length} files · {totalChunks} chunks indexed
            </div>
          </div>

          <button
            className="btn btn-ghost"
            onClick={() => setShowGuide(!showGuide)}
          >
            {showGuide ? "HIDE" : "HOW IT WORKS"}
          </button>
        </div>
      </div>

      {showGuide && <HowItWorks />}

      {/* UPLOAD */}
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
            onChange={(e) => upload(e.target.files[0])}
          />

          {uploading ? "Processing..." : "Drag & Drop or Click"}
        </div>

        <input
          className="input"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="tags (optional)"
          style={{ marginTop: 8 }}
        />

        {message && (
          <div style={{
            marginTop: 10,
            padding: "0.5rem",
            color: message.type === "success" ? "var(--green)" : "var(--red)"
          }}>
            {message.text}
          </div>
        )}
      </div>

      {/* FILE LIST */}
      <div className="card">
        <div className="card-title">
          Files ({docs.length})
        </div>

        {docs.length === 0 ? (
          <div>No files yet</div>
        ) : (
          docs.map((doc, i) => {
            const info = TYPE_INFO[doc.doc_type] || TYPE_INFO.text

            return (
              <div key={i} style={{
                display: "flex",
                justifyContent: "space-between",
                padding: "0.5rem",
                borderBottom: "1px solid var(--border)"
              }}>
                <div>
                  {info.icon} {doc.filename}
                  <div style={{ fontSize: "0.7rem", color: "var(--text3)" }}>
                    {doc.tags || "no tags"}
                  </div>
                </div>

                <div>
                  {doc.chunks} chunks
                </div>

                <button
                  onClick={() => remove(doc.filename)}
                  disabled={deleting === doc.filename}
                >
                  {deleting === doc.filename ? "..." : "X"}
                </button>
              </div>
            )
          })
        )}
      </div>

    </div>
  )
}