import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, uid, downloadDocument, saved, save } from "./mini-client";

const CATEGORY_META = [
  { id: "research", label: "Research" },
  { id: "files", label: "Create & edit files" },
  { id: "google", label: "Google Workspace" },
  { id: "github", label: "GitHub" },
  { id: "other", label: "Other tools" },
];

function categoryFor(tool) {
  if (tool.name.startsWith("github.")) return "github";
  if (["web.search", "web.read", "research.sources"].includes(tool.name)) return "research";
  if (["documents.", "presentations.", "spreadsheets."].some((prefix) => tool.name.startsWith(prefix))) return "files";
  if (tool.service === "google_workspace" || tool.name.startsWith("google.")) return "google";
  return "other";
}

async function requestStorageKey(fingerprint) {
  try {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(fingerprint));
    const hex = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
    return `tool-request-${hex}`;
  } catch {
    return null;
  }
}

function forgetStoredRequest(key) {
  if (!key) return;
  try {
    sessionStorage.removeItem(`ora2:${key}`);
  } catch {
    // An in-memory request ID still protects retries for the current page.
  }
}

function readable(value) {
  return String(value)
    .replaceAll("_", " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusLabel(status) {
  const labels = {
    awaiting_approval: "Awaiting your approval",
    completed: "Completed",
    failed: "Could not complete",
    rejected: "Rejected",
    expired: "Expired",
    executing: "Running after approval",
    needs_review: "Needs another review",
    running: "Working",
  };
  return labels[status] || readable(status || "Unknown status");
}

function statusTone(status) {
  if (status === "completed") return "success";
  if (["awaiting_approval", "running", "executing", "needs_review"].includes(status)) return "warning";
  if (["failed", "rejected", "expired"].includes(status)) return "danger";
  return "";
}

function ToolField({ field, toolName, value, onChange }) {
  const multiline = ["body", "text", "description", "csv", "files", "slides", "rows", "steps", "patch"].includes(field.name);
  const requiredText = field.required ? "required" : "optional";
  const maxLength = ["patch", "files", "slides", "rows", "steps"].includes(field.name) ? 60000 : 20000;
  let choices = null;
  if (toolName === "phone.action" && field.name === "kind") {
    choices = ["dial", "sms", "maps", "browser", "timer", "alarm"];
  } else if (toolName === "github.issue.update" && field.name === "state") {
    choices = ["open", "closed"];
  } else if (["documents.create", "documents.edit"].includes(toolName) && field.name === "format") {
    choices = ["md", "txt", "docx", "pdf"];
  }

  return (
    <label>
      {field.label} · {requiredText}
      {choices ? (
        <select required={field.required} value={value ?? ""} onChange={(event) => onChange(event.target.value)}>
          {!field.required && <option value="">Keep existing/default</option>}
          {choices.map((choice) => <option key={choice} value={choice}>{readable(choice)}</option>)}
        </select>
      ) : multiline ? (
        <textarea
          rows={["body", "text", "csv", "files", "slides", "rows", "steps", "patch"].includes(field.name) ? 5 : 3}
          maxLength={maxLength}
          required={field.required}
          value={value ?? ""}
          placeholder={["files", "slides", "rows", "headers", "steps"].includes(field.name) ? "Enter the JSON structure described above." : ""}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <input
          type={["priority", "hour", "latitude", "longitude"].includes(field.name) ? "number" : "text"}
          step={["latitude", "longitude"].includes(field.name) ? "any" : "1"}
          min={field.name === "priority" ? 1 : field.name === "hour" ? 0 : undefined}
          max={field.name === "priority" ? 3 : field.name === "hour" ? 23 : undefined}
          maxLength={maxLength}
          required={field.required}
          value={value ?? ""}
          placeholder={[
            "start", "end", "due_at", "expires_at",
          ].includes(field.name) ? "2026-11-02T09:30:00+03:00" : ""}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </label>
  );
}

function Output({ value, full = false }) {
  if (value === null || value === undefined) return <span>Nothing to display.</span>;
  if (typeof value !== "object") return <span>{String(value)}</span>;
  if (Array.isArray(value)) {
    const rows = full ? value : value.slice(0, 100);
    return (
      <div className="tool-results">
        {rows.map((row, index) => <div className="tool-result-item" key={row?.id || row?.path || index}><Output value={row} full={full} /></div>)}
        {!full && value.length > 100 && <p>Showing the first 100 items.</p>}
      </div>
    );
  }
  return (
    <dl className="tool-values">
      {Object.entries(value)
        .filter(([key]) => !["node_id", "avatar_url", "gravatar_id", "_google_connection"].includes(key))
        .map(([key, item]) => (
          <div key={key}>
            <dt>{readable(key)}</dt>
            <dd>
              {typeof item === "string" && /^https:\/\//.test(item) ? (
                <a href={item} target="_blank" rel="noreferrer">Open source ↗</a>
              ) : ["content", "patch", "diff", "text", "body", "excerpt"].includes(key) && typeof item === "string" ? (
                <pre>{item}</pre>
              ) : (
                <Output value={item} full={full} />
              )}
            </dd>
          </div>
        ))}
    </dl>
  );
}

function InputPreview({ tool, args, repo }) {
  const rows = (tool?.fields || [])
    .filter((field) => field.name !== "repo")
    .map((field) => [field.label, args[field.name] || "Not entered"]);
  if (tool?.name.startsWith("github.") && tool.name !== "github.repositories") rows.unshift(["Repository", repo || "Not selected"]);
  if (!rows.length) return <p className="muted">No additional inputs are required.</p>;
  return (
    <dl className="tool-values">
      {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
    </dl>
  );
}

export default function ToolsPage({ onAsk }) {
  const [data, setData] = useState({ tools: [], runs: [], repositories: [], documents: [] });
  const [selected, setSelected] = useState("github.overview");
  const [category, setCategory] = useState("github");
  const [args, setArgs] = useState({});
  const [repo, setRepo] = useState("");
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [announcement, setAnnouncement] = useState("");
  const pendingRequests = useRef(new Map());
  const hasLoaded = useRef(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await api("/tools"));
      hasLoaded.current = true;
    } catch (requestError) {
      const message = requestError.message || "Could not load tools and activity.";
      setError(hasLoaded.current ? `${message} Previously loaded tool data may be out of date.` : message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // These are the live Mini catalog operations. Gmail is intentionally not
  // surfaced here; the rebuild does not offer a Gmail integration.
  const tools = useMemo(
    () => data.tools.filter((tool) => !tool.name.startsWith("email.")),
    [data.tools],
  );
  const categories = CATEGORY_META
    .map((item) => ({ ...item, tools: tools.filter((tool) => categoryFor(tool) === item.id) }))
    .filter((item) => item.tools.length > 0);
  const categoryTools = tools.filter((tool) => categoryFor(tool) === category);
  const visibleTools = categoryTools.filter((tool) =>
    `${tool.title} ${tool.description}`.toLowerCase().includes(filter.toLowerCase()),
  );
  const tool = tools.find((item) => item.name === selected);
  const visibleRuns = data.runs.filter((run) => !run.tool?.startsWith("email."));
  const pending = visibleRuns.filter((run) => run.status === "awaiting_approval");
  const resultTitle = (name) => tools.find((item) => item.name === name)?.title || readable(name);

  useEffect(() => {
    if (!loading && tools.length && !tools.some((item) => item.name === selected)) {
      const firstCategory = categories[0];
      if (firstCategory) {
        setCategory(firstCategory.id);
        setSelected(firstCategory.tools[0].name);
      }
    }
  }, [categories, loading, selected, tools]);

  const chooseCategory = (nextCategory) => {
    setCategory(nextCategory);
    setFilter("");
    setArgs(nextCategory === "github" && repo ? { repo } : {});
    setResult(null);
    const firstTool = tools.find((item) => categoryFor(item) === nextCategory);
    if (firstTool) setSelected(firstTool.name);
  };

  const chooseTool = (nextTool) => {
    setSelected(nextTool.name);
    setArgs({});
    setResult(null);
    setAnnouncement(`${nextTool.title} selected.`);
  };

  const run = async (name = selected, input = args) => {
    setBusy(true);
    setError("");
    setAnnouncement("Preparing tool request…");
    const requestArgs = {
      ...input,
      ...(name.startsWith("github.") && name !== "github.repositories" ? { repo: input.repo || repo } : {}),
    };
    const fingerprint = JSON.stringify([name, requestArgs]);
    const storageKey = await requestStorageKey(fingerprint);
    const request_id = pendingRequests.current.get(fingerprint)
      || (storageKey ? saved(storageKey) : null)
      || uid();
    pendingRequests.current.set(fingerprint, request_id);
    if (storageKey) {
      try { save(storageKey, request_id); } catch { /* Keep the in-memory retry ID if storage is unavailable. */ }
    }
    try {
      const response = await api("/tools/run", { name, args: requestArgs, request_id });
      pendingRequests.current.delete(fingerprint);
      forgetStoredRequest(storageKey);
      setResult(response);
      setAnnouncement(`${resultTitle(name)}: ${statusLabel(response.status)}.`);
      await refresh();
    } catch (requestError) {
      if (requestError.status && requestError.status < 500) {
        pendingRequests.current.delete(fingerprint);
        forgetStoredRequest(storageKey);
      }
      setError(requestError.message || "Tool request failed. Your entered values are still here.");
      setAnnouncement("Tool request failed. Review the error and retry when safe; an identical retry reuses its request ID.");
    } finally {
      setBusy(false);
    }
  };

  const decide = async (id, reject) => {
    setBusy(true);
    setError("");
    setAnnouncement(reject ? "Rejecting proposal…" : "Approving the exact proposal…");
    try {
      const response = await api(`/tools/actions/${encodeURIComponent(id)}`, { reject });
      setResult(response);
      setAnnouncement(`Action ${statusLabel(response.status).toLowerCase()}.`);
      await refresh();
    } catch (requestError) {
      setError(requestError.message || "Could not update this proposal.");
      setAnnouncement("The action decision did not complete.");
    } finally {
      setBusy(false);
    }
  };

  const download = async (id, name) => {
    setError("");
    try {
      await downloadDocument(id, name);
      setAnnouncement(`${name} download started.`);
    } catch (requestError) {
      setError(requestError.message || "File download failed.");
    }
  };

  const selectRepository = (event) => {
    const nextRepo = event.target.value;
    setRepo(nextRepo);
    setArgs((current) => ({ ...current, repo: nextRepo }));
  };

  const activeToolStatus = tool
    ? !tool.enabled ? "Disabled by you"
      : !tool.connected ? "Needs a connection"
        : tool.approval ? "Prepare for your review"
          : "Read-only or handoff"
    : "";

  return (
    <section className="tools-page" aria-busy={loading}>
      <header className="page-heading">
        <div>
          <span className="eyebrow">ACTIONS WITH CLEAR BOUNDARIES</span>
          <h1>Tools & activity</h1>
          <p>Read tools return information. Write tools prepare an exact proposal for your approval; ORA does not approve it for you.</p>
        </div>
        <button className="button secondary" type="button" disabled={loading || busy} onClick={refresh}>Refresh tools</button>
      </header>

      {error && <p className="tool-error" role="alert">{error}</p>}
      <p className="sr-only" role="status" aria-live="polite">{announcement}</p>

      {loading && !data.tools.length ? (
        <div className="panel"><p role="status">Loading the available tools…</p></div>
      ) : error && !data.tools.length ? (
        <div className="panel"><p>No tools loaded. Retry to check the current backend catalog.</p><button className="button secondary" type="button" onClick={refresh}>Retry</button></div>
      ) : (
        <>
          <div className="tool-categories" role="group" aria-label="Tool categories">
            {categories.map((item) => (
              <button key={item.id} type="button" aria-pressed={category === item.id} onClick={() => chooseCategory(item.id)}>
                {item.label} <span>({item.tools.length})</span>
              </button>
            ))}
          </div>

          <div className="tool-workspace">
            <aside aria-label="Available tools">
              <label>
                Find an action
                <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Search tools" />
              </label>
              {visibleTools.length ? visibleTools.map((item) => (
                <button key={item.name} type="button" className={item.name === selected ? "selected" : ""} aria-pressed={item.name === selected} onClick={() => chooseTool(item)}>
                  {item.title}
                  <small>{!item.enabled ? "Disabled" : !item.connected ? "Needs connection" : item.approval ? "Review before changes" : "Read-only or device handoff"}</small>
                </button>
              )) : <p className="muted">No tools match this search.</p>}
            </aside>

            <div className="tool-main">
              {tool ? (
                <form onSubmit={(event) => { event.preventDefault(); run(); }}>
                  <div className="section-heading">
                    <h2>{tool.title}</h2>
                    <span className={`status-pill ${tool.connected && tool.enabled ? "success" : "warning"}`}>{activeToolStatus}</span>
                  </div>
                  <p>{tool.description}</p>
                  {!tool.connected && <p className="muted">This tool needs a server-side connection before it can run. No connection credentials are entered here.</p>}
                  {tool.name.startsWith("github.") && tool.name !== "github.repositories" && (
                    <label>
                      Repository <span aria-hidden="true">· required</span>
                      <select required value={repo} onChange={selectRepository}>
                        <option value="">Choose an allowed repository</option>
                        {data.repositories.map((repository) => <option key={repository} value={repository}>{repository}</option>)}
                      </select>
                      {!data.repositories.length && <small>No repositories are allowed in the backend configuration yet.</small>}
                    </label>
                  )}
                  {tool.fields.filter((field) => field.name !== "repo").map((field) => (
                    <ToolField
                      key={field.name}
                      field={field}
                      toolName={tool.name}
                      value={args[field.name]}
                      onChange={(value) => setArgs((current) => ({ ...current, [field.name]: value }))}
                    />
                  ))}
                  <div className="tool-preview" aria-label="Request preview">
                    <h3>Review your inputs</h3>
                    <InputPreview tool={tool} args={args} repo={repo} />
                  </div>
                  <div className="button-row">
                    <button
                      className="button primary"
                      type="submit"
                      disabled={busy || loading || !tool.connected || !tool.enabled || (tool.name.startsWith("github.") && tool.name !== "github.repositories" && !repo)}
                    >
                      {busy ? "Working…" : tool.approval ? "Prepare for review" : tool.name === "phone.action" ? "Prepare phone handoff" : "Run read-only tool"}
                    </button>
                    <button className="button secondary" type="button" onClick={() => onAsk(`Help me use ${tool.title}${repo ? ` for ${repo}` : ""}. Ask for any missing details first, then explain whether the next step needs my approval.`)}>Ask ORA about this</button>
                    <button className="button quiet" type="button" disabled={busy} onClick={async () => {
                      setError("");
                      try {
                        await api("/tools/settings", { name: tool.name, enabled: !tool.enabled });
                        await refresh();
                      } catch (requestError) {
                        setError(requestError.message || "Could not update this tool preference.");
                      }
                    }}>{tool.enabled ? "Disable tool" : "Enable tool"}</button>
                  </div>
                </form>
              ) : (
                <div className="panel"><p>Select a tool to see its inputs and next step.</p></div>
              )}

              {result && (
                <article className="tool-result" aria-busy={busy}>
                  <div className="section-heading">
                    <h2>{resultTitle(result.tool || selected)}</h2>
                    <span className={`status-pill ${statusTone(result.status)}`}>{statusLabel(result.status)}</span>
                  </div>
                  {result.error && <p className="tool-error" role="alert">{result.error}</p>}
                  {result.status === "awaiting_approval" && <p className="muted">This is a proposal only. Review the exact preview below, then approve it from the review queue.</p>}
                  {result.status === "completed" && result.tool?.startsWith("github.") && <p className="muted">This result is from a read-only repository tool. ORA did not change or execute repository code.</p>}
                  {result.result?.handoff_url && /^(https:|sms:|tel:)/.test(result.result.handoff_url) && <a className="button secondary" href={result.result.handoff_url}>Open on this device</a>}
                  {result.result?.native_action && <p className="muted">Open this handoff in the Android companion to review it in the matching app. Nothing has been run yet.</p>}
                  {result.result?.document_id && <button className="button secondary" type="button" onClick={() => download(result.result.document_id, result.result.name)}>Download saved file</button>}
                  {result.tool === "github.tree" && result.result?.files ? (
                    <div className="tool-file-list">
                      {result.result.files.filter((file) => file.type === "blob").map((file) => (
                        <button key={file.path} type="button" disabled={busy} onClick={() => run("github.file", { repo: result.args.repo, path: file.path, ref: result.result.sha })}>{file.path}</button>
                      ))}
                    </div>
                  ) : <Output value={result.status === "awaiting_approval" ? result.preview : result.result || result.preview} full={result.status === "awaiting_approval"} />}
                  {result.tool === "github.builds" && Array.isArray(result.result) && result.result.map((buildRun) => (
                    <button key={buildRun.id} className="button secondary" type="button" disabled={busy} onClick={() => run("github.build", { repo: result.args.repo, run_id: buildRun.id })}>Inspect {buildRun.name} · {buildRun.conclusion || buildRun.status}</button>
                  ))}
                  {result.tool === "routines.list" && Array.isArray(result.result) && result.result.map((routine) => (
                    <button key={routine.id} className="button secondary" type="button" disabled={!routine.enabled || busy} onClick={async () => {
                      try {
                        await api(`/routines/${encodeURIComponent(routine.id)}/disable`, {});
                        await run("routines.list", {});
                      } catch (requestError) {
                        setError(requestError.message || "Could not disable this routine.");
                      }
                    }}>Disable {routine.name}</button>
                  ))}
                </article>
              )}

              <section aria-labelledby="saved-files-heading" className="tool-cockpit">
                <h2 id="saved-files-heading">Saved files</h2>
                <p className="muted">Approved file outputs are stored in your ORA workspace. Downloading a file does not create a new proposal.</p>
                {data.documents.length ? data.documents.map((file) => (
                  <div className="tool-saved-file" key={file.id}>
                    <div><strong>{file.name}</strong><small>Version {file.version || 1} · {readable(file.kind || "document")}</small></div>
                    <div className="button-row">
                      <button className="button secondary" type="button" onClick={() => download(file.id, file.name)}>Download</button>
                      <button className="button quiet" type="button" onClick={() => onAsk(`Read my saved file ${file.id} (${file.name}, version ${file.version}), then help me revise it. Prepare the exact replacement for my review.`)}>Ask ORA to revise</button>
                    </div>
                  </div>
                )) : <p>No saved files yet.</p>}
              </section>

              <section aria-labelledby="review-queue-heading">
                <div className="section-heading"><h2 id="review-queue-heading">Review queue · {pending.length}</h2><span className="muted">Each approval applies only to the preview shown.</span></div>
                {pending.length ? pending.map((run) => (
                  <article key={run.id} className="tool-result">
                    <div className="section-heading">
                      <h3>{resultTitle(run.tool)}</h3>
                      <span className="status-pill warning">Awaiting your decision</span>
                    </div>
                    <p><strong>Exact action preview</strong></p>
                    <Output value={run.preview} full />
                    <div className="button-row">
                      <button className="button primary" type="button" disabled={busy} onClick={() => decide(run.id, false)}>Approve this exact action</button>
                      <button className="button destructive" type="button" disabled={busy} onClick={() => decide(run.id, true)}>Reject proposal</button>
                    </div>
                  </article>
                )) : <div className="panel"><p>No tool actions are waiting for approval.</p></div>}
              </section>

              <section aria-labelledby="activity-heading" className="tool-activity">
                <div className="section-heading"><h2 id="activity-heading">Activity</h2><span className="muted">Recent tool results and proposals</span></div>
                {[...visibleRuns].slice(-30).reverse().map((run) => (
                  <button className="tool-history" type="button" key={run.id} onClick={async () => {
                    setError("");
                    try {
                      const details = await api(`/tools/runs/${encodeURIComponent(run.id)}`);
                      setResult(details);
                      setAnnouncement(`${resultTitle(details.tool)}: ${statusLabel(details.status)}.`);
                    } catch (requestError) {
                      setError(requestError.message || "Could not load this activity item.");
                    }
                  }}>
                    <span>{resultTitle(run.tool)}<small>{statusLabel(run.status)}</small></span>
                    <time dateTime={new Date(run.created * 1000).toISOString()}>{new Date(run.created * 1000).toLocaleString()}</time>
                  </button>
                ))}
                {!visibleRuns.length && <div className="panel"><p>No tool activity yet. Read results and reviewable proposals will appear here.</p></div>}
              </section>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
