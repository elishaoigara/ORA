import { useState, useEffect } from "react"
import API from "../api"

export default function TasksPage() {
  const [tasks, setTasks] = useState([])

  useEffect(() => {
    fetch(`${API}/api/tasks`).then(r => r.json()).then(setTasks).catch(() => {})
  }, [])

  const priColor = { high: "var(--red)", medium: "var(--amber)", low: "var(--green)" }

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">// Task Queue</div>
        <div className="page-sub">Manage via Telegram · /task add [title] @HH:MM</div>
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <div className="card-title">Telegram Commands</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "0.5rem" }}>
          {[
            ["/task add Buy milk @14:00", "Add task"],
            ["/task list", "View all"],
            ["/task done [id]", "Complete"],
            ["/task delete [id]", "Delete"],
          ].map(([cmd, desc]) => (
            <div key={cmd} style={{ padding: "0.5rem", background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 4 }}>
              <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.72rem", color: "var(--amber)", marginBottom: 2 }}>{cmd}</div>
              <div style={{ fontSize: "0.75rem", color: "var(--text3)" }}>{desc}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-title">Pending ({tasks.length})</div>
        {tasks.length === 0 ? (
          <div className="empty"><div className="empty-icon">◆</div>Queue empty</div>
        ) : (
          tasks.map(t => (
            <div key={t.id} className="task-row">
              <div>
                <div className="task-title">{t.title}</div>
                <div className="task-meta">
                  ID:{t.id} · {t.created_at?.slice(0, 10)}
                  {t.due_at && ` · DUE: ${t.due_at.slice(11, 16)}`}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.7rem", color: priColor[t.priority] || "var(--text3)", letterSpacing: 1 }}>
                  {t.priority?.toUpperCase()}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
