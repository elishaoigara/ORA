import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, uid, saved, save } from "./mini-client";
import "./WorkPage.css";
const blank = {
  name: "",
  repository: "",
  goal: "",
  next_step: "",
  blockers: "",
  branch: "",
  github_alerts: false,
  archived: false,
};
const fields = {
  name: "Project name",
  repository: "GitHub repository (owner/repository)",
  goal: "Goal",
  next_step: "Next step",
  blockers: "Blockers",
  branch: "Working branch",
};
const jobStatusTone = (status) => status === "completed"
  ? "success"
  : ["queued", "running", "awaiting_approval"].includes(status)
    ? "warning"
    : ["failed", "needs_review", "expired"].includes(status)
      ? "danger"
      : "";

async function workChatStorageKey(fingerprint) {
  try {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(fingerprint));
    const hex = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
    return `work-chat-request-${hex}`;
  } catch {
    return null;
  }
}

function forgetWorkChatRequest(key) {
  if (!key) return;
  try {
    sessionStorage.removeItem(`ora2:${key}`);
  } catch {
    // An in-memory request ID still protects retries while this view is open.
  }
}
export default function WorkPage() {
  const [diagnostics, setDiagnostics] = useState(null);
  const [data, setData] = useState(null),
    [desktop, setDesktop] = useState({ workers: [], jobs: [] });
  const [project, setProject] = useState(blank),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const [fact, setFact] = useState({
      text: "",
      source: "Owner note",
      expires_at: "",
    }),
    [prompt, setPrompt] = useState(""),
    [reply, setReply] = useState("");
  const [attachments, setAttachments] = useState([]),
    [code, setCode] = useState(""),
    [resume, setResume] = useState(null);
  const pendingQuestions = useRef(new Map());
  const [job, setJob] = useState({
    worker_id: "",
    repository: "",
    check: "",
    base_sha: "",
    patch: "",
  });
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [w, d] = await Promise.all([api("/work"), api("/desktop")]);
      setData(w);
      setDesktop(d);
      setError("");
      return { work: w, desktop: d };
    } catch (e) {
      const message = `Refresh failed: ${e.message || "Could not load projects and desktop activity."} Any previously loaded workspace details may be out of date.`;
      setError(message);
      throw new Error(message);
    } finally {
      setLoading(false);
    }
  }, []);
  async function run(fn, shouldRefresh = true) {
    setBusy(true);
    setError("");
    try {
      await fn();
      if (shouldRefresh) await refresh();
    } catch (e) {
      setError(e.message || "That request could not be completed.");
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);
  function select(p) {
    setProject(p);
    setResume(null);
    setReply("");
    setAttachments([]);
    setFact({ text: "", source: "Owner note", expires_at: "" });
  }
  const docs = (data?.documents || []).filter(
    (d) => d.project_id === project.id,
  );
  const facts = (data?.facts || []).filter((f) => f.project_id === project.id);
  const worker = desktop.workers.find((w) => w.id === job.worker_id);
  return (
    <section className="ora-work" aria-busy={loading}>
      <header>
        <p className="eyebrow">YOUR WORK, REMEMBERED</p>
        <h1>Projects & desktop</h1>
        <p>
          Pick up where you left off. Keep decisions, evidence and next steps
          together.
        </p>
        <button className="button secondary" type="button" disabled={busy || loading} onClick={() => run(refresh, false)}>
          Refresh activity
        </button>
      </header>
      {error && (
        <p role="alert" className="work-error">
          {error}
        </p>
      )}
      {loading && !data ? (
        <div className="work-panel"><p role="status">Loading your projects and desktop status…</p></div>
      ) : !data ? (
        <div className="work-panel"><p>Projects and desktop activity are not available yet.</p><button type="button" disabled={loading} onClick={() => refresh().catch(() => {})}>Retry</button></div>
      ) : (
      <div className="work-layout">
        <aside className="work-panel">
          <h2>Your projects</h2>
          <button className="button secondary" type="button" disabled={busy} onClick={() => select(blank)}>
            + New project
          </button>
          {(data?.projects || []).map((p) => (
            <button
              key={p.id}
              type="button"
              aria-pressed={p.id === project.id}
              disabled={busy}
              onClick={() => select(p)}
            >
              {p.name}
              {p.archived ? " · archived" : ""}
            </button>
          ))}
          <h3>Connections</h3>
          <button
            className="button secondary"
            type="button"
            disabled={busy}
            onClick={() =>
              run(async () =>
                setDiagnostics(await api("/work/diagnostics", {})),
              )
            }
          >
            Test connections
          </button>
          {diagnostics?.checks.map((check) => (
            <p key={check.name}>
              <strong>{check.name}: </strong>
              <span className={`status-pill ${jobStatusTone(check.status)}`}>{check.status}</span>
              <br />
              {check.detail}
            </p>
          ))}
          <p>
            GitHub token:{" "}
            {data?.connections.github_token_configured
              ? "configured"
              : "missing"}
          </p>
          <p>
            Webhook:{" "}
            {data?.connections.webhook_configured ? "configured" : "missing"}
          </p>
          <p>
            Image analysis:{" "}
            {data?.connections.vision_configured ? "configured" : "missing"}
          </p>
          <small>
            Configuration is not a live provider test. Use Tools & GitHub to
            make a repository read; upload an image to test vision.
          </small>
        </aside>
        <div>
          <form
            className="work-panel"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                setProject(
                  await api("/work/projects", {
                    ...project,
                    request_id: uid(),
                  }),
                );
              });
            }}
          >
            <h2>{project.id ? "Project workspace" : "Create a project"}</h2>
            {Object.entries(fields).map(([key, label]) => (
              <label key={key}>
                {label}
                {["goal", "next_step", "blockers"].includes(key) ? (
                  <textarea
                    maxLength={2000}
                    value={project[key]}
                    onChange={(e) =>
                      setProject({ ...project, [key]: e.target.value })
                    }
                  />
                ) : (
                  <input
                    required={key === "name"}
                    maxLength={key === "name" ? 80 : 160}
                    value={project[key]}
                    onChange={(e) =>
                      setProject({ ...project, [key]: e.target.value })
                    }
                  />
                )}
              </label>
            ))}
            <label className="work-check">
              <input
                type="checkbox"
                checked={project.github_alerts}
                onChange={(e) =>
                  setProject({ ...project, github_alerts: e.target.checked })
                }
              />
              GitHub alerts for this repository
            </label>
            <label className="work-check">
              <input
                type="checkbox"
                checked={project.archived}
                onChange={(e) =>
                  setProject({ ...project, archived: e.target.checked })
                }
              />
              Archive project
            </label>
            <button className="button primary" type="submit" disabled={busy}>Save project</button>
          </form>
          {project.id && (
            <>
              <div className="work-panel">
                <h2>Resume my work</h2>
                <button
                  className="button secondary"
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    run(async () =>
                      setResume(
                        await api(`/work/projects/${project.id}/resume`),
                      ),
                    )
                  }
                >
                  Show saved context
                </button>
                {resume && (
                  <>
                    <h3>{resume.project.name}</h3>
                    <p>
                      <strong>Goal:</strong> {resume.project.goal || "Not set"}
                    </p>
                    <p>
                      <strong>Next:</strong>{" "}
                      {resume.project.next_step || "Not set"}
                    </p>
                    <p>
                      <strong>Blockers:</strong>{" "}
                      {resume.project.blockers || "None recorded"}
                    </p>
                    <small>
                      Last saved{" "}
                      {new Date(resume.project.updated_at).toLocaleString()} ·{" "}
                      {resume.facts.length} active facts
                    </small>
                    {resume.messages?.map((m) => (
                      <article key={m.id}>
                        <small>{m.role}</small>
                        <ReactMarkdown>{m.text}</ReactMarkdown>
                      </article>
                    ))}
                  </>
                )}
              </div>
              <div className="work-panel">
                <h2>Decisions & memory</h2>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    run(async () => {
                      await api("/work/facts", {
                        ...fact,
                        expires_at: fact.expires_at
                          ? new Date(fact.expires_at).toISOString()
                          : null,
                        project_id: project.id,
                        request_id: uid(),
                      });
                      setFact({
                        text: "",
                        source: "Owner note",
                        expires_at: "",
                      });
                    });
                  }}
                >
                  <label>
                    Fact or decision
                    <textarea
                      required
                      maxLength={2000}
                      value={fact.text}
                      onChange={(e) =>
                        setFact({ ...fact, text: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Source
                    <input
                      required
                      maxLength={240}
                      value={fact.source}
                      onChange={(e) =>
                        setFact({ ...fact, source: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Optional expiry
                    <input
                      type="datetime-local"
                      value={fact.expires_at}
                      onChange={(e) =>
                        setFact({ ...fact, expires_at: e.target.value })
                      }
                    />
                  </label>
                  <button className="button primary" type="submit" disabled={busy}>
                    {fact.id ? "Save correction" : "Remember this"}
                  </button>
                </form>
                {facts.map((f) => (
                  <article key={f.id}>
                    <p>{f.text}</p>
                    <small>
                      {f.source} · {new Date(f.updated_at).toLocaleString()}
                      {f.expires_at
                        ? ` · ${new Date(f.expires_at) < new Date() ? "Expired" : "Expires"} ${new Date(f.expires_at).toLocaleString()}`
                        : ""}
                    </small>
                    <div>
                      <button
                        className="button secondary"
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          setFact({
                            ...f,
                            expires_at: f.expires_at
                              ? new Date(
                                  new Date(f.expires_at).getTime() -
                                    new Date(f.expires_at).getTimezoneOffset() *
                                      60000,
                                )
                                  .toISOString()
                                  .slice(0, 16)
                              : "",
                          })
                        }
                      >
                        Correct
                      </button>
                      <button
                        className="button destructive"
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          if (!window.confirm("Forget this project fact? It will be removed from future project context.")) return;
                          run(() => api("/work/facts", {
                            ...f,
                            deleted: true,
                            request_id: uid(),
                          }));
                        }}
                      >
                        Forget
                      </button>
                    </div>
                  </article>
                ))}
              </div>
              <div className="work-panel">
                <h2>Ask ORA about this project</h2>
                <p>
                  Attach PNG/JPEG, text, Markdown, CSV, logs or a readable PDF.
                  Up to 2 MB. Images are sent to the configured vision provider;
                  only their generated description is saved.
                </p>
                <label>
                  Upload an attachment
                  <input
                    disabled={busy}
                    type="file"
                    accept=".png,.jpg,.jpeg,.pdf,.txt,.md,.csv,.log"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      if (file.size > 2 * 1024 * 1024) {
                        setError("Files must be 2 MB or smaller. The attachment was not uploaded.");
                        e.target.value = "";
                        return;
                      }
                      run(async () => {
                        const f = new FormData();
                        f.append("file", file);
                        f.append("project_id", project.id);
                        const d = await api("/work/attachments", f);
                        setAttachments([d.id]);
                      });
                      e.target.value = "";
                    }}
                  />
                </label>
                {docs.map((d) => (
                  <div key={d.id}>
                    <label className="work-check">
                      <input
                        type="checkbox"
                        checked={attachments.includes(d.id)}
                        disabled={
                          busy ||
                          (!attachments.includes(d.id) &&
                            attachments.length >= 3)
                        }
                        onChange={() =>
                          setAttachments(
                            attachments.includes(d.id)
                              ? attachments.filter((id) => id !== d.id)
                              : [...attachments, d.id],
                          )
                        }
                      />
                      {d.name}
                      {d.analysis_kind === "ai_image_description"
                        ? " · AI description"
                        : ""}
                    </label>
                    <button
                      className="button destructive"
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        if (!window.confirm(`Remove “${d.name}” from this project? This deletes the saved attachment.`)) return;
                        run(async () => {
                          await api("/operations", {
                            kind: "document.delete",
                            payload: { id: d.id },
                            request_id: uid(),
                          });
                          setAttachments((a) => a.filter((x) => x !== d.id));
                        });
                      }}
                    >
                      Remove document
                    </button>
                  </div>
                ))}
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const question = { text: prompt, project_id: project.id, document_ids: attachments };
                    const fingerprint = JSON.stringify(question);
                    run(async () => {
                      const storageKey = await workChatStorageKey(fingerprint);
                      const request_id = pendingQuestions.current.get(fingerprint)
                        || (storageKey ? saved(storageKey) : null)
                        || uid();
                      pendingQuestions.current.set(fingerprint, request_id);
                      if (storageKey) {
                        try { save(storageKey, request_id); } catch { /* Keep the in-memory retry ID if storage is unavailable. */ }
                      }
                      try {
                        const r = await api("/chat", { request_id, ...question });
                        pendingQuestions.current.delete(fingerprint);
                        forgetWorkChatRequest(storageKey);
                        setReply(r.reply);
                        setPrompt("");
                      } catch (requestError) {
                        if (requestError.status && requestError.status < 500) {
                          pendingQuestions.current.delete(fingerprint);
                          forgetWorkChatRequest(storageKey);
                        }
                        throw requestError;
                      }
                    });
                  }}
                >
                  <label>
                    Your question
                    <textarea
                      required
                      maxLength={8000}
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                    />
                  </label>
                  <button className="button primary" type="submit" disabled={busy}>Ask ORA</button>
                </form>
                {reply && <ReactMarkdown>{reply}</ReactMarkdown>}
                <small>
                  Any proposed actions appear in Tools & GitHub or the existing
                  approval queue.
                </small>
              </div>
              <div className="work-panel">
                <h2>GitHub updates</h2>
                {(data?.events || [])
                  .filter(
                    (e) =>
                      e.repository.toLowerCase() ===
                      project.repository.toLowerCase(),
                  )
                  .reverse()
                  .map((e) => (
                    <article key={e.id}>
                      <a href={e.url} target="_blank" rel="noreferrer">
                        {e.title}
                      </a>
                      <p>{new Date(e.created_at).toLocaleString()}</p>
                    </article>
                  ))}
                <small>
                  Events appear after the webhook is configured. Push delivery
                  follows quiet hours and the notification scheduler.
                </small>
              </div>
            </>
          )}
          <div className="work-panel">
            <h2>Your computers</h2>
            <button
              className="button primary"
              type="button"
              disabled={busy}
              onClick={() =>
                run(async () =>
                  setCode((await api("/desktop/pairing-code", {})).code),
                )
              }
            >
              Create worker pairing code
            </button>
            {code && (
              <p>
                <code>{code}</code>
                <br />
                Valid for 10 minutes. Enter it on your computer.
              </p>
            )}
            {desktop.workers.map((w) => (
              <article key={w.id}>
                <strong>{w.label}</strong>
                <p><span className={`status-pill ${w.revoked ? "danger" : w.online ? "success" : "warning"}`}>
                  {w.revoked ? "Revoked" : w.online ? "Online" : "Offline — queued work waits"}
                </span></p>
                {!w.revoked && (
                  <button
                    className="button destructive"
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      if (!window.confirm(`Revoke ${w.label}? This stops future ORA desktop jobs for that computer. Existing local files are not removed.`)) return;
                      run(() => api("/desktop/revoke", { id: w.id }));
                    }}
                  >
                    Revoke worker
                  </button>
                )}
              </article>
            ))}
          </div>
          {project.id && (
            <form
              className="work-panel"
              onSubmit={(e) => {
                e.preventDefault();
                const workerLabel = worker?.label || "the selected computer";
                const patchSummary = job.patch ? ` A ${job.patch.length}-character patch (base ${job.base_sha || "not specified"}) is attached; inspect the exact diff on the computer before approving.` : " No patch is attached.";
                if (!window.confirm(`Queue “${job.check}” for ${job.repository} on ${workerLabel}?${patchSummary} This creates a queued request only; the local owner must review and approve it before any code runs.`)) return;
                run(() => api("/desktop/jobs", {
                  ...job,
                  project_id: project.id,
                  request_id: uid(),
                }));
              }}
            >
              <h2>Queue a desktop check</h2>
              <p>
                Review the exact check and optional patch on the computer before
                running. Repository code runs with your local user permissions.
              </p>
              <label>
                Computer
                <select
                  required
                  value={job.worker_id}
                  onChange={(e) =>
                    setJob({
                      ...job,
                      worker_id: e.target.value,
                      repository: "",
                      check: "",
                    })
                  }
                >
                  <option value="">Choose computer</option>
                  {desktop.workers
                    .filter((w) => !w.revoked)
                    .map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.label}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Local repository
                <select
                  required
                  value={job.repository}
                  onChange={(e) =>
                    setJob({ ...job, repository: e.target.value, check: "" })
                  }
                >
                  <option value="">Choose repository</option>
                  {Object.keys(worker?.repositories || {}).map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </label>
              <label>
                Check
                <select
                  required
                  value={job.check}
                  onChange={(e) => setJob({ ...job, check: e.target.value })}
                >
                  <option value="">Choose check</option>
                  {(worker?.repositories[job.repository] || []).map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
              <details>
                <summary>Test an exact code patch</summary>
                <label>
                  Base commit SHA
                  <input
                    value={job.base_sha}
                    onChange={(e) =>
                      setJob({ ...job, base_sha: e.target.value })
                    }
                  />
                </label>
                <label>
                  Git unified diff
                  <textarea
                    maxLength={60000}
                    value={job.patch}
                    onChange={(e) => setJob({ ...job, patch: e.target.value })}
                  />
                </label>
              </details>
              <button className="button primary" type="submit" disabled={busy}>Queue for local approval</button>
            </form>
          )}
          <div className="work-panel">
            <h2>Desktop activity</h2>
            {desktop.jobs
              .slice()
              .reverse()
              .map((j) => (
                <article key={j.id}>
                  <strong>{j.repository} · {j.check}</strong>
                  <p><span className={`status-pill ${jobStatusTone(j.status)}`}>{j.status}</span></p>
                  <small>Job: {j.id}</small>
                  {j.has_result && (
                    <button
                      className="button secondary"
                      type="button"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true);
                        try {
                          const full = await api(`/desktop/jobs/${j.id}`);
                          setDesktop((d) => ({
                            ...d,
                            jobs: d.jobs.map((row) =>
                              row.id === j.id ? full : row,
                            ),
                          }));
                        } catch (e) {
                          setError(e.message);
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      Load full result
                    </button>
                  )}
                  <pre>{j.summary}</pre>
                  {j.diff && (
                    <details>
                      <summary>View diff</summary>
                      <pre>{j.diff}</pre>
                    </details>
                  )}
                  {j.branch && (
                    <p>
                      Branch: <code>{j.branch}</code>
                    </p>
                  )}
                  {j.status === "queued" && (
                    <button
                      className="button destructive"
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        if (!window.confirm("Cancel this queued desktop job? The computer will no longer receive this request.")) return;
                        run(() => api("/desktop/cancel", { id: j.id }));
                      }}
                    >
                      Cancel queued job
                    </button>
                  )}
                </article>
              ))}
          </div>
        </div>
      </div>
      )}
    </section>
  );
}
