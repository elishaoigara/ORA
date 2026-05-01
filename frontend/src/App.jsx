import { useState, useEffect } from "react";
import "./App.css";
import Sidebar from "./components/Sidebar";

import DashboardPage from "./pages/DashboardPage";
import ChatPage      from "./pages/ChatPage";
import TasksPage     from "./pages/TasksPage";
import AlertsPage    from "./pages/AlertsPage";
import KnowledgePage from "./pages/KnowledgePage";
import MemoryPage    from "./pages/MemoryPage";
import ResearchPage  from "./pages/ResearchPage";
import InboxPage     from "./pages/InboxPage";
import ContentPage   from "./pages/ContentPage";
import CodePage      from "./pages/CodePage";

import { health, getAlerts } from "./api";
import BASE_URL from "./api";

const pages = {
  dashboard: DashboardPage,
  chat:      ChatPage,
  tasks:     TasksPage,
  alerts:    AlertsPage,
  knowledge: KnowledgePage,
  memory:    MemoryPage,
  research:  ResearchPage,
  inbox:     InboxPage,
  content:   ContentPage,
  code:      CodePage,
};

// Primary nav items shown in bottom nav on mobile (most used first)
const PRIMARY_NAV = [
  { id: "chat",      icon: "◉", label: "CHAT" },
  { id: "dashboard", icon: "◈", label: "HOME" },
  { id: "inbox",     icon: "✉", label: "INBOX" },
  { id: "tasks",     icon: "◻", label: "TASKS" },
  { id: "alerts",    icon: "△", label: "ALERTS" },
  { id: "knowledge", icon: "◆", label: "DOCS" },
  { id: "memory",    icon: "◌", label: "MEMORY" },
  { id: "research",  icon: "⊕", label: "SEARCH" },
  { id: "content",   icon: "✍️", label: "CONTENT" },
  { id: "code",      icon: "⌥",  label: "CODE" },
];

export default function App() {
  const [page, setPage]             = useState("dashboard");
  const [authBanner, setAuthBanner] = useState(null);
  const [unreadAlerts, setUnreadAlerts] = useState(0);
  const [unreadEmails, setUnreadEmails] = useState(0);

  // ── Handle Google OAuth redirect ──────────────────────────────
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("google_auth");
    if (status === "success") {
      setAuthBanner("success");
      setPage("memory");
    } else if (status === "error") {
      setAuthBanner("error");
    }
    if (status) {
      window.history.replaceState({}, "", window.location.pathname);
      setTimeout(() => setAuthBanner(null), 6000);
    }
  }, []);

  // ── Badge counts for mobile nav ───────────────────────────────
  useEffect(() => {
    const check = async () => {
      try {
        const data = await getAlerts(20);
        if (Array.isArray(data)) setUnreadAlerts(data.filter(a => !a.acknowledged).length);
      } catch {}
    };
    check();
    const id = setInterval(check, 30000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch(BASE_URL + "/api/gmail/summary");
        if (res.ok) {
          const data = await res.json();
          setUnreadEmails(data?.unread_count || 0);
        }
      } catch {}
    };
    check();
    const id = setInterval(check, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  const navigate = (next) => {
    if (!next || next === page) return;
    setPage(next);
    // scroll main back to top on navigation
    setTimeout(() => {
      document.querySelector(".app-main")?.scrollTo(0, 0);
    }, 50);
  };

  const Page = pages[page] || DashboardPage;

  const getBadge = (id) => {
    if (id === "alerts" && unreadAlerts > 0) return unreadAlerts;
    if (id === "inbox"  && unreadEmails > 0) return unreadEmails;
    return null;
  };

  return (
    <div className="app-shell">
      {/* Desktop sidebar */}
      <Sidebar current={page} onNavigate={navigate} />

      {/* Main content */}
      <main className="app-main">
        {authBanner && (
          <div style={{
            padding: "10px 20px",
            background: authBanner === "success" ? "rgba(0,255,157,0.08)" : "rgba(255,68,68,0.08)",
            borderBottom: `1px solid ${authBanner === "success" ? "rgba(0,255,157,0.3)" : "rgba(255,68,68,0.3)"}`,
            fontFamily: "var(--mono)", fontSize: "12px",
            color: authBanner === "success" ? "var(--green)" : "var(--red)",
            letterSpacing: "0.06em", display: "flex", alignItems: "center", gap: "10px",
          }}>
            {authBanner === "success"
              ? "✓ Google connected — Calendar, Gmail and Drive are now active"
              : "✕ Google auth failed — check your GOOGLE_CLIENT_ID and GOOGLE_REDIRECT_URI env vars"}
            <button onClick={() => setAuthBanner(null)} style={{
              marginLeft: "auto", background: "none", border: "none",
              color: "inherit", cursor: "pointer", fontSize: "14px",
            }}>×</button>
          </div>
        )}
        <Page />
      </main>

      {/* Mobile bottom navigation */}
      <nav className="mobile-nav" aria-label="Mobile navigation">
        <div className="mobile-nav-inner">
          {PRIMARY_NAV.map(item => {
            const badge = getBadge(item.id);
            return (
              <button
                key={item.id}
                className={`mobile-nav-item${page === item.id ? " active" : ""}`}
                onClick={() => navigate(item.id)}
                aria-label={item.label}
              >
                {badge && <span className="mobile-nav-badge">{badge > 9 ? "9+" : badge}</span>}
                <span className="mobile-nav-item-icon">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
