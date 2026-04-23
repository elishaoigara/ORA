import { useState, useEffect, useRef, useCallback } from "react"
import API from "../api"

const TYPE_INFO = {
  pdf:   { icon: "📄", label: "PDF",   color: "var(--red)" },
  image: { icon: "🖼", label: "IMAGE", color: "var(--green)" },
  text:  { icon: "📝", label: "TEXT",  color: "var(--amber)" },
  docx:  { icon: "📝", label: "DOCX",  color: "var(--amber)" },
}

const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS  = 300_000  // 5 min max

function HowItWorks() {
  return (
    <div className="card" style={{ marginBottom: "1rem", borderColor: "rgba(245,158,11,0.3)" }}>
      <div className="card-title">How ORA Uses Your Files</div>
      <div style={{ marginTop: 8, fontSize: "0.8rem", color: "var(--text3)", lineHeight: 1.6 }}>
        ORA uses a <b>hybrid semantic + keyword engine</b>.
        <br />• ⚡ Upload returns instantly — indexing runs in the background
        <br />• 📊 Progress bar shows embedding status in real time
        <br />• 💬 File is searchable once indexing completes
      </div>
    </div>
  )
}

function ProgressBar({ status, filename }) {
  const pct =
    status === "done"       ? 100 :
    status === "error"      ? 100 :
    status === "processing" ? 60  : 20
  const color =
    status === "done"  ? "var(--green)" :
    status === "error" ? "var(--red)"   : "var(--amber)"
  const label =
    status === "queued"     ? `Queued: ${filename}` :
    status === "processing" ? `Indexing: ${filename}…` :
    status === "done"       ? `Done: ${filename}` :
                              `Error: ${filename}`

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ fontSize: "0.78rem", color, marginBottom: 4 }}>{label}</div>
      <div style={{ background: "var(--border)", borderRadius: 4, height: 6 }}>
        <div style={{
          width: `${pct}%`,
          background: color,
          height: "100%",
          borderRadius: 4,
          transition: "width 0.5s ease"
        }} />
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
  const [activeJob, setActiveJob] = useState(null)
  const fileRef    = useRef()
  const pollRef    = useRef(null)
  const startedAt  = useRef(null)

  const loadDocs = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/knowledge/documents`)
      if (!res.ok) throw new Error()
      setDocs(await res.json() || [])
    } catch {
      setDocs([])
    }
  }, [])

  useEffect(() => { loadDocs() }, [loadDocs])
  useEffect(() => () => clearInterval(pollRef.current), [])

  const startPolling = useCallback((job_id, filename) => {
    startedAt.current = Date.now()

    pollRef.current = setInterval(async () => {
      if (Date.now() - startedAt.current > POLL_TIMEOUT_MS) {
        clearInterval(pollRef.current)
        setActiveJob(prev => ({ ...prev, status: "error" }))
        setMessage({ text: "Indexing timed out. Check server logs.", type: "error" })
        setUploading(false)
        return
      }

      try {
        const res = await fetch(`${API}/api/knowledge/status/${job_id}`)
        if (!res.ok) throw new Error()
        const job = await res.json()

        setActiveJob({ job_id, filename, status: job.status })

        if (job.status === "done") {
          clearInterval(pollRef.current)
          const r = job.result || {}
          setMessage({
            text: r.status === "skipped"
              ? `${filename} already indexed (skipped).`
              : `${filename} indexed — ${r.chunks || 0} chunks stored.`,
            type: "success"
          })
          setUploading(false)
          loadDocs()
        } else if (job.status === "error") {
          clearInterval(pollRef.current)
          setMessage({ text: `Indexing failed for ${filename}. Check server logs.`, type: "error" })
          setUploading(false)
        }
      } catch {
        // network blip — keep polling
      }
    }, POLL_INTERVAL_MS)
  }, [loadDocs])

  const upload = async (file) => {
    if (!file) return
    clearInterval(pollRef.current)
    setUploading(true)
    setMessage(null)
    setActiveJob(null)

    const form = new FormData()
    form.append("file", file)
    form.append("tags", tags)

    try {
      const res = await fetch(`${API}/api/knowledge/upload`, { method: "POST", body: form })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.error || err.detail || "Upload failed")
      }
      const data = await res.json()
      // Upload is synchronous — result comes back directly (no job polling needed)
      setMessage({
        text: data.status === "skipped"
          ? `${data.filename || file.name} already indexed (skipped).`
          : `${data.filename || file.name} indexed — ${data.chunks || 0} chunks stored.`,
        type: data.status === "error" ? "error" : "success"
      })
      setTags("")
      setUploading(false)
      loadDocs()
    } catch (e) {
      setMessage({ text: e.message || "Upload failed. Try again.", type: "error" })
      setUploading(false)
    }
  }

  const remove = async (filename) => {
    setDeleting(filename)
    try {
      await fetch(`${API}/api/knowledge/documents/${encodeURIComponent(filename)}`, { method: "DELETE" })
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
            onChange={(e) => upload(e.target.files[0])}
          />
          {uploading ? "Uploading…" : "Drag & Drop or Click"}
        </div>

        <input
          className="input"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="tags (optional)"
          style={{ marginTop: 8 }}
          disabled={uploading}
        />

        {activeJob && <ProgressBar status={activeJob.status} filename={activeJob.filename} />}

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

      <div className="card">
        <div className="card-title">Files ({docs.length})</div>

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
                <div>{doc.chunks} chunks</div>
                <button onClick={() => remove(doc.filename)} disabled={deleting === doc.filename}>
                  {deleting === doc.filename ? "…" : "X"}
                </button>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
