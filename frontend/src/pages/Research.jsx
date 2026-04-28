import { useState, useEffect } from "react";
import "./research.css";

export default function Research() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState("research"); // research | analyze | essay | presentation

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setResult("");

    try {
      // Simulate backend call (replace with real API when ready)
      await new Promise(resolve => setTimeout(resolve, 1800));

      setResult(`**Research Complete**\n\nQuery: "${query}"\n\nMode: ${mode.toUpperCase()}\n\n**Key Insights:**\n• Found 7 relevant documents from your knowledge base\n• Strong correlation between X and Y factors\n• Recommendation: Prioritize action Z\n\n**Sources:**\n- Document A.pdf\n- Internal Notes 2025.md\n- Market Analysis Q1.docx`);
    } catch (err) {
      setResult("Error connecting to ORA Research Engine.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="research-page">
      <div className="research-header">
        <div className="research-logo">
          <span className="logo-mark">ORA</span>
          <div>
            <div className="research-title">RESEARCH INTELLIGENCE</div>
            <div className="research-subtitle">Grounded • Analytical • Autonomous</div>
          </div>
        </div>
      </div>

      <div className="research-main">
        {/* Mode Selector */}
        <div className="mode-selector">
          {["research", "analyze", "essay", "presentation"].map(m => (
            <button
              key={m}
              className={`mode-btn ${mode === m ? "active" : ""}`}
              onClick={() => setMode(m)}
            >
              {m === "research" && "🔬 Deep Research"}
              {m === "analyze" && "📄 Document Analysis"}
              {m === "essay" && "✍️ Essay Writer"}
              {m === "presentation" && "📊 Presentation"}
            </button>
          ))}
        </div>

        {/* Input Area */}
        <div className="input-area">
          <form onSubmit={handleSubmit}>
            <textarea
              className="research-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={
                mode === "research" ? "What would you like to research today?" :
                mode === "analyze" ? "Paste or describe the document to analyze..." :
                mode === "essay" ? "Enter essay topic or thesis statement..." :
                "What should the presentation be about?"
              }
              rows={mode === "research" ? 3 : 4}
            />

            <div className="input-actions">
              <button
                type="submit"
                className="run-btn"
                disabled={loading || !query.trim()}
              >
                {loading ? "THINKING..." : "RUN RESEARCH"}
              </button>
            </div>
          </form>
        </div>

        {/* Output Area */}
        <div className="output-area">
          {loading ? (
            <div className="loading-state">
              <div className="spinner"></div>
              <div className="loading-text">
                {mode === "research" && "Synthesizing from knowledge base..."}
                {mode === "analyze" && "Deep reading document..."}
                {mode === "essay" && "Structuring argument..."}
                {mode === "presentation" && "Building slide deck..."}
              </div>
            </div>
          ) : result ? (
            <div className="result-card">
              <div className="result-header">
                <span className="result-mode">{mode.toUpperCase()}</span>
                <span className="result-time">JUST NOW</span>
              </div>
              <div className="result-content" dangerouslySetInnerHTML={{ __html: result.replace(/\n/g, '<br>') }} />
              <div className="result-actions">
                <button className="action-btn">Copy</button>
                <button className="action-btn">Save to Knowledge</button>
                <button className="action-btn">Export PDF</button>
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">◈</div>
              <div className="empty-text">
                Enter a query above to begin research
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}