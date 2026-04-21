import { NavLink } from "react-router-dom"

const links = [
  { to: "/", icon: "⬡", label: "Dashboard" },
  { to: "/chat", icon: "◈", label: "Chat" },
  { to: "/tasks", icon: "◎", label: "Tasks" },
  { to: "/knowledge", icon: "◫", label: "Knowledge" },
  { to: "/memory", icon: "◉", label: "Memory" },
]

export default function Sidebar() {
  return (
    <aside style={{
      position: "fixed", top: 0, left: 0, bottom: 0,
      width: "220px",
      background: "rgba(14,14,26,0.97)",
      borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
      padding: "2rem 1.25rem",
      backdropFilter: "blur(20px)",
      zIndex: 100,
    }}>
      <div style={{ marginBottom: "3rem" }}>
        <div style={{
          fontFamily: "Syne, sans-serif",
          fontSize: "1.6rem",
          fontWeight: 800,
          color: "var(--text)",
          letterSpacing: "-0.02em",
          display: "flex", alignItems: "center", gap: "0.5rem"
        }}>
          <span style={{
            width: "32px", height: "32px",
            background: "linear-gradient(135deg, var(--accent), var(--accent2))",
            borderRadius: "10px",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "1rem",
            boxShadow: "0 0 24px rgba(124,106,247,0.5)"
          }}>👁</span>
          ORA
        </div>
        <div style={{ fontSize: "0.6rem", color: "var(--muted)", marginTop: "0.3rem", letterSpacing: "0.12em" }}>
          OIGARA'S ASSISTANT
        </div>
      </div>

      <nav style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
        {links.map(({ to, icon, label }) => (
          <NavLink key={to} to={to} end={to === "/"} style={({ isActive }) => ({
            display: "flex", alignItems: "center", gap: "0.75rem",
            padding: "0.7rem 1rem",
            borderRadius: "10px",
            textDecoration: "none",
            fontSize: "0.78rem",
            letterSpacing: "0.04em",
            fontWeight: isActive ? 700 : 400,
            color: isActive ? "var(--text)" : "var(--muted)",
            background: isActive ? "rgba(124,106,247,0.15)" : "transparent",
            border: isActive ? "1px solid rgba(124,106,247,0.25)" : "1px solid transparent",
            transition: "all 0.15s",
          })}>
            <span style={{ fontSize: "1rem", opacity: 0.9 }}>{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      <div style={{ marginTop: "auto" }}>
        <div style={{
          padding: "0.75rem 1rem",
          background: "rgba(0,229,160,0.08)",
          border: "1px solid rgba(0,229,160,0.15)",
          borderRadius: "10px",
          display: "flex", alignItems: "center", gap: "0.5rem"
        }}>
          <div style={{
            width: "7px", height: "7px",
            background: "var(--accent3)",
            borderRadius: "50%",
            boxShadow: "0 0 8px var(--accent3)"
          }} />
          <span style={{ fontSize: "0.65rem", color: "var(--accent3)", letterSpacing: "0.08em" }}>
            ONLINE
          </span>
        </div>
        <div style={{ fontSize: "0.55rem", color: "var(--muted)", marginTop: "0.5rem", textAlign: "center", letterSpacing: "0.1em" }}>
          ORA v0.3
        </div>
      </div>
    </aside>
  )
}