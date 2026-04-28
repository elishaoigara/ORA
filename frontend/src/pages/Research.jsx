import { useState } from "react";
import "./research.css";

export default function Research() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState("");

  return (
    <div id="app">
      {/* SIDEBAR */}
      <div id="sidebar">
        <div className="sidebar-logo">
          <div className="ora-eye">
            <div className="ora-eye-inner"></div>
          </div>
          <div>
            <div className="ora-name">ORA</div>
            <div className="ora-sub">Research Agent</div>
          </div>
        </div>
      </div>

      {/* MAIN */}
      <div id="main">
        <div id="topbar">
          <div id="topbar-title">ORA Research</div>
        </div>

        <div id="panel-home" className="panel active">
          <h1 className="home-heading">
            ORA <em>Research</em>
          </h1>

          <input
            className="field-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask anything..."
          />

          <button className="run-btn">
            Run Research
          </button>

          <div className="output-body">
            {result}
          </div>
        </div>
      </div>
    </div>
  );
}