import { NavLink } from "react-router-dom"

const links = [
  { to: "/", icon: "⬡", label: "Dashboard" },
  { to: "/chat", icon: "◈", label: "Chat" },
  { to: "/tasks", icon: "◎", label: "Tasks" },
  { to: "/memory", icon: "◉", label: "Memory" },
]

export default function Sidebar() {
  return (
    <aside style={{
      position: "fixed", top: 0, left: 0, bottom: 0,
      width: "220px",
      background: "rgba(8,8,16,0.95)",
      borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
      padding: "2rem 1.5rem",
      backdropFilter: "blur(20px)",
      zIndex: 100,
    }}>
      <div style={{ marginBottom: "3rem" }}>
        <div style={{
          fontFamily: "Syne, sans-serif",
          fontSize: "1.5rem",
          fontWeight: 800,
          color: "var(--accent)",
          letterSpacing: "-0.02em",
          display: "flex", alignItems: "center", gap: "0.5rem"
        }}>
          <span style={{
            width: "28px", height: "28px",
            background: "var(--accent)",
            borderRadius: "8px",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "0.9rem",
            boxShadow: "0 0 20px rgba(108,99,255,0.4)"
          }}>👁</span>
          ORA
        </div>
        <div style={{ fontSize: "0.65rem", color: "var(--muted)", marginTop: "0.25rem", letterSpacing: "0.1em" }}>
          OIGARA'S ASSISTANT
        </div>
      </div>

      <nav style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        {links.map(({ to, icon, label }) => (
          <NavLink key={to} to={to} end={to === "/"} style={({ isActive }) => ({
            display: "flex", alignItems: "center", gap: "0.75rem",
            padding: "0.75rem 1rem",
            borderRadius: "10px",
            textDecoration: "none",
            fontSize: "0.8rem",
            letterSpacing: "0.05em",
            fontWeight: isActive ? 700 : 400,
            color: isActive ? "var(--text)" : "var(--muted)",
            background: isActive ? "rgba(108,99,255,0.12)" : "transparent",
            border: isActive ? "1px solid rgba(108,99,255,0.2)" : "1px solid transparent",
            transition: "all 0.2s",
          })}>
            <span style={{ fontSize: "1rem" }}>{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      <div style={{ marginTop: "auto", fontSize: "0.6rem", color: "var(--muted)", letterSpacing: "0.1em" }}>
        ORA v0.3 — ONLINE
      </div>
    </aside>
  )
}