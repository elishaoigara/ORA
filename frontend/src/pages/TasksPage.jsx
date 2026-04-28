import { useState, useEffect, useCallback } from "react"
import { getTasks, createTask, completeTask, deleteTask } from "../api"

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

  const getPriorityColor = (p) => {
    if (p === "high") return { bg: "rgba(255, 0, 110, 0.2)", color: "#ff006e" }
    if (p === "medium") return { bg: "rgba(255, 165, 0, 0.2)", color: "#ffa500" }
    return { bg: "rgba(57, 255, 20, 0.2)", color: "#39ff14" }
  }

  return (
    <div className="dashboard-container">
      {/* Header */}
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">Task Queue</h1>
          <p className="dashboard-subtitle">{tasks.length} {filter} · {overdueTasks.length} overdue</p>
        </div>
        <button className="cyber-button" onClick={() => setShowAdd(!showAdd)}>
          {showAdd ? "✕ Cancel" : "+ Add Task"}
        </button>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Pending</div>
          <div className="stat-value">{tasks.filter(t => t.status === "pending" || !t.status).length}</div>
        </div>
        <div className="stat-card magenta">
          <div className="stat-label magenta">Overdue</div>
          <div className={`stat-value ${overdueTasks.length > 0 ? 'magenta' : 'lime'}`}>{overdueTasks.length}</div>
        </div>
        <div className="stat-card lime">
          <div className="stat-label">Completed</div>
          <div className="stat-value lime">{tasks.filter(t => t.status === "done").length}</div>
        </div>
      </div>

      {/* Add Task Form */}
      {showAdd && (
        <div className="dashboard-card" style={{ borderColor: "rgba(255, 165, 0, 0.3)", marginBottom: "20px" }}>
          <div className="card-header">
            <span className="card-icon">✏️</span>
            <span className="card-title">New Task</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <input
              className="chat-textarea"
              placeholder="Task title..."
              value={title}
              onChange={e => setTitle(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleAdd()}
              autoFocus
              style={{ resize: "none", height: "auto" }}
            />
            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <div style={{ display: "flex", gap: "8px" }}>
                {PRIORITIES.map(p => {
                  const colors = getPriorityColor(p)
                  return (
                    <button
                      key={p}
                      className="cyber-button"
                      style={{
                        background: priority === p ? colors.bg : "transparent",
                        borderColor: colors.color,
                        color: colors.color,
                        padding: "8px 12px",
                        fontSize: "11px"
                      }}
                      onClick={() => setPriority(p)}
                    >
                      {p.toUpperCase()}
                    </button>
                  )
                })}
              </div>
              <input
                type="datetime-local"
                className="chat-textarea"
                style={{ flex: 1, minWidth: "180px", height: "auto" }}
                value={dueAt}
                onChange={e => setDueAt(e.target.value)}
              />
              <button 
                className="cyber-button" 
                onClick={handleAdd} 
                disabled={saving || !title.trim()}
                style={{ padding: "8px 16px" }}
              >
                {saving ? "Creating..." : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filter Buttons */}
      <div style={{ display: "flex", gap: "12px", marginBottom: "20px" }}>
        {["pending", "done"].map(f => (
          <button
            key={f}
            className="cyber-button"
            onClick={() => setFilter(f)}
            style={{
              background: filter === f ? "rgba(0, 240, 255, 0.2)" : "transparent",
              borderColor: filter === f ? "var(--neon-cyan)" : "rgba(0, 240, 255, 0.3)",
              color: filter === f ? "var(--neon-cyan)" : "var(--text-secondary)",
              padding: "8px 16px"
            }}
          >
            {f.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Task List */}
      <div className="dashboard-card">
        <div className="card-header">
          <span className="card-icon">📋</span>
          <span className="card-title">{filter === "pending" ? "Pending" : "Completed"} Tasks</span>
          <span className="card-badge">{tasks.length}</span>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "32px", color: "var(--text-tertiary)" }}>
            Loading tasks...
          </div>
        ) : tasks.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">◆</div>
            {filter === "pending" ? "Queue empty — add a task above" : "No completed tasks"}
          </div>
        ) : (
          <div className="task-list">
            {tasks.map(t => {
              const isOverdue = t.due_at && new Date(t.due_at) < new Date()
              const acting    = actingOn === t.id
              const priColor = getPriorityColor(t.priority)
              return (
                <div key={t.id} className="task-item" style={{ opacity: acting ? 0.5 : 1 }}>
                  <div style={{ flex: 1 }}>
                    <div className="task-title" style={{ color: isOverdue ? "#ff006e" : "var(--text-primary)" }}>
                      {isOverdue && "⚠ "}{t.title}
                    </div>
                    <div style={{ fontSize: "11px", color: "var(--text-tertiary)", marginTop: "4px", fontFamily: "'JetBrains Mono', monospace" }}>
                      #{t.id} · {t.created_at?.slice(0, 10)}
                      {t.due_at && (
                        <span style={{ color: isOverdue ? "#ff006e" : "var(--text-tertiary)" }}>
                          {" · DUE "}{new Date(t.due_at).toLocaleString("en-KE", { dateStyle: "short", timeStyle: "short" })}
                        </span>
                      )}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                    <span 
                      style={{ 
                        fontFamily: "'JetBrains Mono', monospace", 
                        fontSize: "10px", 
                        fontWeight: 700, 
                        color: priColor.color,
                        background: priColor.bg,
                        padding: "4px 8px",
                        borderRadius: "4px",
                        border: `1px solid ${priColor.color}`
                      }}
                    >
                      {t.priority?.toUpperCase()}
                    </span>
                    {filter === "pending" && (
                      <button 
                        className="cyber-button"
                        style={{ 
                          padding: "4px 8px", 
                          fontSize: "11px",
                          color: "#39ff14",
                          borderColor: "rgba(57, 255, 20, 0.4)"
                        }}
                        onClick={() => handleComplete(t.id)} 
                        disabled={acting}
                      >
                        ✓
                      </button>
                    )}
                    <button 
                      className="cyber-button"
                      style={{ 
                        padding: "4px 8px", 
                        fontSize: "11px",
                        color: "#ff006e",
                        borderColor: "rgba(255, 0, 110, 0.4)"
                      }}
                      onClick={() => handleDelete(t.id)} 
                      disabled={acting}
                    >
                      ✕
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
