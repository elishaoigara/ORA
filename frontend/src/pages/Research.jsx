import { useState } from "react";
import "./research.css";

export default function Research() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);

  const API_URL = import.meta.env.VITE_API_URL;

  const runResearch = async () => {
    if (!query.trim()) return;

    try {
      setLoading(true);
      setResult("");

      const res = await fetch(`${API_URL}/research`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query }),
      });

      if (!res.ok) {
        throw new Error("Request failed");
      }

      const data = await res.json();
      setResult(data.result || "No result returned");
    } catch (error) {
      console.error(error);
      setResult("Error: Could not connect to backend");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ora-container">
      {/* SIDEBAR */}
      <div id="sidebar">
        <div className="sidebar-header">
          <div className="logo">
            <div className="logo-mark">ORA</div>
            <div>
              <div className="logo-text">ORA</div>
              <div className="logo-sub">Research Agent</div>
            </div>
          </div>
        </div>
      </div>

      {/* MAIN */}
      <div className="main">
        <h1>ORA Research Agent</h1>

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask anything..."
        />

        <button onClick={runResearch} disabled={loading}>
          {loading ? "Running..." : "Run Research"}
        </button>

        <div className="result">
          {result}
        </div>
      </div>
    </div>
  );
}