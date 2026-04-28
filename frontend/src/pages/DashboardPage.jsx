import { useState, useEffect, useCallback } from "react";
import {
  getStatus, getAlerts, getTasks, getTheNumber,
  getMpesaSummary, getGoals, getCalendarToday,
  getAgentStatus, ackAlert, ackAllAlerts,
} from "../api";

/* ─────────────────────────────────────────────
   SMALL UI ENHANCEMENTS
───────────────────────────────────────────── */

function MachineThinking({ show }) {
  if (!show) return null;
  return <div className="machine-thinking">PROCESSING DATA...</div>;
}

function LiveDot() {
  return <span className="live-dot" />;
}

/* STREAMING TEXT EFFECT */
function useStreamingText(text) {
  const [out, setOut] = useState("");

  useEffect(() => {
    if (!text) return;
    let i = 0;
    setOut("");

    const interval = setInterval(() => {
      i += 3;
      setOut(text.slice(0, i));
      if (i >= text.length) clearInterval(interval);
    }, 10);

    return () => clearInterval(interval);
  }, [text]);

  return out;
}

/* ───────────────────────────────────────────── */

function Meter({ label, value = 0, unit = "%" }) {
  const v = Math.min(Math.max(Number(value) || 0, 0), 100);
  const color = v > 85 ? "var(--red)" : v > 65 ? "var(--amber)" : "var(--green)";

  return (
    <div className="meter">
      <div className="meter-header">
        <span>{label}</span>
        <span style={{ color }}>{v}{unit}</span>
      </div>
      <div className="meter-track">
        <div className="meter-bar" style={{ width: `${v}%`, background: color }} />
      </div>
    </div>
  );
}

/* ───────────────────────────────────────────── */

function TheNumber({ task }) {
  const streamed = useStreamingText(task?.title || "");

  if (!task) return null;

  return (
    <div className="poi-card the-number-card target-box">
      <div className="card-header">
        ◆ HIGH PRIORITY TARGET <LiveDot />
      </div>

      <div className="the-number-title">
        {streamed}
      </div>

      <div className="classification high">
        RELEVANCE: {task.priority?.toUpperCase() || "HIGH"}
      </div>

      {task.overdue && <div className="overdue-badge">⚠ OVERDUE</div>}
    </div>
  );
}

/* ───────────────────────────────────────────── */

function SystemLogs({ logs }) {
  return (
    <div className="poi-card">
      <div className="card-header">SYSTEM LOGS</div>
      <div className="system-log">
        {logs.map((l, i) => (
          <div key={i} className="log-line">
            [{l.time}] {l.msg}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ───────────────────────────────────────────── */

export default function DashboardPage() {
  const [status, setStatus] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [theNumber, setTheNumber] = useState(null);
  const [mpesa, setMpesa] = useState(null);
  const [goals, setGoals] = useState([]);
  const [calendar, setCalendar] = useState([]);
  const [agentCtx, setAgentCtx] = useState(null);

  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState([]);

  /* ───────────────────────────────────────────── */

  const addLog = (msg) => {
    setLogs(prev => [
      { time: new Date().toLocaleTimeString(), msg },
      ...prev.slice(0, 20)
    ]);
  };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    addLog("Fetching system state...");

    const results = await Promise.allSettled([
      getStatus(), getAlerts(10), getTasks(), getTheNumber(),
      getMpesaSummary(), getGoals(), getCalendarToday(), getAgentStatus(),
    ]);

    const [s, a, t, n, m, g, c, ag] = results.map(r =>
      r.status === "fulfilled" ? r.value : null
    );

    if (s) { setStatus(s); addLog("System status updated"); }
    if (a) { setAlerts(Array.isArray(a) ? a : []); }
    if (t) { setTasks(Array.isArray(t) ? t : []); }
    if (n) { setTheNumber(n); addLog("Target identified"); }
    if (m) { setMpesa(m); }
    if (g) { setGoals(Array.isArray(g) ? g : []); }
    if (c) { setCalendar(Array.isArray(c) ? c : []); }
    if (ag) { setAgentCtx(ag); }

    setLoading(false);
  }, []);

  /* ───────────────────────────────────────────── */

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 15000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const activeAlerts = alerts.filter(a => !a.acknowledged);
  const isOnline = status && typeof status.cpu === "number";

  /* ───────────────────────────────────────────── */

  return (
    <div className="page">

      {/* COMMAND INPUT */}
      <input
        className="command-input"
        placeholder="ENTER QUERY..."
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            addLog(`Query received: ${e.target.value}`);
            e.target.value = "";
          }
        }}
      />

      <div className="page-header">
        <div className="page-title">// COMMAND CENTER</div>
        <div className="page-sub">Real-time intelligence • Nairobi • EAT</div>
      </div>

      <MachineThinking show={loading} />

      {/* STATS */}
      <div className="grid-3 stats-row">
        <div className="stat-box">
          {tasks.length}
          <div>PENDING TASKS</div>
        </div>

        <div className="stat-box">
          <span style={{ color: activeAlerts.length ? "var(--red)" : "var(--green)" }}>
            {activeAlerts.length}
          </span>
          <div>ACTIVE ALERTS</div>
        </div>

        <div className="stat-box">
          <span style={{ color: isOnline ? "var(--green)" : "var(--red)" }}>
            {isOnline ? "ONLINE" : "OFFLINE"}
          </span>
          <div>SYSTEM</div>
        </div>
      </div>

      {/* THE NUMBER */}
      <TheNumber task={theNumber} />

      {/* GRID */}
      <div className="grid-2">

        {/* SYSTEM */}
        <div className="poi-card">
          <div className="card-header">
            SYSTEM MONITOR <LiveDot />
          </div>

          {isOnline ? (
            <>
              <Meter label="CPU" value={status.cpu} />
              <Meter label="RAM" value={status.ram} />
            </>
          ) : (
            <div className="empty">OFFLINE</div>
          )}
        </div>

        {/* ALERTS */}
        <div className="poi-card">
          <div className="card-header">
            ALERT FEED
          </div>

          {activeAlerts.length === 0 ? (
            <div className="empty success">ALL SYSTEMS NOMINAL</div>
          ) : (
            activeAlerts.slice(0, 4).map(a => (
              <div key={a.id} className="alert-row">
                {a.message}
              </div>
            ))
          )}
        </div>

        {/* LOGS */}
        <SystemLogs logs={logs} />

      </div>
    </div>
  );
}