import { useState, useEffect } from "react"

const API = "http://localhost:8000"

export default function TasksPage() {
  const [tasks, setTasks] = useState([])

  const load = async () => {
    try {
      const data = await fetch(`${API}/api/tasks`).then(r => r.json())
      setTasks(data)
    } catch {}
  }

  useEffect(() => { load() }, [])

  return (
    <div style={s.page}>
      <h1 style={s.title}>📌 Tasks</h1>
      <p style={s.sub}>Manage tasks via Telegram: /task add, /task done, /task delete</p>

      <div style={s.list}>
        {tasks.length === 0
          ? <div style={s.empty}>No pending tasks. Add one via Telegram: <code>/task add Buy milk @14:00</code></div>
          : tasks.map(t => (
            <div key={t.id} style={s.task}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <p style={s.taskTitle}>{t.title}</p>
                  <p style={s.taskMeta}>Added: {new Date(t.created_at).toLocaleDateString()}</p>
                </div>
                <div style={{ textAlign: "right" }}>
                  {t.due_at && <span style={s.due}>⏰ {t.due_at.slice(11, 16)}</span>}
                  <span style={{ ...s.priority, color: t.priority === "high" ? "#f87171" : t.priority === "low" ? "#34d399" : "#fbbf24" }}>
                    {t.priority}
                  </span>
                </div>
              </div>
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
  list: { display: "flex", flexDirection: "column", gap: "0.75rem" },
  empty: { color: "#444", background: "#0d0d1a", border: "1px solid #1a1a2e", borderRadius: 12, padding: "2rem", textAlign: "center" },
  task: { background: "#0d0d1a", border: "1px solid #1a1a2e", borderRadius: 12, padding: "1rem 1.25rem" },
  taskTitle: { color: "#e0e0e0", fontSize: "0.95rem" },
  taskMeta: { color: "#333", fontSize: "0.75rem", marginTop: 4 },
  due: { color: "#7c6af7", fontSize: "0.8rem", display: "block" },
  priority: { fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase" }
}