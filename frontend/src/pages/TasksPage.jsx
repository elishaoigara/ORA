import { useState, useEffect, useCallback } from "react"
import { getTasks, createTask, completeTask, deleteTask } from "../api"

const PRI_COLOR = { high: "var(--red)", medium: "var(--amber)", low: "var(--green)" }
const PRIORITIES = ["high", "medium", "low"]

export default function TasksPage() {
  const [tasks,    setTasks]    = useState([])
  const [filter,   setFilter]   = useState("pending")
  const [loading,  setLoading]  = useState(true)
  const [showAdd,  setShowAdd]  = useState(false)
  const [title,    setTitle]    = useState("")
  const [priority, setPriority] = useState("medium")
  const [dueAt,    setDueAt]    = useState("")
  const [saving,   setSaving]   = useState(false)
  const [actingOn, setActingOn] = useState(null)

  const load = useCallback(async (status = filter) => {
    setLoading(true)
    try {
      const data = await getTasks(status)
      setTasks(Array.isArray(data) ? data : [])
    } catch {}
    setLoading(false)
  }, [filter])

  useEffect(() => { load(filter) }, [filter, load])

  const handleAdd = async () => {
    if (!title.trim()) return
    setSaving(true)
    try {
      await createTask({ title: title.trim(), priority, due_at: dueAt || null })
      setTitle(""); setPriority("medium"); setDueAt("")
      setShowAdd(false)
      load(filter)
    } catch {}
    setSaving(false)
  }

  const handleComplete = async (id) => {
    setActingOn(id)
    await completeTask(id).catch(() => {})
    setTasks(prev => prev.filter(t => t.id !== id))
    setActingOn(null)
  }

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this task?")) return
    setActingOn(id)
    await deleteTask(id).catch(() => {})
    setTasks(prev => prev.filter(t => t.id !== id))
    setActingOn(null)
  }

  const overdueTasks = tasks.filter(t => t.due_at && new Date(t.due_at) < new Date())

  return (
    <div className="page">
      <div className="page-header">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div className="page-title">// Task Queue</div>
            <div className="page-sub">{tasks.length} {filter} · {overdueTasks.length} overdue</div>
          </div>
          <button className="btn btn-primary" onClick={() => setShowAdd(!showAdd)}>
            {showAdd ? "✕ CANCEL" : "+ ADD TASK"}
          </button>
        </div>
      </div>

      {/* Add Task */}
      {showAdd && (
        <div className="card fade-in" style={{ marginBottom: "1rem", borderColor: "rgba(245,158,11,.3)" }}>
          <div className="card-title">New Task</div>
          <input
            className="input"
            placeholder="Task title..."
            value={title}
            onChange={e => setTitle(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleAdd()}
            autoFocus
            style={{ marginBottom: 8 }}
          />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <div style={{ display: "flex", gap: 4 }}>
              {PRIORITIES.map(p => (
                <button
                  key={p}
                  className={`btn ${priority === p ? "btn-primary" : ""}`}
                  style={{ color: PRI_COLOR[p], borderColor: priority === p ? PRI_COLOR[p] : undefined }}
                  onClick={() => setPriority(p)}
                >
                  {p.toUpperCase()}
                </button>
              ))}
            </div>
            <input
              type="datetime-local"
              className="input"
              style={{ flex: 1, minWidth: 180 }}
              value={dueAt}
              onChange={e => setDueAt(e.target.value)}
            />
            <button className="btn btn-primary" onClick={handleAdd} disabled={saving || !title.trim()}>
              {saving ? "···" : "CREATE"}
            </button>
          </div>
        </div>
      )}

      {/* Filter */}
      <div style={{ display: "flex", gap: 6, marginBottom: "1rem" }}>
        {["pending", "done"].map(f => (
          <button
            key={f}
            className={`btn ${filter === f ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setFilter(f)}
          >
            {f.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Task List */}
      <div className="card">
        <div className="card-title">
          {filter === "pending" ? "Pending" : "Completed"} ({tasks.length})
        </div>

        {loading ? (
          <div className="empty">Loading tasks...</div>
        ) : tasks.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">◆</div>
            {filter === "pending" ? "Queue empty — add a task above" : "No completed tasks"}
          </div>
        ) : (
          tasks.map(t => {
            const isOverdue = t.due_at && new Date(t.due_at) < new Date()
            const acting    = actingOn === t.id
            return (
              <div key={t.id} className="task-row fade-in" style={{ opacity: acting ? .5 : 1 }}>
                <div style={{ flex: 1 }}>
                  <div className="task-title" style={{ color: isOverdue ? "var(--red)" : undefined }}>
                    {isOverdue && "⚠ "}{t.title}
                  </div>
                  <div className="task-meta">
                    #{t.id} · {t.created_at?.slice(0, 10)}
                    {t.due_at && (
                      <span style={{ color: isOverdue ? "var(--red)" : "var(--text3)" }}>
                        {" · DUE "}{new Date(t.due_at).toLocaleString("en-KE", { dateStyle: "short", timeStyle: "short" })}
                      </span>
                    )}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: ".68rem", fontWeight: 700, color: PRI_COLOR[t.priority] }}>
                    {t.priority?.toUpperCase()}
                  </span>
                  {filter === "pending" && (
                    <button className="btn" style={{ fontSize: ".6rem", color: "var(--green)", borderColor: "rgba(0,255,157,.3)" }}
                      onClick={() => handleComplete(t.id)} disabled={acting}>
                      ✓
                    </button>
                  )}
                  <button className="btn btn-danger" style={{ fontSize: ".6rem" }}
                    onClick={() => handleDelete(t.id)} disabled={acting}>
                    ✕
                  </button>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}