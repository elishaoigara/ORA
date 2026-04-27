import { useState, useEffect } from "react"
import "./App.css"

import Sidebar       from "./components/Sidebar"
import DashboardPage from "./pages/DashboardPage"
import ChatPage      from "./pages/ChatPage"
import TasksPage     from "./pages/TasksPage"
import AlertsPage    from "./pages/AlertsPage"
import KnowledgePage from "./pages/KnowledgePage"
import MemoryPage    from "./pages/MemoryPage"

export default function App() {
  const [page, setPage] = useState("dashboard")
  const [prevPage, setPrevPage] = useState(null)

  const navigate = (next) => {
    if (next === page) return
    setPrevPage(page)
    setPage(next)
  }

  useEffect(() => {
    // optional: log navigation (future analytics / agent memory)
    console.log("[NAV]", page)
  }, [page])

  const pages = {
    dashboard: <DashboardPage />,
    chat:      <ChatPage />,
    tasks:     <TasksPage />,
    alerts:    <AlertsPage />,
    knowledge: <KnowledgePage />,
    memory:    <MemoryPage />,
  }

  return (
    <div className="app">
      <Sidebar current={page} onNavigate={navigate} />

      <main className="main-content fade-in" key={page}>
        {pages[page]}
      </main>
    </div>
  )
}