import { useState, useEffect, useRef, useCallback } from "react"
import BASE from "../api"

const TYPE_INFO = {
  pdf:   { icon: "📄", label: "PDF" },
  image: { icon: "🖼", label: "IMAGE" },
  text:  { icon: "📝", label: "TEXT" },
  docx:  { icon: "📝", label: "DOCX" },
}

function HowItWorks() {
  return (
    <div className="dashboard-card" style={{ borderColor: "rgba(255, 165, 0, 0.3)", marginBottom: "20px" }}>
      <div className="card-header">
        <span className="card-icon">📚</span>
        <span className="card-title">How It Works</span>
      </div>
      <div style={{ marginTop: "8px", fontSize: "13px", color: "var(--text-secondary)", lineHeight: 1.6 }}>
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
    <div className="dashboard-container">
      {/* Header */}
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">Knowledge Base</h1>
          <p className="dashboard-subtitle">Semantic document indexing · {totalChunks} chunks</p>
        </div>
        <button 
          className="cyber-button"
          onClick={() => setShowGuide(!showGuide)}
          style={{ padding: "8px 16px" }}
        >
          {showGuide ? "✕ Hide" : "? Guide"}
        </button>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Documents</div>
          <div className="stat-value">{docs.length}</div>
        </div>
        <div className="stat-card lime">
          <div className="stat-label">Chunks</div>
          <div className="stat-value lime">{totalChunks}</div>
        </div>
        <div className="stat-card magenta">
          <div className="stat-label">Status</div>
          <div className="stat-value magenta">{uploading ? "Indexing..." : "Ready"}</div>
        </div>
      </div>

      {/* Guide */}
      {showGuide && <HowItWorks />}

      {/* Message */}
      {message && (
        <div className="dashboard-card" style={{
          borderColor: message.type === "success" ? "rgba(57, 255, 20, 0.3)" : "rgba(255, 0, 110, 0.3)",
          background: message.type === "success" ? "rgba(57, 255, 20, 0.05)" : "rgba(255, 0, 110, 0.05)",
          marginBottom: "20px"
        }}>
          <div style={{ color: message.type === "success" ? "#39ff14" : "#ff006e" }}>
            {message.type === "success" ? "✓" : "⚠"} {message.text}
          </div>
        </div>
      )}

      {/* Upload Zone */}
      <div 
        className="dashboard-card"
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        style={{
          borderColor: dragging ? "var(--neon-cyan)" : "rgba(0, 240, 255, 0.2)",
          background: dragging ? "rgba(0, 240, 255, 0.1)" : "rgba(26, 31, 58, 0.8)",
          transition: "all 0.2s ease",
          cursor: "pointer",
          textAlign: "center",
          padding: "40px",
          marginBottom: "20px"
        }}
        onClick={() => fileRef.current?.click()}
      >
        <div style={{ fontSize: "32px", marginBottom: "12px" }}>📤</div>
        <div style={{ fontSize: "16px", fontWeight: "600", color: "var(--text-primary)", marginBottom: "4px" }}>
          {uploading ? "Uploading..." : "Drag files here or click to upload"}
        </div>
        <div style={{ fontSize: "12px", color: "var(--text-tertiary)" }}>
          PDF, DOCX, TXT, or images
        </div>
        <input 
          ref={fileRef}
          type="file"
          onChange={(e) => upload(e.target.files?.[0])}
          disabled={uploading}
          style={{ display: "none" }}
        />
      </div>

      {/* Tags Input */}
      <div className="dashboard-card" style={{ marginBottom: "20px" }}>
        <div className="card-header">
          <span className="card-icon">🏷️</span>
          <span className="card-title">Tags (Optional)</span>
        </div>
        <input
          className="chat-textarea"
          placeholder="Enter tags separated by commas..."
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          style={{ resize: "none", height: "auto" }}
        />
      </div>

      {/* Documents List */}
      <div className="dashboard-card">
        <div className="card-header">
          <span className="card-icon">📚</span>
          <span className="card-title">Documents</span>
          <span className="card-badge">{docs.length}</span>
        </div>

        {docs.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📄</div>
            <div className="empty-text">No documents yet</div>
            <div className="connect-link">Upload your first document above</div>
          </div>
        ) : (
          <div className="task-list">
            {docs.map((doc, i) => {
              const typeInfo = TYPE_INFO[doc.doc_type?.toLowerCase()] || { icon: "📄", label: doc.doc_type || "FILE" }
              const isDeleting = deleting === doc.filename
              return (
                <div key={i} className="task-item" style={{ opacity: isDeleting ? 0.5 : 1 }}>
                  <div style={{ flex: 1 }}>
                    <div className="task-title">
                      {typeInfo.icon} {doc.filename}
                    </div>
                    <div style={{ fontSize: "11px", color: "var(--text-tertiary)", marginTop: "4px", fontFamily: "'JetBrains Mono', monospace" }}>
                      {doc.chunks || 0} chunks · {doc.created_at?.slice(0, 10)}
                      {doc.tags && <span> · Tags: {doc.tags}</span>}
                    </div>
                  </div>
                  <button 
                    className="cyber-button"
                    onClick={() => remove(doc.filename)}
                    disabled={isDeleting}
                    style={{ 
                      padding: "4px 8px", 
                      fontSize: "11px",
                      color: "#ff006e",
                      borderColor: "rgba(255, 0, 110, 0.4)"
                    }}
                  >
                    {isDeleting ? "..." : "Delete"}
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
