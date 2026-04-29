import { useState, useEffect, useCallback } from "react";
import { getAlerts, ackAlert, ackAllAlerts } from "../api";

const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
const SEV_COLOR = {
  critical: "#ff3b3b",
  high:     "#ff9500",
  medium:   "#ffcc00",
  low:      "#00ff9d",
  info:     "#4488ff",
};

function fmtTs(ts) {
  if (!ts) return "";
  try { return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch { return ""; }
}

export default function AlertsPage() {
  const [alerts,    setAlerts]    = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [filter,    setFilter]    = useState("unread");

  const load = useCallback(async () => {
    try {
      const data = await getAlerts(50);
      setAlerts(Array.isArray(data) ? data : []);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, [load]);

  const handleAck = async (id) => {
    const snap = alerts;
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, acknowledged: true } : a));
    try { await ackAlert(id); } catch { setAlerts(snap); }
  };

  const handleAckAll = async () => {
    setAlerts(prev => prev.map(a => ({ ...a, acknowledged: true })));
    try { await ackAllAlerts(); } catch {}
  };

  const displayed = alerts
    .filter(a => filter === "all" || !a.acknowledged)
    .sort((a, b) => (SEV_ORDER[a.severity] ?? 5) - (SEV_ORDER[b.severity] ?? 5));

  const unread = alerts.filter(a => !a.acknowledged).length;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">ALERTS</div>
          <div className="page-subtitle mono text-xs text-dimmer">
            {unread} UNREAD · {alerts.length} TOTAL
          </div>
        </div>
        {unread > 0 && (
          <button className="btn" onClick={handleAckAll}>ACK ALL</button>
        )}
      </div>

      <div className="filter-tabs mb-12">
        {[["unread", "UNREAD"], ["all", "ALL"]].map(([v, l]) => (
          <button
            key={v}
            className={`filter-tab ${filter === v ? "active" : ""}`}
            onClick={() => setFilter(v)}
          >
            {l}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="empty-state"><div className="spinner" /></div>
      ) : displayed.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">△</div>
          <div className="empty-title">{filter === "unread" ? "No unread alerts" : "No alerts"}</div>
          <div className="empty-body">SYSTEM NOMINAL</div>
        </div>
      ) : (
        displayed.map(a => {
          const color = SEV_COLOR[a.severity?.toLowerCase()] || "#555";
          return (
            <div key={a.id} className={`alert-card ${a.acknowledged ? "acked" : ""}`}>
              <div className="alert-bar" style={{ background: color }} />
              <div className="alert-body">
                <div className="alert-header">
                  <span className="alert-sev" style={{ color }}>{(a.severity || "info").toUpperCase()}</span>
                  <span className="alert-ts">{fmtTs(a.timestamp)}</span>
                </div>
                <div className="alert-msg">{a.message}</div>
                {!a.acknowledged && (
                  <button
                    className="ack-btn"
                    style={{ borderColor: `${color}55`, color }}
                    onClick={() => handleAck(a.id)}
                  >
                    ACKNOWLEDGE
                  </button>
                )}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}