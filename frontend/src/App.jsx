import { useState } from "react"
import "./App.css"
import Sidebar from "./components/Sidebar"
import DashboardPage from "./pages/DashboardPage"
import ChatPage from "./pages/ChatPage"
import TasksPage from "./pages/TasksPage"
import MemoryPage from "./pages/MemoryPage"
import KnowledgePage from "./pages/KnowledgePage"

export default function App() {
  const [page, setPage] = useState("dashboard")

  const pages = {
    dashboard: <DashboardPage />,
    chat: <ChatPage />,
    tasks: <TasksPage />,
    knowledge: <KnowledgePage />,
    memory: <MemoryPage />,
  }

  return (
    <div className="app">
      <Sidebar current={page} onNavigate={setPage} />
      <main className="main-content">
        {pages[page]}
      </main>
    </div>
  )
}