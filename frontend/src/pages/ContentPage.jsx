import { useState, useEffect } from "react";
import { createContentDraft, getContentDrafts } from "../api";

export default function ContentPage() {
  const [topic, setTopic] = useState("");
  const [contentType, setContentType] = useState("post");
  const [tone, setTone] = useState("professional");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [activeTab, setActiveTab] = useState("generate");
  const [selectedDraft, setSelectedDraft] = useState(null);

  const contentTypes = [
    { value: "post", label: "General Post" },
    { value: "linkedin", label: "LinkedIn Post" },
    { value: "caption", label: "Social Caption" },
    { value: "thread", label: "Twitter Thread" },
    { value: "email", label: "Email Draft" },
  ];

  const loadDrafts = async () => {
    try {
      const data = await getContentDrafts("draft", 15);
      setDrafts(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Failed to load drafts", e);
      setDrafts([]);
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
      const data = await createContentDraft({
        topic: topic.trim(),
        content_type: contentType,
        tone: tone
      });

      setResult(data);
      loadDrafts(); // Refresh list after new draft
    } catch (err) {
      console.error(err);
      alert("Failed to generate draft. Make sure the backend is running.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">CONTENT STUDIO</div>
          <div className="page-subtitle">ORA AI Draft Generator</div>
        </div>
      </div>

      <div className="filter-tabs" style={{ marginBottom: 20 }}>
        <button 
          className={`filter-tab ${activeTab === "generate" ? "active" : ""}`}
          onClick={() => setActiveTab("generate")}
        >
          GENERATE NEW
        </button>
        <button 
          className={`filter-tab ${activeTab === "drafts" ? "active" : ""}`}
          onClick={() => setActiveTab("drafts")}
        >
          MY DRAFTS ({drafts.length})
        </button>
      </div>

      {/* GENERATE TAB */}
      {activeTab === "generate" && (
        <>
          <div className="card">
            <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <input
                className="input"
                placeholder="What should I write about? (e.g. Launching ORA v2 autonomous AI agent)"
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
                style={{ padding: "14px", fontSize: "15px" }}
              >
                {loading ? "🤖 GENERATING DRAFT..." : "✍️ GENERATE DRAFT"}
              </button>
            </div>
          </div>

          {/* Generated Result - Improved for long text */}
          {result && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">GENERATED DRAFT</span>
                <button 
                  className="btn btn-sm" 
                  onClick={() => navigator.clipboard.writeText(result.draft || "")}
                >
                  ⎘ COPY
                </button>
              </div>
              <div className="card-body">
                <div style={{
                  whiteSpace: "pre-wrap",
                  fontSize: "14.8px",
                  lineHeight: "1.78",
                  background: "rgba(0,0,0,0.3)",
                  padding: "24px",
                  borderRadius: "10px",
                  maxHeight: "560px",
                  overflowY: "auto",
                  border: "1px solid var(--border)",
                  color: "#e2e8f0"
                }}>
                  {result.draft || result.error || "No content returned"}
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* DRAFTS TAB */}
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
                <div className="empty-body">Generate your first draft above</div>
              </div>
            ) : (
              drafts.map((draft) => (
                <div 
                  key={draft.id} 
                  className="doc-row"
                  onClick={() => setSelectedDraft(draft)}
                  style={{ cursor: "pointer" }}
                >
                  <div className="doc-info">
                    <div className="doc-name">{draft.title}</div>
                    <div className="doc-meta">
                      {draft.type} • {draft.tone} • {new Date(draft.ts).toLocaleDateString()}
                    </div>
                    <div style={{ 
                      marginTop: 8, 
                      fontSize: "13.5px", 
                      color: "var(--text-3)", 
                      lineHeight: 1.65,
                      maxHeight: "110px",
                      overflow: "hidden",
                      textOverflow: "ellipsis"
                    }}>
                      {draft.draft}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Full Draft Modal */}
      {selectedDraft && (
        <div className="modal-overlay" onClick={() => setSelectedDraft(null)}>
          <div className="modal-sheet" onClick={e => e.stopPropagation()}>
            <div className="modal-title">{selectedDraft.title}</div>
            
            <div style={{
              whiteSpace: "pre-wrap",
              fontSize: "14.8px",
              lineHeight: "1.78",
              padding: "24px",
              background: "rgba(0,0,0,0.35)",
              borderRadius: "10px",
              maxHeight: "65vh",
              overflowY: "auto",
              border: "1px solid var(--border)"
            }}>
              {selectedDraft.draft}
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
              <button className="btn" onClick={() => setSelectedDraft(null)}>
                CLOSE
              </button>
              <button 
                className="btn btn-green" 
                onClick={() => navigator.clipboard.writeText(selectedDraft.draft || "")}
              >
                COPY FULL TEXT
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}