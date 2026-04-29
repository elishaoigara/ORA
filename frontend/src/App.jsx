import { useState } from "react";
import "./App.css";
import Sidebar from "./components/Sidebar";
import DashboardPage from "./pages/DashboardPage";
import ChatPage from "./pages/ChatPage";
import TasksPage from "./pages/TasksPage";
import AlertsPage from "./pages/AlertsPage";
import KnowledgePage from "./pages/KnowledgePage";
import MemoryPage from "./pages/MemoryPage";
import ResearchPage from "./pages/ResearchPage";

const pages = {
  dashboard: DashboardPage,
  chat:      ChatPage,
  tasks:     TasksPage,
  alerts:    AlertsPage,
  knowledge: KnowledgePage,
  memory:    MemoryPage,
  research:  ResearchPage,
};

export default function App() {
  const [page, setPage] = useState("dashboard");

  const navigate = (next) => {
    if (!next || next === page) return;
    setPage(next);
  };

  const Page = pages[page] || DashboardPage;

  return (
    <div className="app-shell">
      <Sidebar current={page} onNavigate={navigate} />
      <main className="app-main">
        <Page />
      </main>
    </div>
  );
}