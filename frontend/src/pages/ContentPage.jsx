import { useState, useEffect } from "react";
import BASE_URL from "../api";

export default function ContentPage() {
  const [topic, setTopic] = useState("");
  const [contentType, setContentType] = useState("post");
  const [tone, setTone] = useState("professional");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [activeTab, setActiveTab] = useState("generate");

  const contentTypes = [
    { value: "post", label: "General Post" },
    { value: "linkedin", label: "LinkedIn Post" },
    { value: "caption", label: "Social Caption" },
    { value: "thread", label: "Twitter/X Thread" },
    { value: "email", label: "Email Draft" },
  ];

  const loadDrafts = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/content/drafts?status=draft`);
      if (res.ok) {
        const data = await res.json();
        setDrafts(Array.isArray(data) ? data : []);
      }
    } catch (err) {
      console.error("Failed to load drafts", err);
    }
  };

  useEffect(() => {
    loadDrafts();
  }, []);

  const generateDraft = async () => {
    if (!topic.trim()) return;
    
    setLoading(true);
    setResult(null);

    try {
      const res = await fetch(`${BASE_URL}/api/content/draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: topic.trim(),
          content_type: contentType,
          tone: tone
        })
      });

      const data = await res.json();
      setResult(data);
      loadDrafts(); // Refresh drafts list
    } catch (error) {
      alert("Failed to generate draft. Make sure the backend is running.");
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">CONTENT STUDIO</div>
          <div className="page-subtitle">AI-Powered Content Generator by ORA</div>
        </div>
      </div>

      <div className="filter-tabs" style={{ marginBottom: 20 }}>
        <button 
          className={`filter-tab ${activeTab === "generate" ? "active" : ""}`}
          onClick={() => setActiveTab("generate")}
        >
          GENERATE NEW DRAFT
        </button>
        <button 
          className={`filter-tab ${activeTab === "drafts" ? "active" : ""}`}
          onClick={() => setActiveTab("drafts")}
        >
          SAVED DRAFTS ({drafts.length})
        </button>
      </div>

      {/* Generate Tab */}
      {activeTab === "generate" && (
        <div className="card">
          <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <input
              className="input"
              placeholder="What should I write about? (e.g. Launching ORA autonomous AI agent)"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />

            <div>
              <div className="mono text-xs text-dimmer mb-2">CONTENT TYPE</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {contentTypes.map((item) => (
                  <button
                    key={item.value}
                    className={`btn ${contentType === item.value ? "btn-green" : ""}`}
                    onClick={() => setContentType(item.value)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="mono text-xs text-dimmer mb-2">TONE</div>
              <select 
                className="select" 
                value={tone} 
                onChange={(e) => setTone(e.target.value)}
                style={{ width: "100%" }}
              >
                <option value="professional">Professional</option>
                <option value="casual">Casual & Friendly</option>
                <option value="inspirational">Inspirational</option>
                <option value="technical">Technical / Founder Voice</option>
              </select>
            </div>

            <button 
              className="btn btn-green" 
              onClick={generateDraft}
              disabled={loading || !topic.trim()}
              style={{ padding: "14px" }}
            >
              {loading ? "🤖 GENERATING DRAFT..." : "✍️ GENERATE DRAFT"}
            </button>
          </div>
        </div>
      )}

      {/* Result */}
      {result && activeTab === "generate" && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">YOUR NEW DRAFT</span>
          </div>
          <div className="card-body" style={{ 
            whiteSpace: "pre-wrap", 
            fontSize: "14.5px", 
            lineHeight: "1.65",
            background: "rgba(0,0,0,0.2)",
            padding: "16px",
            borderRadius: "8px"
          }}>
            {result.draft || result.error || JSON.stringify(result)}
          </div>
        </div>
      )}

      {/* Drafts Tab */}
      {activeTab === "drafts" && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">SAVED DRAFTS</span>
            <span className="card-badge">{drafts.length}</span>
          </div>
          <div className="card-body">
            {drafts.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">✍️</div>
                <div className="empty-title">No drafts yet</div>
                <div className="empty-body">Generate your first piece of content above</div>
              </div>
            ) : (
              drafts.map((draft) => (
                <div key={draft.id} style={{ 
                  padding: "16px 0", 
                  borderBottom: "1px solid var(--border)",
                  marginBottom: "12px"
                }}>
                  <div style={{ fontWeight: 600, marginBottom: 8 }}>
                    {draft.title} • {draft.type}
                  </div>
                  <div style={{ 
                    fontSize: "13.5px", 
                    color: "var(--text-2)", 
                    whiteSpace: "pre-wrap", 
                    lineHeight: 1.6 
                  }}>
                    {draft.draft?.length > 320 
                      ? draft.draft.substring(0, 320) + "..." 
                      : draft.draft}
                  </div>
                  <div className="mono text-xs" style={{ marginTop: 10, color: "var(--text-4)" }}>
                    {new Date(draft.ts).toLocaleString()}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}