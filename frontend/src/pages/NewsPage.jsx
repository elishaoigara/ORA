import { useState, useEffect } from "react";
import BASE_URL from "../api";

export default function NewsPage() {
  const [digest, setDigest] = useState(null);
  const [headlines, setHeadlines] = useState([]);
  const [categories, setCategories] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [savedArticles, setSavedArticles] = useState([]);
  const [readArticles, setReadArticles] = useState(new Set());

  const load = async () => {
    setLoading(true);
    try {
      const [dRes, hRes, cRes, sRes] = await Promise.all([
        fetch(`${BASE_URL}/api/news/digest`),
        fetch(`${BASE_URL}/api/news/headlines?limit=50`),
        fetch(`${BASE_URL}/api/news/categories`),
        fetch(`${BASE_URL}/api/news/saved`),
      ]);
      if (dRes.ok) setDigest(await dRes.json());
      if (hRes.ok) setHeadlines(await hRes.json());
      if (cRes.ok) setCategories(await cRes.json());
      if (sRes.ok) setSavedArticles(await sRes.json());
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const generateDigest = async () => {
    setGenerating(true);
    try {
      const res = await fetch(`${BASE_URL}/api/news/digest`, { method: "POST" });
      if (res.ok) setDigest(await res.json());
    } catch {}
    setGenerating(false);
  };

  const refreshHeadlines = async () => {
    setRefreshing(true);
    try {
      await fetch(`${BASE_URL}/api/news/ingest`, { method: "POST" });
      await load();
    } catch {}
    setRefreshing(false);
  };

  const markAsRead = async (id) => {
    await fetch(`${BASE_URL}/api/news/${id}/read`, { method: "POST" });
    setReadArticles(prev => new Set([...prev, id]));
  };

  const toggleSave = async (id) => {
    const isSaved = savedArticles.includes(id);
    await fetch(`${BASE_URL}/api/news/${id}/save`, { 
      method: isSaved ? "DELETE" : "POST" 
    });
    setSavedArticles(prev => 
      isSaved ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  useEffect(() => { load(); }, []);

  const filteredHeadlines = selectedCategory === "all" 
    ? headlines 
    : headlines.filter(h => h.category === selectedCategory);

  return (
    <div style={{ padding: "24px", maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ fontFamily: "var(--mono)", fontSize: 20, letterSpacing: "0.1em" }}>
          📰 NEWS AGENT
        </h1>
        <div style={{ display: "flex", gap: 12 }}>
          <button
            onClick={refreshHeadlines}
            disabled={refreshing}
            style={{ fontFamily: "var(--mono)", fontSize: 12, padding: "8px 16px",
                     background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", cursor: "pointer" }}
          >
            {refreshing ? "⟳" : "↻"} REFRESH
          </button>
          <button
            onClick={generateDigest}
            disabled={generating}
            style={{ fontFamily: "var(--mono)", fontSize: 12, padding: "8px 16px",
                     background: "var(--green)", color: "#000", border: "none", cursor: "pointer" }}
          >
            {generating ? "GENERATING..." : "⟳ GENERATE DIGEST"}
          </button>
        </div>
      </div>

      {loading && <p style={{ opacity: 0.5, fontFamily: "var(--mono)" }}>Loading...</p>}

      {/* AI Digest */}
      {digest && (
        <div style={{ marginBottom: 32, padding: 20, border: "1px solid var(--border)", background: "var(--surface)" }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, opacity: 0.5, marginBottom: 8 }}>
            AI DIGEST · {digest.created_at?.slice(0, 16)}
          </div>
          <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 12 }}>{digest.headline}</div>
          {digest.top_story && (
            <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--green)", marginBottom: 16 }}>
              TOP STORY: {digest.top_story}
            </div>
          )}
          <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
            {(digest.sections || []).map((s, i) => (
              <div key={i} style={{ padding: 14, border: "1px solid var(--border)" }}>
                <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent)", marginBottom: 6 }}>
                  {s.category}
                </div>
                <p style={{ fontSize: 13, lineHeight: 1.6, marginBottom: 8 }}>{s.summary}</p>
                <ul style={{ fontSize: 12, opacity: 0.7, paddingLeft: 16 }}>
                  {(s.key_stories || []).map((k, j) => <li key={j}>{k}</li>)}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Category Tabs */}
      {categories.length > 0 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
          <button 
            onClick={() => setSelectedCategory("all")}
            style={{ fontFamily: "var(--mono)", fontSize: 11, padding: "6px 12px",
                     background: selectedCategory === "all" ? "var(--green)" : "transparent",
                     color: selectedCategory === "all" ? "#000" : "var(--text)", 
                     border: "1px solid var(--border)", cursor: "pointer", borderRadius: 4 }}
          >
            ALL
          </button>
          {categories.slice(0, 8).map(cat => (
            <button key={cat} onClick={() => setSelectedCategory(cat)} style={{
              fontFamily: "var(--mono)", fontSize: 11, padding: "6px 12px",
              background: selectedCategory === cat ? "var(--green)" : "transparent",
              color: selectedCategory === cat ? "#000" : "var(--text)",
              border: "1px solid var(--border)", cursor: "pointer", borderRadius: 4
            }}>
              {cat.toUpperCase()}
            </button>
          ))}
        </div>
      )}

      {/* Headlines */}
      <div style={{ fontFamily: "var(--mono)", fontSize: 11, opacity: 0.5, marginBottom: 12 }}>
        LATEST HEADLINES ({filteredHeadlines.length})
      </div>
      {filteredHeadlines.map((h, i) => (
        <div key={i} style={{ padding: "12px 0", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
            <div style={{ display: "flex", gap: 8 }}>
              <button 
                onClick={() => markAsRead(h.id)}
                style={{ background: "none", border: "none", cursor: "pointer", fontSize: 14, padding: 0 }}
              >
                {readArticles.has(h.id) ? "✓" : "○"}
              </button>
              <button 
                onClick={() => toggleSave(h.id)}
                style={{ background: "none", border: "none", cursor: "pointer", fontSize: 14, padding: 0, color: savedArticles.includes(h.id) ? "gold" : "inherit" }}
              >
                {savedArticles.includes(h.id) ? "★" : "☆"}
              </button>
            </div>
            <div style={{ flex: 1 }}>
              <a href={h.url} target="_blank" rel="noreferrer"
                 style={{ textDecoration: "none", color: "inherit" }}>
                <div style={{ fontSize: 14, marginBottom: 4, opacity: readArticles.has(h.id) ? 0.5 : 1 }}>
                  {h.title}
                </div>
              </a>
              <div style={{ fontFamily: "var(--mono)", fontSize: 11, opacity: 0.5, display: "flex", gap: 12 }}>
                <span>{h.source || "Unknown"}</span>
                <span>·</span>
                <span>{h.ingested_at?.slice(0, 16)}</span>
                {h.category && <span>· {h.category.toUpperCase()}</span>}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}