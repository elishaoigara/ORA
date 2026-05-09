import { useState, useEffect } from "react";
import BASE_URL from "../api";

export default function NewsPage() {
  const [digest, setDigest]     = useState(null);
  const [headlines, setHeadlines] = useState([]);
  const [loading, setLoading]   = useState(false);
  const [generating, setGenerating] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [dRes, hRes] = await Promise.all([
        fetch(`${BASE_URL}/api/news/digest`),
        fetch(`${BASE_URL}/api/news/headlines?limit=30`),
      ]);
      if (dRes.ok) setDigest(await dRes.json());
      if (hRes.ok) setHeadlines(await hRes.json());
    } catch {}
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

  useEffect(() => { load(); }, []);

  return (
    <div style={{ padding: "24px", maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ fontFamily: "var(--mono)", fontSize: 20, letterSpacing: "0.1em" }}>
          📰 NEWS AGENT
        </h1>
        <button
          onClick={generateDigest}
          disabled={generating}
          style={{ fontFamily: "var(--mono)", fontSize: 12, padding: "8px 16px",
                   background: "var(--green)", color: "#000", border: "none", cursor: "pointer" }}
        >
          {generating ? "GENERATING..." : "⟳ GENERATE DIGEST"}
        </button>
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

      {/* Raw headlines */}
      <div style={{ fontFamily: "var(--mono)", fontSize: 11, opacity: 0.5, marginBottom: 12 }}>
        LATEST HEADLINES ({headlines.length})
      </div>
      {headlines.map((h, i) => (
        <a key={i} href={h.url} target="_blank" rel="noreferrer"
           style={{ display: "block", padding: "12px 0", borderBottom: "1px solid var(--border)",
                    textDecoration: "none", color: "inherit" }}>
          <div style={{ fontSize: 14, marginBottom: 4 }}>{h.title}</div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, opacity: 0.5 }}>
            {h.source} · {h.ingested_at?.slice(0, 16)}
          </div>
        </a>
      ))}
    </div>
  );
}