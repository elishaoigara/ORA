import { useEffect, useState } from "react";
import { api, uid } from "./mini-client";

function Output({ value }) {
  if (value === null || value === undefined) return null;
  if (typeof value !== "object") return <span>{String(value)}</span>;
  if (Array.isArray(value))
    return (
      <div className="tool-results">
        {value.slice(0, 100).map((v, i) => (
          <div className="tool-result-item" key={i}>
            <Output value={v} />
          </div>
        ))}
        {value.length > 100 && <p>Showing the first 100 items.</p>}
      </div>
    );
  return (
    <dl className="tool-values">
      {Object.entries(value)
        .filter(
          ([k]) => !["node_id", "avatar_url", "gravatar_id", "url"].includes(k),
        )
        .map(([k, v]) => (
          <div key={k}>
            <dt>{k.replaceAll("_", " ")}</dt>
            <dd>
              {["content", "patch", "diff", "text", "body", "excerpt"].includes(
                k,
              ) && typeof v === "string" ? (
                <pre>{v}</pre>
              ) : typeof v === "string" && /^https:\/\//.test(v) ? (
                <a href={v} target="_blank" rel="noreferrer">
                  Open source ↗
                </a>
              ) : (
                <Output value={v} />
              )}
            </dd>
          </div>
        ))}
    </dl>
  );
}
export default function ToolsPage({ onAsk }) {
  const [data, setData] = useState({ tools: [], runs: [], repositories: [] });
  const [selected, setSelected] = useState("github.overview");
  const [args, setArgs] = useState({});
  const [repo, setRepo] = useState("");
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const refresh = async () => setData(await api("/tools"));
  useEffect(() => {
    let alive = true;
    const load = () =>
      api("/tools")
        .then((d) => {
          if (alive) setData(d);
        })
        .catch((e) => {
          if (alive) setError(e.message);
        });
    load();
    const timer = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
  const tool = data.tools.find((t) => t.name === selected);
  const run = async (name = selected, input = args) => {
    setBusy(true);
    setError("");
    try {
      const r = await api("/tools/run", {
        name,
        args: {
          ...input,
          ...(name.startsWith("github.") && name !== "github.repositories"
            ? { repo: input.repo || repo }
            : {}),
        },
        request_id: uid(),
      });
      setResult(r);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const decide = async (id, reject) => {
    setBusy(true);
    try {
      const r = await api("/tools/actions/" + id, { reject });
      setResult(r);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const choose = (name, input = {}) => {
    setSelected(name);
    setArgs(input);
    setResult(null);
  };
  const pending = data.runs.filter((r) => r.status === "awaiting_approval");
  const download = (r) => {
    const content = r.result?.text;
    if (typeof content !== "string") return;
    const url = URL.createObjectURL(
      new Blob([content], { type: "text/plain;charset=utf-8" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = (r.result.name || "ora-document.txt").replace(
      /[^a-zA-Z0-9._-]/g,
      "_",
    );
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <section className="tools-page">
      <span className="eyebrow">YOUR WORK, CONNECTED</span>
      <h1>Tools & GitHub</h1>
      <p>
        Ask ORA to combine tools in chat, or run a focused action here. Writes
        require your review.
      </p>
      {error && (
        <p role="alert" className="tool-error">
          {error}
        </p>
      )}
      <div className="tool-cockpit">
        <h2>GitHub workspace</h2>
        <label>
          Repository
          <select value={repo} onChange={(e) => setRepo(e.target.value)}>
            <option value="">Choose a repository</option>
            {data.repositories.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>
        <div className="tool-shortcuts">
          {[
            ["github.overview", "Overview"],
            ["github.tree", "Browse files"],
            ["github.issues", "Issues"],
            ["github.builds", "Builds"],
          ].map(([name, label]) => (
            <button
              key={name}
              disabled={busy || !repo}
              onClick={() => run(name, { repo })}
            >
              {label}
            </button>
          ))}
          <button
            disabled={!repo}
            onClick={() =>
              onAsk(
                `Inspect ${repo}, summarize its current state and failing builds, and recommend my next useful engineering task. Use actual tool results and cite repository paths and commits.`,
              )
            }
          >
            Ask ORA to investigate
          </button>
        </div>
        <p className="muted">
          Allowed repositories come from your backend connection settings.
          Changes create draft pull requests; merging remains a separate
          decision.
        </p>
      </div>
      <div className="tool-workspace">
        <aside>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Find a tool"
            aria-label="Find a tool"
          />
          {data.tools
            .filter((t) =>
              (t.title + " " + t.service)
                .toLowerCase()
                .includes(filter.toLowerCase()),
            )
            .map((t) => (
              <button
                className={t.name === selected ? "selected" : ""}
                key={t.name}
                onClick={() => choose(t.name)}
              >
                {t.title}
                <small>
                  {!t.enabled
                    ? "Disabled"
                    : !t.connected
                      ? "Needs connection"
                      : t.approval
                        ? "Review before action"
                        : "Ready"}
                </small>
              </button>
            ))}
        </aside>
        <div className="tool-main">
          {tool && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                run();
              }}
            >
              <h2>{tool.title}</h2>
              <p>{tool.description}</p>
              {tool.fields
                .filter((f) => f.name !== "repo")
                .map((f) => (
                  <label key={f.name}>
                    {f.label}
                    {!f.required ? " (optional)" : ""}
                    <textarea
                      rows={
                        ["body", "text", "csv", "files", "steps"].includes(
                          f.name,
                        )
                          ? 5
                          : 2
                      }
                      required={f.required}
                      value={args[f.name] ?? ""}
                      onChange={(e) =>
                        setArgs({ ...args, [f.name]: e.target.value })
                      }
                    />
                  </label>
                ))}
              <button
                disabled={
                  busy ||
                  !tool.connected ||
                  !tool.enabled ||
                  (selected.startsWith("github.") &&
                    selected !== "github.repositories" &&
                    !repo)
                }
              >
                {busy
                  ? "Working…"
                  : tool.approval
                    ? "Prepare for review"
                    : "Run tool"}
              </button>
              <button
                type="button"
                onClick={() =>
                  onAsk(
                    `Help me use ${tool.title}${repo ? " for " + repo : ""}. Ask for any missing details before taking action.`,
                  )
                }
              >
                Work through this with ORA
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={async () => {
                  try {
                    await api("/tools/settings", {
                      name: tool.name,
                      enabled: !tool.enabled,
                    });
                    await refresh();
                  } catch (e) {
                    setError(e.message);
                  }
                }}
              >
                {tool.enabled ? "Disable this tool" : "Enable this tool"}
              </button>
            </form>
          )}
          {result && (
            <article className="tool-result">
              <h2>
                {data.tools.find((t) => t.name === result.tool)?.title ||
                  result.tool}
              </h2>
              <strong>{result.status.replaceAll("_", " ")}</strong>
              {result.error && <p role="alert">{result.error}</p>}
              {result.result?.handoff_url &&
                /^(https:|sms:|tel:)/.test(result.result.handoff_url) && (
                  <a href={result.result.handoff_url}>Open on this device ↗</a>
                )}
              {result.result?.native_action && (
                <p>
                  Open this result in the Android companion’s Tools & activity
                  to continue in your clock app.
                </p>
              )}
              {result.result?.document_id && (
                <button onClick={() => download(result)}>
                  Download document
                </button>
              )}
              {result.tool === "github.tree" && result.result?.files ? (
                <div className="tool-file-list">
                  {result.result.files
                    .filter((f) => f.type === "blob")
                    .map((f) => (
                      <button
                        key={f.path}
                        disabled={busy}
                        onClick={() =>
                          run("github.file", {
                            repo: result.args.repo,
                            path: f.path,
                            ref: result.result.sha,
                          })
                        }
                      >
                        {f.path}
                      </button>
                    ))}
                </div>
              ) : (
                <Output value={result.result || result.preview} />
              )}
              {result.tool === "github.builds" &&
                Array.isArray(result.result) &&
                result.result.map((r) => (
                  <button
                    key={r.id}
                    disabled={busy}
                    onClick={() =>
                      run("github.build", {
                        repo: result.args.repo,
                        run_id: r.id,
                      })
                    }
                  >
                    Inspect {r.name} · {r.conclusion || r.status}
                  </button>
                ))}
              {result.tool === "routines.list" &&
                Array.isArray(result.result) &&
                result.result.map((r) => (
                  <button
                    key={r.id}
                    disabled={!r.enabled || busy}
                    onClick={async () => {
                      await api("/routines/" + r.id + "/disable", {});
                      run("routines.list", {});
                    }}
                  >
                    Disable {r.name}
                  </button>
                ))}
            </article>
          )}
          <h2>Awaiting your review · {pending.length}</h2>
          {pending.map((r) => (
            <article key={r.id} className="tool-result">
              <h3>
                {data.tools.find((t) => t.name === r.tool)?.title || r.tool}
              </h3>
              <Output value={r.preview} />
              <button
                disabled={busy || r.expires * 1000 < Date.now()}
                onClick={() => decide(r.id, false)}
              >
                Approve this exact action
              </button>
              <button disabled={busy} onClick={() => decide(r.id, true)}>
                Reject
              </button>
            </article>
          ))}
          <h2>Activity</h2>
          {[...data.runs].reverse().map((r) => (
            <button
              className="tool-history"
              key={r.id}
              onClick={async () => {
                try {
                  setResult(await api("/tools/runs/" + r.id));
                } catch (e) {
                  setError(e.message);
                }
              }}
            >
              {r.tool} · {r.status.replaceAll("_", " ")}
              <small>{new Date(r.created * 1000).toLocaleString()}</small>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
