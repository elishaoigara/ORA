import { useState } from "react";
import "./research.css";

export default function Research() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState("");

  const runResearch = async () => {
    const res = await fetch("http://localhost:8000/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });

    const data = await res.json();
    setResult(data.result || "No result");
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

        <button onClick={runResearch}>Run Research</button>

        <div className="result">
          {result}
        </div>
      </div>
    </div>
  );
}