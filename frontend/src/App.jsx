import { useState, useEffect } from "react";
import "./App.css";
import Sidebar from "./components/Sidebar";

import DashboardPage from "./pages/DashboardPage";
import ChatPage from "./pages/ChatPage";
import TasksPage from "./pages/TasksPage";
import AlertsPage from "./pages/AlertsPage";
import KnowledgePage from "./pages/KnowledgePage";
import MemoryPage from "./pages/MemoryPage";
import ResearchPage from "./pages/ResearchPage";
import InboxPage from "./pages/InboxPage";
import ContentPage from "./pages/ContentPage";
import CodePage from "./pages/CodePage";

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

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [authBanner, setAuthBanner] = useState(null); // "success" | "error" | null

  // ── Handle Google OAuth redirect (?google_auth=success/error) ──
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("google_auth");
    if (status === "success") {
      setAuthBanner("success");
      setPage("memory"); // take them to memory page where the status card lives
    } else if (status === "error") {
      setAuthBanner("error");
    }
    // Clean the URL so a refresh doesn't re-trigger
    if (status) {
      const clean = window.location.pathname;
      window.history.replaceState({}, "", clean);
      setTimeout(() => setAuthBanner(null), 6000);
    }
  }, []);

  const navigate = (next) => {
    if (!next || next === page) return;
    setPage(next);
  };

  const Page = pages[page] || DashboardPage;

  return (
    <div className="app-shell">
      <Sidebar current={page} onNavigate={navigate} />
      <main className="app-main">
        {/* OAuth result banner */}
        {authBanner && (
          <div style={{
            padding: "10px 20px",
            background: authBanner === "success" ? "rgba(0,255,157,0.08)" : "rgba(255,68,68,0.08)",
            borderBottom: `1px solid ${authBanner === "success" ? "rgba(0,255,157,0.3)" : "rgba(255,68,68,0.3)"}`,
            fontFamily: "var(--mono)",
            fontSize: "12px",
            color: authBanner === "success" ? "var(--green)" : "var(--red)",
            letterSpacing: "0.06em",
            display: "flex",
            alignItems: "center",
            gap: "10px",
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
    </div>
  );
}