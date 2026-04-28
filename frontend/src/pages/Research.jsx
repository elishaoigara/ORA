import { useState } from "react";

const API_BASE = "https://ora-oovf.onrender.com";

export default function Research() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);

  const runResearch = async () => {
    if (!query.trim()) return;

    try {
      setLoading(true);
      setResult("");

      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: query,
        }),
      });

      const data = await res.json();

      setResult(
        data.response ||
        data.message ||
        JSON.stringify(data, null, 2)
      );
    } catch (err) {
      console.error(err);
      setResult("❌ Failed to connect to ORA backend");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ora-container">
      <div className="main">
        <h1>ORA Research Agent</h1>

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask anything..."
        />

        <button onClick={runResearch} disabled={loading}>
          {loading ? "Researching..." : "Run Research"}
        </button>

        <div className="result">
          {result}
        </div>
      </div>
    </div>
  );
}