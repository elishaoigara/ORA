import { useState, useCallback, useRef } from "react";
import { getTasks, createTask, completeTask, deleteTask } from "../api";

const PRI_COLOR = { high: "#ff4444", medium: "#ff9900", low: "#4488ff" };
const FILTERS = ["PENDING", "DONE"];

function fmtDue(due_at) {
  if (!due_at) return null;
  try { return new Date(due_at).toLocaleDateString("en-KE", { month: "short", day: "2-digit" }); } catch { return null; }
}

export default function TasksPage() {
  const [tasks,      setTasks]      = useState([]);
  const [filter,     setFilter]     = useState("PENDING");
  const [loading,    setLoading]    = useState(true);
  const [modal,      setModal]      = useState(false);
  const [newTitle,   setNewTitle]   = useState("");
  const [newPri,     setNewPri]     = useState("medium");
  const [newDue,     setNewDue]     = useState("");
  const [saving,     setSaving]     = useState(false);
  const [error,      setError]      = useState(null);
  const filterRef = useRef("PENDING");

  const load = useCallback(async (status) => {
    try {
      const data = await getTasks(status);
      setTasks(Array.isArray(data) ? data : []);
      setError(null);
    } catch {
      setError("Could not reach ORA backend.");
    }
  }, []);

  // Load on mount
  useState(() => {
    setLoading(true);
    load("pending").finally(() => setLoading(false));
  });

  // Also trigger once on mount via useEffect pattern
  const [init, setInit] = useState(false);
  if (!init) {
    setInit(true);
    setTimeout(() => load("pending").finally(() => setLoading(false)), 0);
  }

  const onFilterChange = (f) => {
    filterRef.current = f;
    setFilter(f);
    setLoading(true);
    load(f.toLowerCase()).finally(() => setLoading(false));
  };

  const handleComplete = async (id) => {
    const prev = tasks;
    setTasks(t => t.filter(x => x.id !== id));
    try { await completeTask(id); } catch { setTasks(prev); setError("Failed to complete task."); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this task?")) return;
    const prev = tasks;
    setTasks(t => t.filter(x => x.id !== id));
    try { await deleteTask(id); } catch { setTasks(prev); setError("Failed to delete task."); }
  };

  const openModal = () => {
    setNewTitle(""); setNewPri("medium"); setNewDue(""); setError(null); setModal(true);
  };

  const handleAdd = async () => {
    if (!newTitle.trim()) return;
    setSaving(true);
    try {
      await createTask({ title: newTitle.trim(), priority: newPri, due_at: newDue || null });
      setModal(false);
      filterRef.current = "PENDING";
      setFilter("PENDING");
      setLoading(true);
      await load("pending");
    } catch {
      setError("Failed to create task.");
    } finally {
      setSaving(false);
      setLoading(false);
    }
  };

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">{filter}</div>
          <div className="page-subtitle mono text-xs text-dimmer">{tasks.length} TASKS</div>
        </div>
        <button className="btn btn-green" onClick={openModal}>+ NEW</button>
      </div>

      {/* Filters */}
      <div className="filter-tabs mb-12">
        {FILTERS.map(f => (
          <button
            key={f}
            className={`filter-tab ${filter === f ? "active" : ""}`}
            onClick={() => onFilterChange(f)}
          >
            {f}
          </button>
        ))}
      </div>

      {error && <div className="error-bar">{error}</div>}

      {/* List */}
      {loading ? (
        <div className="empty-state"><div className="spinner" /></div>
      ) : tasks.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">{filter === "PENDING" ? "◻" : "✓"}</div>
          <div className="empty-title">{filter === "PENDING" ? "No pending tasks" : "No completed tasks"}</div>
        </div>
      ) : (
        <div className="card">
          <div className="card-header">
            <span className="card-title">TASK LIST</span>
            <span className="card-badge">{tasks.length}</span>
          </div>
          {tasks.map(t => {
            const due = fmtDue(t.due_at);
            return (
              <div key={t.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderBottom: "1px solid var(--border)" }}>
                <div className="task-dot" style={{ background: PRI_COLOR[t.priority] || "#555" }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="task-title">{t.title}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 3 }}>
                    <span className="task-id">#{t.id}</span>
                    <span className="mono text-xs" style={{ color: PRI_COLOR[t.priority] || "#555" }}>
                      {t.priority?.toUpperCase()}
                    </span>
                    {due && <span className="task-due">DUE {due}</span>}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  {filter === "PENDING" && (
                    <button
                      className="btn btn-sm btn-green"
                      onClick={() => handleComplete(t.id)}
                      title="Complete"
                    >
                      ✓
                    </button>
                  )}
                  <button
                    className="btn btn-sm btn-red"
                    onClick={() => handleDelete(t.id)}
                    title="Delete"
                  >
                    ✕
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal */}
      {modal && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && setModal(false)}>
          <div className="modal-sheet">
            <div className="modal-handle" />
            <div className="modal-title">NEW TASK</div>

            <input
              className="input mb-12"
              placeholder="Task description..."
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleAdd()}
              autoFocus
            />

            <div className="mono text-xs text-dimmer mb-8" style={{ letterSpacing: 2 }}>PRIORITY</div>
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              {["high", "medium", "low"].map(p => (
                <button
                  key={p}
                  className={`btn ${newPri === p ? "btn-green" : ""}`}
                  style={newPri === p ? {} : { borderColor: `${PRI_COLOR[p]}44`, color: PRI_COLOR[p] }}
                  onClick={() => setNewPri(p)}
                >
                  {p.toUpperCase()}
                </button>
              ))}
            </div>

            <div className="mono text-xs text-dimmer mb-8" style={{ letterSpacing: 2 }}>DUE DATE (OPTIONAL)</div>
            <input
              type="datetime-local"
              className="input mb-16"
              value={newDue}
              onChange={e => setNewDue(e.target.value)}
            />

            {error && <div className="error-bar mb-12">{error}</div>}

            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn w-full" onClick={() => setModal(false)}>CANCEL</button>
              <button
                className="btn btn-green w-full"
                onClick={handleAdd}
                disabled={!newTitle.trim() || saving}
              >
                {saving ? "..." : "CREATE TASK"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}