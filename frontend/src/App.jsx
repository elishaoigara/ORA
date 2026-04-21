import { BrowserRouter, Routes, Route } from "react-router-dom"
import Sidebar from "./components/Sidebar"
import DashboardPage from "./pages/DashboardPage"
import ChatPage from "./pages/ChatPage"
import TasksPage from "./pages/TasksPage"
import MemoryPage from "./pages/MemoryPage"
import KnowledgePage from "./pages/KnowledgePage"
import "./App.css"

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/memory" element={<MemoryPage />} />
            <Route path="/knowledge" element={<KnowledgePage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}