import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  api,
  connect,
  operation,
  saved,
  save,
  clearLocal,
  uid,
} from "./mini-client";
import "./App.css";

const nav = [
  ["today", "Today", "sun"],
  ["chat", "Talk to ORA", "spark"],
  ["tasks", "My plan", "check"],
  ["memory", "Second brain", "layers"],
  ["settings", "Connections", "sliders"],
];
function Icon({ name, size = 20 }) {
  const paths = {
    sun: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" />
      </>
    ),
    spark: (
      <path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6L12 3Z" />
    ),
    check: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="6" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    layers: (
      <>
        <path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5" />
      </>
    ),
    sliders: (
      <>
        <path d="M4 7h16M4 17h16" />
        <circle cx="9" cy="7" r="2" />
        <circle cx="16" cy="17" r="2" />
      </>
    ),
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
    mic: (
      <>
        <rect x="9" y="3" width="6" height="12" rx="3" />
        <path d="M6 11v1a6 6 0 0 0 12 0v-1m-6 7v3m-3 0h6" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    refresh: (
      <>
        <path d="M20 7v5h-5M4 17v-5h5" />
        <path d="M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1" />
      </>
    ),
    sound: (
      <>
        <path d="m11 5-6 4H2v6h3l6 4V5Zm4 3a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14" />
      </>
    ),
    close: <path d="m6 6 12 12M6 18 18 6" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.spark}
    </svg>
  );
}
function BrandMark({ size = 36 }) {
  return <img src="/ora-horus.webp" alt="ORA" width={size} height={size} className="brand-mark" />;
}
function Orb({ small = false, active = false }) {
  return <div aria-hidden="true" className={`orb brand-emblem ${small ? "small" : ""} ${active ? "active" : ""}`}><img src="/ora-horus.webp" alt="" width="220" height="220" /></div>;
}
function Empty({ children }) {
  return (
    <div className="empty">
      <Icon name="spark" />
      {children}
    </div>
  );
}
function dateLabel(value) {
  return value
    ? new Date(value).toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : "Whenever you’re ready";
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(Boolean(saved("token")));
  const [data, setData] = useState(saved("snapshot"));
  const [page, setPage] = useState("today");
  const [status, setStatus] = useState("Ready to connect");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState(saved("draft", ""));
  const [key, setKey] = useState("");
  const [task, setTask] = useState("");
  const [when, setWhen] = useState("");
  const [memory, setMemory] = useState("");
  const [pairCode, setPairCode] = useState("");
  const [voices, setVoices] = useState([]);
  const [voice, setVoice] = useState(localStorage.getItem("ora:voice") || "");
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [recording, setRecording] = useState(false);
  const [outbox, setOutbox] = useState(saved("outbox", []));
  const [pendingChat, setPendingChat] = useState(saved("pendingChat"));
  const recorder = useRef(null);
  const recordingTimer = useRef(null);
  const bottom = useRef(null);
  const syncing = useRef(false);
  const busyRef = useRef(false);
  const sync = useCallback(async () => {
    if (syncing.current) return;
    syncing.current = true;
    setStatus("Connecting · may take a minute");
    try {
      const queue = saved("outbox", []);
      for (const item of [...queue]) {
        try {
          await operation(item.kind, item.payload, item.request_id);
        } catch (e) {
          if (!e.status || e.status >= 500) throw e;
          setError(`A queued change needs attention: ${e.message}`);
          break;
        }
        const remaining = saved("outbox", []).filter(
          (x) => x.request_id !== item.request_id,
        );
        save("outbox", remaining);
        setOutbox(remaining);
      }
      const snapshot = await api("/sync");
      setData(snapshot);
      save("snapshot", snapshot);
      setStatus("Synced just now");
    } catch (e) {
      setStatus("Offline · showing saved data");
      setError(e.message);
      if (e.status === 401) {
        clearLocal();
        setAuthenticated(false);
        setData(null);
      }
    } finally {
      syncing.current = false;
    }
  }, []);
  useEffect(() => {
    if (!authenticated) return;
    sync();
    const id = setInterval(() => {
      if (document.visibilityState === "visible" && !busyRef.current) sync();
    }, 60000);
    const focus = () => {
      if (document.visibilityState === "visible" && !busyRef.current) sync();
    };
    document.addEventListener("visibilitychange", focus);
    window.addEventListener("online", focus);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", focus);
      window.removeEventListener("online", focus);
    };
  }, [authenticated, sync]);
  useEffect(() => {
    save("draft", draft);
  }, [draft]);
  useEffect(() => {
    const load = () => setVoices(window.speechSynthesis?.getVoices() || []);
    load();
    window.speechSynthesis?.addEventListener("voiceschanged", load);
    return () =>
      window.speechSynthesis?.removeEventListener("voiceschanged", load);
  }, []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [data?.messages?.length, busy, page]);
  useEffect(
    () => () => {
      clearTimeout(recordingTimer.current);
      if (recorder.current?.state === "recording") recorder.current.stop();
      window.speechSynthesis?.cancel();
    },
    [],
  );
  const speak = (text) => {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.replace(/[*#`]/g, ""));
    utterance.voice = voices.find((v) => v.voiceURI === voice) || null;
    utterance.rate = 0.98;
    window.speechSynthesis.speak(utterance);
  };
  const run = async (fn) => {
    setError("");
    setBusy(true);
    busyRef.current = true;
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  };
  const change = async (kind, payload) => {
    const request_id = uid();
    try {
      await operation(kind, payload, request_id);
      await sync();
    } catch (e) {
      if (
        !e.status &&
        ["task.create", "task.complete", "memory.save"].includes(kind)
      ) {
        const q = [...saved("outbox", []), { kind, payload, request_id }];
        save("outbox", q);
        setOutbox(q);
        setStatus("Saved on this browser · awaiting sync");
      } else throw e;
    }
  };
  const send = async (text = draft) => {
    if (!text.trim() || busy) return;
    setPage("chat");
    await run(async () => {
      const request =
        pendingChat?.text === text
          ? pendingChat
          : { request_id: uid(), text: text.trim() };
      setPendingChat(request);
      save("pendingChat", request);
      const result = await api("/chat", request);
      setDraft("");
      setPendingChat(null);
      save("pendingChat", null);
      await sync();
      if (autoSpeak) speak(result.reply);
    });
  };
  const record = async () => {
    if (recording) {
      recorder.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const media = new MediaRecorder(stream);
      recorder.current = media;
      const chunks = [];
      media.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      media.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        clearTimeout(recordingTimer.current);
        setRecording(false);
        await run(async () => {
          const body = new FormData();
          body.append(
            "file",
            new Blob(chunks, { type: media.mimeType }),
            "voice.webm",
          );
          const result = await api("/transcribe", body);
          setDraft(result.text);
          setPage("chat");
        });
      };
      media.start();
      setRecording(true);
      recordingTimer.current = setTimeout(
        () => media.state === "recording" && media.stop(),
        60000,
      );
    } catch {
      setError(
        "Microphone access is unavailable. Check your browser permission.",
      );
    }
  };
  const tasks = data?.tasks || [];
  const pending = tasks.filter((t) => !t.done);
  const actions = (data?.actions || []).filter(
    (a) => a.status === "pending" && a.expires_at > new Date().toISOString(),
  );
  const logout = () =>
    run(async () => {
      await api("/session", null, "DELETE");
      clearLocal();
      setAuthenticated(false);
      setData(null);
      setOutbox([]);
      setDraft("");
      setPendingChat(null);
    });
  const taskRow = (t) => (
    <div className={`task-row ${t.done ? "done" : ""}`} key={t.id}>
      <button
        className="task-check"
        aria-label={t.done ? "Reopen task" : "Complete task"}
        disabled={busy}
        onClick={() =>
          run(() => change("task.complete", { id: t.id, version: t.version }))
        }
      >
        {t.done ? "✓" : ""}
      </button>
      <div>
        <strong>{t.title}</strong>
        <small>{dateLabel(t.due_at)}</small>
      </div>
      <span className={`priority p${t.priority}`}>
        {["", "Low", "Normal", "Focus"][t.priority]}
      </span>
      {page === "tasks" && (
        <button
          className="icon-button"
          aria-label="Delete task"
          disabled={busy}
          onClick={() =>
            run(() => change("task.delete", { id: t.id, version: t.version }))
          }
        >
          <Icon name="close" size={16} />
        </button>
      )}
    </div>
  );
  const approvalCards = actions.map((a) => (
    <article className="approval" key={a.id}>
      <span className="eyebrow">REVIEW · {a.kind}</span>
      <p>{a.payload.title || a.payload.text || `To ${a.payload.recipient}`}</p>
      {a.payload.body && <p className="muted">{a.payload.body}</p>}
      {a.payload.due_at && <small>{dateLabel(a.payload.due_at)}</small>}
      <div className="button-row">
        <button
          disabled={busy}
          className="button primary"
          onClick={() => run(() => change("action.approve", { id: a.id }))}
        >
          Approve
        </button>
        <button
          disabled={busy}
          className="button ghost"
          onClick={() => run(() => change("action.reject", { id: a.id }))}
        >
          Dismiss
        </button>
      </div>
    </article>
  ));
  if (!authenticated)
    return (
      <main className="connect-screen">
        <div className="connect-card">
          <div className="wordmark">
            <BrandMark /> ORA <span>MINI AI</span>
          </div>
          <Orb />
          <span className="eyebrow">YOUR SPACE TO THINK</span>
          <h1>
            A little closer
            <br />
            to your own Jarvis.
          </h1>
          <p className="muted">
            Your ideas, your plans, your personal AI.
            <br />
            Connect to your private workspace.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                await connect(key);
                setKey("");
                setAuthenticated(true);
              });
            }}
          >
            <label htmlFor="access">Owner access key</label>
            <input
              id="access"
              type="password"
              autoComplete="current-password"
              placeholder="Enter your private access key"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              required
            />
            <button disabled={busy} className="button primary wide">
              {busy ? "Waking ORA…" : "Connect to ORA"}
              <Icon name="arrow" />
            </button>
          </form>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <small>
            Your key is exchanged for a temporary session. It is never built
            into the website.
          </small>
        </div>
      </main>
    );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="wordmark"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("today");
          }}
        >
          <BrandMark /> ORA <span>MINI AI</span>
        </a>
        <div className="sidebar-caption">PERSONAL WORKSPACE</div>
        <nav>
          {nav.map(([id, label, icon]) => (
            <button
              key={id}
              className={page === id ? "selected" : ""}
              onClick={() => setPage(id)}
            >
              <Icon name={icon} />
              <span>{label}</span>
              {id === "tasks" && pending.length > 0 && <b>{pending.length}</b>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="assistant-badge">
            <Orb small />
            <div>
              <strong>Always your ORA</strong>
              <small>One mind. All your devices.</small>
            </div>
          </div>
          <button className="profile" onClick={() => setPage("settings")}>
            <span className="avatar">{data?.settings?.name?.[0] || "E"}</span>
            <div>
              <strong>{data?.settings?.name || "Your workspace"}</strong>
              <small>Personal account</small>
            </div>
            <Icon name="sliders" size={18} />
          </button>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <span className="breadcrumb">
            MY ORA <span>/</span> {nav.find((n) => n[0] === page)?.[1]}
          </span>
          <button className="sync-status" disabled={busy} onClick={sync}>
            <Icon name="refresh" size={15} />
            {status}
          </button>
        </header>
        {error && (
          <div className="notice" role="alert">
            <span>{error}</span>
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <Icon name="close" size={16} />
            </button>
          </div>
        )}
        {outbox.length > 0 && (
          <div className="notice">
            {outbox.length} change(s) saved on this browser, waiting to sync.{" "}
            <button
              onClick={() => {
                save("outbox", []);
                setOutbox([]);
              }}
            >
              Discard queued changes
            </button>
          </div>
        )}
        <div className={`page-content ${page === "chat" ? "chat-page" : ""}`}>
          {page === "today" && (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">
                    {new Date()
                      .toLocaleDateString([], {
                        weekday: "long",
                        month: "long",
                        day: "numeric",
                      })
                      .toUpperCase()}
                  </span>
                  <h1>Your day, with a little clarity.</h1>
                  <p className="muted">
                    Hey {data?.settings?.name || "there"}. What’s on your mind?
                  </p>
                </div>
                <span className="edition">ORA / 02</span>
              </div>
              <section className="presence">
                <div>
                  <span className="eyebrow cyan">A MIND BY YOUR SIDE</span>
                  <h2>
                    Let’s make something
                    <br />
                    of today.
                  </h2>
                  <p>
                    Think out loud. Untangle an idea.
                    <br />
                    Turn “someday” into a small next step.
                  </p>
                  <button
                    className="button primary"
                    onClick={() => setPage("chat")}
                  >
                    Talk to ORA
                    <Icon name="arrow" />
                  </button>
                </div>
                <Orb active={busy} />
                <span className="presence-footer">
                  THINK · REMEMBER · FOLLOW THROUGH
                </span>
              </section>
              <div className="summary-strip">
                <div>
                  <strong>{pending.length.toString().padStart(2, "0")}</strong>
                  <span>Things on your mind</span>
                </div>
                <div>
                  <strong>{actions.length.toString().padStart(2, "0")}</strong>
                  <span>Awaiting your review</span>
                </div>
                <div>
                  <strong>
                    {(data?.memories?.length || 0).toString().padStart(2, "0")}
                  </strong>
                  <span>Things ORA remembers</span>
                </div>
              </div>
              <div className="two-columns">
                <section>
                  <div className="section-heading">
                    <h2>A little direction</h2>
                    <Icon name="spark" />
                  </div>
                  <div className="suggestions">
                    {(data?.suggestions || []).map((s, i) => (
                      <button
                        className="suggestion"
                        key={s.title}
                        disabled={busy}
                        onClick={() => send(s.prompt)}
                      >
                        <span className="suggestion-number">0{i + 1}</span>
                        <div>
                          <strong>{s.title}</strong>
                          <p>{s.detail}</p>
                        </div>
                        <Icon name="arrow" size={18} />
                      </button>
                    ))}
                  </div>
                </section>
                <section>
                  <div className="section-heading">
                    <h2>On your radar</h2>
                    <button
                      className="text-button"
                      onClick={() => setPage("tasks")}
                    >
                      View plan
                    </button>
                  </div>
                  <div className="panel">
                    {pending.length ? (
                      pending.slice(0, 4).map(taskRow)
                    ) : (
                      <Empty>Your next chapter starts with one task.</Empty>
                    )}
                  </div>
                </section>
              </div>
              {actions.length > 0 && (
                <section>
                  <div className="section-heading">
                    <h2>Your call</h2>
                    <span className="muted">ORA proposes. You decide.</span>
                  </div>
                  <div className="approval-grid">{approvalCards}</div>
                </section>
              )}
            </>
          )}
          {page === "chat" && (
            <>
              <div className="chat-heading">
                <Orb small active={busy} />
                <div>
                  <h1>Think out loud.</h1>
                  <p className="muted">A conversation that stays with you.</p>
                </div>
                <button
                  className="icon-button"
                  aria-label="Stop voice playback"
                  onClick={() => window.speechSynthesis?.cancel()}
                >
                  <Icon name="sound" />
                </button>
              </div>
              <div className="conversation" aria-live="polite">
                {!data?.messages?.length && (
                  <div className="chat-welcome">
                    <Icon name="spark" size={36} />
                    <h2>Big idea? Busy mind?</h2>
                    <p>I’m here for both. Tell me what you’re working on.</p>
                    <div className="chips">
                      {[
                        "Help me plan today",
                        "Let’s brainstorm an AI project",
                        "What do you remember about me?",
                      ].map((t) => (
                        <button disabled={busy} key={t} onClick={() => send(t)}>
                          {t}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {(data?.messages || []).map((m) => (
                  <article key={m.id} className={`message ${m.role}`}>
                    <span className="message-label">
                      {m.role === "user" ? "YOU" : "ORA"}
                    </span>
                    <div className="message-body">
                      <ReactMarkdown>{m.text}</ReactMarkdown>
                      {m.role === "assistant" && (
                        <button
                          className="read-button"
                          aria-label="Read response aloud"
                          onClick={() => speak(m.text)}
                        >
                          <Icon name="sound" size={16} />
                        </button>
                      )}
                    </div>
                  </article>
                ))}
                {pendingChat && (
                  <article className="message user">
                    <span className="message-label">
                      YOU · {busy ? "SENDING" : "NOT SENT"}
                    </span>
                    <div className="message-body">{pendingChat.text}</div>
                  </article>
                )}
                {busy && (
                  <div className="thinking">
                    <span />
                    ORA is thinking. A sleeping server can take a minute.
                  </div>
                )}
                <div className="approval-grid">{approvalCards}</div>
                <div ref={bottom} />
              </div>
              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  send();
                }}
              >
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Tell ORA what’s on your mind…"
                  aria-label="Message ORA"
                  rows={2}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                />
                <div className="composer-bottom">
                  <span>Personal context, connected.</span>
                  <div>
                    <button
                      type="button"
                      className={`icon-button ${recording ? "recording" : ""}`}
                      disabled={busy}
                      aria-label={
                        recording ? "Stop recording" : "Record voice note"
                      }
                      onClick={record}
                    >
                      <Icon name="mic" />
                    </button>
                    <button
                      className="send-button"
                      disabled={busy || !draft.trim()}
                      aria-label="Send message"
                    >
                      <Icon name="arrow" />
                    </button>
                  </div>
                </div>
              </form>
              <small className="composer-hint">
                Voice becomes a draft first. Review it, then send.
              </small>
            </>
          )}
          {page === "tasks" && (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">SMALL STEPS, REAL PROGRESS</span>
                  <h1>Make a little space.</h1>
                  <p className="muted">
                    Your plan, synchronized across web and phone.
                  </p>
                </div>
              </div>
              <form
                className="task-form panel"
                onSubmit={(e) => {
                  e.preventDefault();
                  run(async () => {
                    await change("task.create", {
                      title: task,
                      due_at: when ? new Date(when).toISOString() : null,
                      priority: 2,
                    });
                    setTask("");
                    setWhen("");
                  });
                }}
              >
                <label>
                  What do you want to do?
                  <input
                    value={task}
                    maxLength={240}
                    onChange={(e) => setTask(e.target.value)}
                    placeholder="Build something that matters"
                    required
                  />
                </label>
                <label>
                  Remind me at <span className="muted">(optional)</span>
                  <input
                    type="datetime-local"
                    value={when}
                    onChange={(e) => setWhen(e.target.value)}
                  />
                </label>
                <button disabled={busy} className="button primary">
                  <Icon name="plus" />
                  Add to my plan
                </button>
              </form>
              <p className="muted">
                Open Android after adding a reminder here so it can schedule it
                on your phone. Scheduled phone reminders work while the server
                sleeps.
              </p>
              <div className="panel task-list">
                {tasks.length ? (
                  [...tasks]
                    .sort((a, b) => Number(a.done) - Number(b.done))
                    .map(taskRow)
                ) : (
                  <Empty>No tasks yet. Keep it simple: start with one.</Empty>
                )}
              </div>
            </>
          )}
          {page === "memory" && (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">LESS TO HOLD IN YOUR HEAD</span>
                  <h1>Your second brain.</h1>
                  <p className="muted">
                    Keep what matters. Change your mind whenever you want.
                  </p>
                </div>
              </div>
              <form
                className="panel memory-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  run(async () => {
                    await change("memory.save", { text: memory });
                    setMemory("");
                  });
                }}
              >
                <label>
                  A useful thing for ORA to remember
                  <textarea
                    rows={3}
                    maxLength={1000}
                    value={memory}
                    onChange={(e) => setMemory(e.target.value)}
                    placeholder="My current focus is building useful, thoughtful AI products…"
                    required
                  />
                </label>
                <button disabled={busy} className="button primary">
                  Remember this
                  <Icon name="plus" />
                </button>
              </form>
              <div className="memory-grid">
                {(data?.memories || []).map((m) => (
                  <article className="panel memory-card" key={m.id}>
                    <Icon name="layers" />
                    <p>{m.text}</p>
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={() =>
                        run(() => change("memory.delete", { id: m.id }))
                      }
                    >
                      Forget
                    </button>
                  </article>
                ))}
              </div>
              <div className="section-heading">
                <h2>Your knowledge</h2>
                <label className="button ghost upload-label">
                  Add a document
                  <input
                    type="file"
                    accept=".pdf,.txt,.md"
                    disabled={busy}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f)
                        run(async () => {
                          const form = new FormData();
                          form.append("file", f);
                          await api("/documents", form);
                          await sync();
                        });
                      e.target.value = "";
                    }}
                  />
                </label>
              </div>
              <p className="muted">
                Readable PDF, text or Markdown. Up to 2 MB. ORA uses excerpts to
                ground its answers.
              </p>
              {(data?.documents || []).map((d) => (
                <div className="document panel" key={d.id}>
                  <Icon name="layers" />
                  <strong>{d.name}</strong>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() =>
                      run(() => change("document.delete", { id: d.id }))
                    }
                  >
                    Remove
                  </button>
                </div>
              ))}
            </>
          )}
          {page === "settings" && (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">MAKE ORA YOURS</span>
                  <h1>One mind. Your world.</h1>
                  <p className="muted">
                    Choose the voice. Connect your phone. Stay in control.
                  </p>
                </div>
              </div>
              <div className="two-columns">
                <section className="panel settings-panel">
                  <h2>A voice you connect with</h2>
                  <label>
                    Available browser voices
                    <select
                      value={voice}
                      onChange={(e) => {
                        setVoice(e.target.value);
                        localStorage.setItem("ora:voice", e.target.value);
                      }}
                    >
                      <option value="">System default</option>
                      {voices.map((v) => (
                        <option key={v.voiceURI} value={v.voiceURI}>
                          {v.name} · {v.lang}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="button ghost"
                    onClick={() =>
                      speak(
                        "Hey. I’m ORA. Let’s make a little room for your next big idea.",
                      )
                    }
                  >
                    <Icon name="sound" />
                    Preview voice
                  </button>
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={autoSpeak}
                      onChange={(e) => setAutoSpeak(e.target.checked)}
                    />
                    Read replies aloud in this session
                  </label>
                  <p className="muted">
                    Voice availability depends on your browser. Android has its
                    own installed voices.
                  </p>
                </section>
                <section className="panel settings-panel">
                  <h2>Pair your Android</h2>
                  <p className="muted">
                    Open the ORA app and enter a one-time pairing code. Your
                    phone gets its own revocable connection.
                  </p>
                  <button
                    disabled={busy}
                    className="button primary"
                    onClick={() =>
                      run(async () => {
                        const r = await api("/pairing-code", {});
                        setPairCode(r.code);
                      })
                    }
                  >
                    Generate pairing code
                    <Icon name="arrow" />
                  </button>
                  {pairCode && (
                    <div className="pair-code">
                      <strong>{pairCode}</strong>
                      <small>Expires in 10 minutes · use once</small>
                    </div>
                  )}
                </section>
              </div>
              <section className="panel settings-panel">
                <h2>Your rhythm</h2>
                <form
                  className="rhythm"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const f = new FormData(e.target);
                    run(() =>
                      change("settings.update", {
                        name: f.get("name"),
                        timezone: f.get("timezone"),
                        quiet_start: Number(f.get("quiet_start")),
                        quiet_end: Number(f.get("quiet_end")),
                      }),
                    );
                  }}
                  key={data?.settings?.name + data?.settings?.timezone}
                >
                  <label>
                    Your name
                    <input
                      name="name"
                      defaultValue={data?.settings?.name}
                      maxLength={60}
                      required
                    />
                  </label>
                  <label>
                    Timezone
                    <input
                      name="timezone"
                      defaultValue={data?.settings?.timezone}
                      required
                    />
                  </label>
                  <label>
                    Quiet hours start
                    <input
                      name="quiet_start"
                      type="number"
                      min="0"
                      max="23"
                      defaultValue={data?.settings?.quiet_start}
                    />
                  </label>
                  <label>
                    Quiet hours end
                    <input
                      name="quiet_end"
                      type="number"
                      min="0"
                      max="23"
                      defaultValue={data?.settings?.quiet_end}
                    />
                  </label>
                  <button className="button ghost" disabled={busy}>
                    Save rhythm
                  </button>
                </form>
              </section>
              <section className="panel settings-panel">
                <h2>Connected devices</h2>
                {data?.devices?.length ? (
                  data.devices.map((d) => (
                    <div className="document" key={d.id}>
                      <span className="avatar">
                        <Icon name="sliders" />
                      </span>
                      <div>
                        <strong>{d.label}</strong>
                        <small>
                          Last heard {dateLabel(d.last_seen)} ·{" "}
                          {d.paused ? "Awareness paused" : "Paired"}
                        </small>
                      </div>
                      <button
                        disabled={busy}
                        className="text-button"
                        onClick={() =>
                          run(() => change("device.revoke", { id: d.id }))
                        }
                      >
                        Revoke
                      </button>
                    </div>
                  ))
                ) : (
                  <p className="muted">No phone paired yet.</p>
                )}
              </section>
              {(data?.actions || [])
                .filter((a) => a.status === "ready_to_share")
                .map((a) => (
                  <section className="panel settings-panel" key={a.id}>
                    <h2>Message ready for {a.payload.recipient}</h2>
                    <p>{a.payload.body}</p>
                    <button
                      className="button ghost"
                      onClick={() =>
                        run(async () => {
                          if (navigator.share)
                            await navigator.share({ text: a.payload.body });
                          else
                            await navigator.clipboard.writeText(a.payload.body);
                        })
                      }
                    >
                      Share or copy draft
                    </button>
                    <small>
                      Choose the recipient and send in your messaging app. ORA
                      has not sent this.
                    </small>
                  </section>
                ))}
              <div className="button-row">
                <button
                  className="button ghost"
                  onClick={() =>
                    run(async () => {
                      const content = await api("/export");
                      const url = URL.createObjectURL(
                        new Blob([JSON.stringify(content, null, 2)], {
                          type: "application/json",
                        }),
                      );
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = "ora-workspace.json";
                      a.click();
                      URL.revokeObjectURL(url);
                    })
                  }
                >
                  Export my workspace
                </button>
                <button
                  className="button ghost"
                  onClick={logout}
                  disabled={busy}
                >
                  Disconnect this browser
                </button>
              </div>
            </>
          )}
        </div>
        <footer className="page-footer">
          <span>
            <BrandMark size={24} /> ORA <b>MINI AI</b>
          </span>
          <span>Built around you.</span>
        </footer>
      </main>
      <nav className="mobile-nav">
        {nav.map(([id, label, icon]) => (
          <button
            key={id}
            className={page === id ? "selected" : ""}
            onClick={() => setPage(id)}
            aria-label={label}
          >
            <Icon name={icon} />
            <span>
              {label === "Talk to ORA"
                ? "Talk"
                : label === "Connections"
                  ? "Settings"
                  : label === "Second brain"
                    ? "Memory"
                    : label}
            </span>
          </button>
        ))}
      </nav>
    </div>
  );
}
