import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
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
import { CORE_NAV_ITEMS, MORE_NAV_ITEMS, NAV_BY_ID, NAV_BY_PATH } from "./mini/navigation";
import "./App.css";
import ToolsPage from "./ToolsPage";
import WorkPage from "./WorkPage";
import GoogleConnection from "./GoogleConnection";

function Icon({ name, size = 20 }) {
  const paths = {
    sun: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" />
      </>
    ),
    message: (
      <>
        <path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l-2 2v-6.5A7.5 7.5 0 1 1 20 11.5Z" />
        <path d="M8 11h.01M12 11h.01M16 11h.01" />
      </>
    ),
    spark: <path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6L12 3Z" />,
    check: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="5" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    brain: (
      <>
        <path d="M9 4.5A3.5 3.5 0 0 0 5.5 8v.5A3.5 3.5 0 0 0 5 15a3.5 3.5 0 0 0 4 5" />
        <path d="M15 4.5A3.5 3.5 0 0 1 18.5 8v.5A3.5 3.5 0 0 1 19 15a3.5 3.5 0 0 1-4 5M12 3v18M8 9c1.5 0 2.5 1 2.5 2.5M16 9c-1.5 0-2.5 1-2.5 2.5M8 16c1.5 0 2.5-1 2.5-2.5M16 16c-1.5 0-2.5-1-2.5-2.5" />
      </>
    ),
    tool: (
      <>
        <path d="M14.5 6.5a4 4 0 0 0-5.4 5.4L3 18l3 3 6.1-6.1a4 4 0 0 0 5.4-5.4L15 12l-3-3 2.5-2.5Z" />
        <path d="m14 10 3-3 3 3-3 3" />
      </>
    ),
    folder: <path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H10l2 2h7.5A1.5 1.5 0 0 1 21 8.5v10a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5Z" />,
    settings: (
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
    sound: <path d="m11 5-6 4H2v6h3l6 4V5Zm4 3a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    copy: <path d="M8 8h12v13H8zM4 16H3V3h12v2" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {paths[name] || paths.spark}
    </svg>
  );
}

function BrandMark({ size = 34 }) {
  return (
    <img
      src="/ora-mark.svg"
      alt=""
      width={size}
      height={size}
      className="brand-mark"
    />
  );
}

function Orb({ small = false }) {
  return (
    <span aria-hidden="true" className={`orb ${small ? "small" : ""}`}>
      <BrandMark size={small ? 36 : 96} />
    </span>
  );
}

function Empty({ children }) {
  return (
    <div className="empty">
      <Icon name="spark" />
      <span>{children}</span>
    </div>
  );
}

function dateLabel(value, timezone) {
  if (!value) return "No due date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
      ...(timezone ? { timeZone: timezone } : {}),
    }).format(date);
  } catch {
    return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }
}

function dueLabel(value, timezone) {
  if (!value) return "No due date";
  const due = new Date(value);
  if (Number.isNaN(due.getTime())) return "Date unavailable";
  if (due.getTime() < Date.now()) return `Overdue · ${dateLabel(value, timezone)}`;
  try {
    const formatDay = (date) =>
      new Intl.DateTimeFormat("en-CA", {
        timeZone: timezone || undefined,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(date);
    if (formatDay(due) === formatDay(new Date())) return `Due today · ${dateLabel(value, timezone)}`;
  } catch {
    if (due.toDateString() === new Date().toDateString()) return `Due today · ${dateLabel(value, timezone)}`;
  }
  return `Due ${dateLabel(value, timezone)}`;
}

const CONNECTION_SECTIONS = [
  ["account-session", "Account & session"],
  ["google-workspace", "Google Workspace"],
  ["phone", "Phone"],
  ["telegram", "Telegram"],
  ["voice", "Voice"],
  ["your-rhythm", "Your rhythm"],
  ["share-drafts", "Ready to share"],
  ["connection-health", "Connection health"],
];

function scrollToSection(id) {
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const target = document.getElementById(id);
  target?.scrollIntoView({
    behavior: reducedMotion ? "auto" : "smooth",
    block: "start",
  });
  const heading = target?.querySelector("h1, h2, h3");
  if (heading) {
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }
}

function MoreSheet({ open, onClose, currentPage }) {
  const dialogRef = useRef(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className="more-sheet"
      aria-label="More workspace sections"
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="more-sheet-panel">
        <div className="more-sheet-heading">
          <h2>More workspace</h2>
          <button className="icon-button" type="button" aria-label="Close menu" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <nav aria-label="More workspace sections">
          {MORE_NAV_ITEMS.map((item) => (
            <NavLink key={item.id} to={item.path} onClick={onClose}>
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {currentPage === item.id && <small>Current section</small>}
            </NavLink>
          ))}
        </nav>
      </div>
    </dialog>
  );
}

// Sync cadence tuned for a free Render instance (750 h/month for the workspace).
// Active tab: one snapshot a minute. Idle tab: every three minutes. Hidden tab or
// ten minutes without input: no traffic at all, so Render can spin the service down.
const ACTIVE_MS = 60 * 1000;
const SLOW_AFTER_MS = 2 * 60 * 1000;
const SLOW_MS = 3 * 60 * 1000;
const IDLE_STOP_MS = 10 * 60 * 1000;
const MAX_BACKOFF_MS = 4 * 60 * 1000;

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const currentPath = location.pathname.replace(/\/+$/, "") || "/";
  const currentSection = NAV_BY_PATH[currentPath];
  const page = currentSection?.id || "today";
  const previousPath = useRef(currentPath);
  const setPage = (id) => {
    const section = NAV_BY_ID[id];
    if (section) navigate(section.path);
  };
  const [authenticated, setAuthenticated] = useState(Boolean(saved("token")));
  const [data, setData] = useState(saved("snapshot"));
  const [status, setStatus] = useState(() =>
    saved("token") ? (navigator.onLine ? "waking" : "offline") : "not-connected",
  );
  const [lastSyncedAt, setLastSyncedAt] = useState(saved("lastSyncedAt"));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState(saved("draft", ""));
  const [key, setKey] = useState("");
  const [task, setTask] = useState("");
  const [when, setWhen] = useState("");
  const [taskPriority, setTaskPriority] = useState(2);
  const [taskFilter, setTaskFilter] = useState("active");
  const [memory, setMemory] = useState("");
  const [memoryView, setMemoryView] = useState("memories");
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadState, setUploadState] = useState("idle");
  const [uploadMessage, setUploadMessage] = useState("");
  const [pairCode, setPairCode] = useState("");
  const [pairCopied, setPairCopied] = useState(false);
  const [telegram, setTelegram] = useState(null);
  const [telegramError, setTelegramError] = useState("");
  const [telegramLoading, setTelegramLoading] = useState(false);
  const [readiness, setReadiness] = useState(null);
  const [readinessError, setReadinessError] = useState("");
  const [readinessLoading, setReadinessLoading] = useState(false);
  const [shareStatus, setShareStatus] = useState("");
  const [telegramLink, setTelegramLink] = useState(null);
  const [voices, setVoices] = useState([]);
  const [voice, setVoice] = useState(saved("voice", ""));
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("");
  const [chatStatus, setChatStatus] = useState("");
  const [moreOpen, setMoreOpen] = useState(false);
  const [outboxOpen, setOutboxOpen] = useState(false);
  const [outbox, setOutbox] = useState(saved("outbox", []));
  const [pendingChat, setPendingChat] = useState(saved("pendingChat"));
  const recorder = useRef(null);
  const recordingTimer = useRef(null);
  const conversation = useRef(null);
  const bottom = useRef(null);
  const followChat = useRef(true);
  const syncing = useRef(false);
  const busyRef = useRef(false);
  const sessionActive = useRef(Boolean(saved("token")));
  const discardRecording = useRef(false);
  const hasData = useRef(Boolean(saved("snapshot")));
  const lastSyncAt = useRef(0);
  const lastActivity = useRef(0);
  const failures = useRef(0);

  const resetSessionUi = useCallback((notice = "") => {
    sessionActive.current = false;
    if (recorder.current?.state === "recording") {
      discardRecording.current = true;
      recorder.current.stop();
    }
    window.speechSynthesis?.cancel();
    setAuthenticated(false);
    setData(null);
    setStatus("not-connected");
    setLastSyncedAt(null);
    setOutbox([]);
    setOutboxOpen(false);
    setPendingChat(null);
    setDraft("");
    setKey("");
    setTask("");
    setWhen("");
    setTaskPriority(2);
    setTaskFilter("active");
    setMemory("");
    setMemoryView("memories");
    setUploadFile(null);
    setUploadState("idle");
    setUploadMessage("");
    setPairCode("");
    setPairCopied(false);
    setTelegram(null);
    setTelegramError("");
    setTelegramLoading(false);
    setTelegramLink(null);
    setReadiness(null);
    setReadinessError("");
    setReadinessLoading(false);
    setShareStatus("");
    setVoice("");
    setAutoSpeak(false);
    setRecording(false);
    setTranscribing(false);
    setVoiceStatus("");
    setChatStatus("");
    setMoreOpen(false);
    setError(notice);
    setBusy(false);
    busyRef.current = false;
    hasData.current = false;
    lastSyncAt.current = 0;
  }, []);

  useEffect(() => {
    sessionActive.current = authenticated;
  }, [authenticated]);

  useEffect(() => {
    if (!currentSection) navigate("/today", { replace: true });
  }, [currentSection, currentPath, navigate]);

  useEffect(() => {
    document.title = `${currentSection?.title || "Today"} · ORA`;
    setMoreOpen(false);
    if (previousPath.current !== currentPath) {
      const heading = document.querySelector("#page-content h1");
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
      }
    }
    previousPath.current = currentPath;
  }, [currentPath, currentSection]);
  const refreshReadiness = useCallback(async () => {
    setReadinessError("");
    setReadinessLoading(true);
    try {
      setReadiness(await api("/readiness"));
    } catch (e) {
      setReadiness(null);
      setReadinessError(e.message);
    } finally {
      setReadinessLoading(false);
    }
  }, []);
  const refreshTelegram = useCallback(async () => {
    setTelegramError("");
    setTelegramLoading(true);
    try {
      setTelegram(await api("/telegram/status"));
    } catch (e) {
      setTelegram(null);
      setTelegramError(e.message);
    } finally {
      setTelegramLoading(false);
    }
  }, []);
  const sync = useCallback(async () => {
    if (!sessionActive.current || syncing.current) return;
    syncing.current = true;
    setStatus(hasData.current ? "syncing" : "waking");
    let queuedChangeNeedsAttention = false;
    try {
      const queue = saved("outbox", []);
      for (const item of [...queue]) {
        try {
          await operation(item.kind, item.payload, item.request_id);
        } catch (e) {
          if (!e.status || e.status >= 500) throw e;
          setError(`A queued change needs attention: ${e.message}`);
          queuedChangeNeedsAttention = true;
          break;
        }
        const remaining = saved("outbox", []).filter(
          (x) => x.request_id !== item.request_id,
        );
        save("outbox", remaining);
        setOutbox(remaining);
      }
      const snapshot = await api("/sync");
      if (snapshot) {
        // A 304 means the server sent nothing new: keep the current snapshot.
        setData(snapshot);
        save("snapshot", snapshot);
        hasData.current = true;
      }
      const syncedAt = Date.now();
      setLastSyncedAt(syncedAt);
      save("lastSyncedAt", syncedAt);
      lastSyncAt.current = syncedAt;
      failures.current = 0;
      setStatus(queuedChangeNeedsAttention ? "error" : "up-to-date");
      if (!queuedChangeNeedsAttention) setError("");
    } catch (e) {
      failures.current += 1;
      setStatus(e.status === 401 ? "not-connected" : navigator.onLine ? "error" : "offline");
      setError(e.message);
      if (e.status === 401) {
        clearLocal();
        resetSessionUi(e.message);
      }
    } finally {
      syncing.current = false;
    }
  }, [resetSessionUi]);
  useEffect(() => {
    if (!authenticated) return;
    let timer = null;
    let cancelled = false;

    // Render Free sleeps after 15 minutes without traffic, so a forgotten or
    // hidden tab must not poll. Polling stops when the tab is hidden or after
    // ten minutes without user input; any activity wakes it and syncs at once.
    const gap = () => {
      if (document.visibilityState !== "visible") return null;
      const idleFor = Date.now() - lastActivity.current;
      if (idleFor > IDLE_STOP_MS) return null;
      const base = idleFor > SLOW_AFTER_MS ? SLOW_MS : ACTIVE_MS;
      const backoff = Math.min(failures.current * 30000, MAX_BACKOFF_MS);
      return base + backoff;
    };
    const clear = () => {
      if (timer) clearTimeout(timer);
      timer = null;
    };
    const arm = () => {
      clear();
      const wait = gap();
      if (cancelled || wait === null) return;
      timer = setTimeout(async () => {
        if (!cancelled && document.visibilityState === "visible" && !busyRef.current)
          await sync();
        arm();
      }, wait);
    };
    const activity = () => {
      const stopped = gap() === null;
      lastActivity.current = Date.now();
      if (document.visibilityState !== "visible") {
        clear();
        return;
      }
      // Resume after a hidden or idle period, or after a long gap between checks.
      if (stopped || Date.now() - lastSyncAt.current > ACTIVE_MS) sync();
      arm();
    };

    lastActivity.current = Date.now();
    sync();
    arm();
    document.addEventListener("visibilitychange", activity);
    const offline = () => setStatus("offline");
    window.addEventListener("online", activity);
    window.addEventListener("offline", offline);
    window.addEventListener("pointerdown", activity, { passive: true });
    window.addEventListener("keydown", activity);
    window.addEventListener("scroll", activity, { passive: true });
    return () => {
      cancelled = true;
      clear();
      document.removeEventListener("visibilitychange", activity);
      window.removeEventListener("online", activity);
      window.removeEventListener("offline", offline);
      window.removeEventListener("pointerdown", activity);
      window.removeEventListener("keydown", activity);
      window.removeEventListener("scroll", activity);
    };
  }, [authenticated, sync]);
  useEffect(() => {
    if (authenticated && page === "connections") {
      refreshTelegram();
      refreshReadiness();
    }
  }, [authenticated, page, refreshTelegram, refreshReadiness]);
  useEffect(() => {
    save("draft", draft);
  }, [draft]);
  useEffect(() => {
    save("outbox", outbox);
  }, [outbox]);
  useEffect(() => {
    save("pendingChat", pendingChat);
  }, [pendingChat]);
  useEffect(() => {
    const load = () => setVoices(window.speechSynthesis?.getVoices() || []);
    load();
    window.speechSynthesis?.addEventListener("voiceschanged", load);
    return () =>
      window.speechSynthesis?.removeEventListener("voiceschanged", load);
  }, []);
  useEffect(() => {
    if (page !== "chat") {
      followChat.current = true;
      return;
    }
    if (!followChat.current) return;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    bottom.current?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "end" });
  }, [data?.messages?.length, busy, page, pendingChat]);
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
      if (e.status === 401) {
        clearLocal();
        resetSessionUi(e.message);
      }
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
      if (!e.status && ["task.create", "task.complete", "memory.save"].includes(kind)) {
        const q = [...saved("outbox", []), { kind, payload, request_id }];
        save("outbox", q);
        setOutbox(q);
        setStatus(navigator.onLine ? "error" : "offline");
      } else throw e;
    }
  };
  const send = async (text = draft) => {
    const cleanedText = text.trim();
    if (!cleanedText || busy) return;
    if (pendingChat && pendingChat.text !== cleanedText) {
      setPage("chat");
      setChatStatus("An earlier message is unconfirmed. Retry it with its original request ID, or discard its retry reference before sending a different message.");
      return;
    }
    setPage("chat");
    setChatStatus("Sending your message…");
    await run(async () => {
      const request = pendingChat?.text === cleanedText
        ? pendingChat
        : { request_id: uid(), text: cleanedText };
      setPendingChat(request);
      save("pendingChat", request);
      let result;
      try {
        result = await api("/chat", request);
      } catch (e) {
        setChatStatus("Message not confirmed. Your draft is still here; retry uses the same request.");
        throw e;
      }
      setDraft("");
      setPendingChat(null);
      save("pendingChat", null);
      setChatStatus("ORA replied. Your conversation is up to date when sync completes.");
      await sync();
      if (autoSpeak) speak(result.reply);
    });
  };
  const record = async () => {
    if (recording) {
      recorder.current?.stop();
      setVoiceStatus("Recording stopped. Transcribing your note…");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setVoiceStatus("Voice recording is not available in this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!sessionActive.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const media = new MediaRecorder(stream);
      recorder.current = media;
      const chunks = [];
      media.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      media.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        clearTimeout(recordingTimer.current);
        setRecording(false);
        if (discardRecording.current) {
          discardRecording.current = false;
          setTranscribing(false);
          setVoiceStatus("");
          return;
        }
        setTranscribing(true);
        setVoiceStatus("Transcribing your voice note…");
        await run(async () => {
          const body = new FormData();
          body.append("file", new Blob(chunks, { type: media.mimeType }), "voice.webm");
          try {
            const result = await api("/transcribe", body);
            if (!sessionActive.current) return;
            setDraft(result.text);
            setPage("chat");
            setVoiceStatus("Transcript added to your editable draft. It has not been sent.");
            setChatStatus("Voice transcript is an unsent draft. Review it before sending.");
          } catch (e) {
            setVoiceStatus("Transcription failed. Your existing draft was kept; you can record another note.");
            throw e;
          }
        });
        setTranscribing(false);
      };
      media.start();
      setRecording(true);
      setVoiceStatus("Recording. Tap Stop voice note when you are ready.");
      recordingTimer.current = setTimeout(() => {
        if (media.state === "recording") {
          setVoiceStatus("One-minute recording limit reached. Transcribing your note…");
          media.stop();
        }
      }, 60000);
    } catch (e) {
      if (!sessionActive.current) return;
      const denied = e.name === "NotAllowedError" || e.name === "PermissionDeniedError";
      setVoiceStatus(denied
        ? "Microphone permission was denied. Allow microphone access in your browser settings and try again."
        : "Microphone access failed. Check browser permission and try again.");
    }
  };

  const uploadDocument = async (file = uploadFile) => {
    if (!file) return;
    setUploadFile(file);
    const supported = /\.(pdf|txt|md)$/i.test(file.name);
    if (!supported) {
      setUploadState("error");
      setUploadMessage("Choose a PDF, UTF-8 text, or Markdown file.");
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      setUploadState("error");
      setUploadMessage("This file is over the 2 MB limit. Choose a smaller file.");
      return;
    }
    setUploadState("uploading");
    setUploadMessage(`Uploading ${file.name}…`);
    try {
      const form = new FormData();
      form.append("file", file);
      await api("/documents", form);
      setUploadState("success");
      setUploadMessage(`${file.name} is now in ORA’s active knowledge.`);
      await sync();
    } catch (e) {
      setUploadState("error");
      setUploadMessage(e.message || "Upload failed. Your selected file is kept here so you can retry.");
    }
  };

  const tasks = data?.tasks || [];
  const pending = tasks.filter((item) => !item.done);
  const actions = (data?.actions || []).filter(
    (item) => item.status === "pending" && item.expires_at > new Date().toISOString(),
  );
  const pendingToolRuns = (data?.tool_runs || []).filter((item) => item.status === "awaiting_approval" && !item.tool?.startsWith("email."));

  const logout = () => {
    const accepted = window.confirm(
      "Disconnect this browser from ORA? This clears this browser’s session, cached workspace, drafts, and any unsynced queued changes. It does not delete your server workspace or revoke paired phones.",
    );
    if (!accepted) return;
    sessionActive.current = false;
    if (recorder.current?.state === "recording") {
      discardRecording.current = true;
      recorder.current.stop();
    }
    run(async () => {
      let revokeWarning = "";
      try {
        await api("/session", null, "DELETE");
      } catch (e) {
        if (e.status !== 401) revokeWarning = " The server could not confirm session revocation; this browser will still clear its local session.";
      }
      clearLocal();
      resetSessionUi(revokeWarning.trim());
    });
  };

  const taskRow = (item) => (
    <div className={`task-row ${item.done ? "done" : ""}`} key={item.id}>
      <button
        className="task-check"
        type="button"
        aria-pressed={Boolean(item.done)}
        aria-label={item.done ? `Reopen ${item.title}` : `Complete ${item.title}`}
        disabled={busy}
        onClick={() => run(() => change("task.complete", { id: item.id, version: item.version }))}
      >
        {item.done ? "✓" : ""}
      </button>
      <div>
        <strong>{item.title}</strong>
        <small>
          {item.due_at
            ? <time dateTime={item.due_at} className={new Date(item.due_at) < new Date() && !item.done ? "due-overdue" : ""}>{item.done ? `Due ${dateLabel(item.due_at, data?.settings?.timezone)}` : dueLabel(item.due_at, data?.settings?.timezone)}</time>
            : "No due date"}
        </small>
      </div>
      <span className={`priority p${item.priority || 2}`}>
        {{ 1: "High priority", 2: "Normal priority", 3: "Low priority" }[item.priority] || "Normal priority"}
      </span>
      {page === "plan" && (
        <button
          className="icon-button"
          type="button"
          aria-label={`Delete task ${item.title}`}
          disabled={busy}
          onClick={() => {
            if (window.confirm(`Delete “${item.title}”? This removes it from your plan across devices after sync. There is no undo.`)) {
              run(() => change("task.delete", { id: item.id, version: item.version }));
            }
          }}
        >
          <Icon name="close" size={18} />
        </button>
      )}
    </div>
  );

  const approvalCards = actions.map((item) => {
    const type = item.kind === "task" ? "Task proposal" : item.kind === "memory" ? "Memory proposal" : item.kind === "message" ? "Message draft" : "ORA proposal";
    const title = item.kind === "task"
      ? item.payload.title
      : item.kind === "memory"
        ? item.payload.text
        : item.kind === "message"
          ? `Draft for ${item.payload.recipient || "your recipient"}`
          : item.payload.title || item.payload.text || "Review this proposal";
    const effect = item.kind === "task"
      ? "Approval adds this task to your plan. A paired Android device schedules a local reminder after it syncs."
      : item.kind === "memory"
        ? "Approval adds this fact to your confirmed memories, where you can review or forget it later."
        : item.kind === "message"
          ? "Approval prepares a shareable draft. ORA will not choose a recipient or send it; you decide in your messaging app."
          : "Approval permits the exact action shown above. Review every detail before you decide.";
    return (
      <article className="approval" key={item.id}>
        <div className="approval-meta">
          <span className="status-pill warning">Awaiting your decision</span>
          {item.expires_at && <small>Expires {dateLabel(item.expires_at, data?.settings?.timezone)}</small>}
        </div>
        <h3>{type}</h3>
        <p>{title}</p>
        {item.kind === "task" && item.payload.due_at && <p><strong>Reminder:</strong> {dateLabel(item.payload.due_at, data?.settings?.timezone)}</p>}
        {item.kind === "task" && <p><strong>Priority:</strong> {{ 1: "High", 2: "Normal", 3: "Low" }[item.payload.priority] || "Normal"}</p>}
        {item.kind === "message" && <p className="approval-message-body">{item.payload.body}</p>}
        <p className="approval-explanation">{effect}</p>
        <div className="button-row">
          <button
            type="button"
            disabled={busy}
            className="button primary"
            onClick={() => run(() => change("action.approve", { id: item.id }))}
          >
            {item.kind === "task" ? "Approve & add task" : item.kind === "memory" ? "Approve memory" : item.kind === "message" ? "Approve draft" : "Approve exact action"}
          </button>
          <button
            type="button"
            disabled={busy}
            className="button secondary"
            aria-label={`Dismiss ${type.toLowerCase()}`}
            onClick={() => run(() => change("action.reject", { id: item.id }))}
          >
            Dismiss proposal
          </button>
        </div>
      </article>
    );
  });

  const queuedDescription = (item) => {
    if (item.kind === "task.create") return `Create task: “${item.payload.title || "Untitled task"}”`;
    if (item.kind === "task.complete") {
      const taskItem = tasks.find((taskEntry) => taskEntry.id === item.payload.id);
      return `${taskItem?.done ? "Reopen" : "Complete"} task: “${taskItem?.title || "Task no longer in the cached plan"}”`;
    }
    if (item.kind === "memory.save") return `Save memory: “${item.payload.text || "Memory text unavailable"}”`;
    return `Queued ${item.kind} change`;
  };
  if (!authenticated)
    return (
      <main className="connect-screen">
        <section className="connect-card" aria-labelledby="connect-title">
          <div className="wordmark">
            <BrandMark /> <span className="wordmark-name">ORA</span>
            <span>PRIVATE WORKSPACE</span>
          </div>
          <span className="eyebrow">YOUR SPACE TO THINK</span>
          <h1 id="connect-title">A little more room for what matters.</h1>
          <p>
            Connect to your personal ORA workspace to continue your conversations,
            plans, and saved context.
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              run(async () => {
                await connect(key);
                setKey("");
                save("draft", draft);
                setError("");
                setStatus("waking");
                sessionActive.current = true;
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
              onChange={(event) => setKey(event.target.value)}
              required
            />
            <button disabled={busy} className="button primary wide">
              {busy ? "Connecting…" : error ? "Try connecting again" : "Connect to ORA"}
              {!busy && <Icon name="arrow" />}
            </button>
          </form>
          {busy && <p role="status">Exchanging your key for a temporary session. The server may take a moment to wake.</p>}
          {error && <p role="alert" className="error">{error}</p>}
          <small>
            Your key is exchanged for a temporary browser session. It is not
            bundled into this website and is cleared from the form after you connect.
          </small>
        </section>
      </main>
    );
  const statusText = {
    "not-connected": "Not connected",
    waking: "Waking server…",
    syncing: "Syncing…",
    "up-to-date": "Up to date",
    offline: data ? "Offline · cached data" : "Offline",
    error: error?.startsWith("A queued change needs attention")
      ? "Queued change needs attention"
      : data
        ? "Sync issue · data may be stale"
        : "Sync needs attention",
  }[status] || "Checking sync";
  const lastSyncedText = lastSyncedAt
    ? `Last successful sync ${dateLabel(lastSyncedAt, data?.settings?.timezone)}`
    : "No successful sync time is available yet";

  return (
    <div className="app-shell">
      <a className="skip-link sr-only" href="#main-content" onFocus={(event) => event.currentTarget.classList.remove("sr-only")} onBlur={(event) => event.currentTarget.classList.add("sr-only")}>
        Skip to main content
      </a>
      <aside className="sidebar">
        <NavLink className="wordmark" to="/today" aria-label="ORA home">
          <BrandMark /> <span className="wordmark-name">ORA</span><span>MINI</span>
        </NavLink>
        <div className="sidebar-caption">Everyday</div>
        <nav aria-label="Primary navigation">
          {CORE_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.id}
              to={item.path}
              aria-label={item.id === "plan" && pending.length ? `${item.label}. ${pending.length} active tasks.` : item.label}
              title={item.label}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.id === "plan" && pending.length > 0 && <b aria-label={`${pending.length} active tasks`}>{pending.length}</b>}
            </NavLink>
          ))}
          <div className="nav-divider" aria-hidden="true" />
          <div className="sidebar-group-label">More workspace</div>
          {MORE_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.id}
              to={item.path}
              aria-label={item.id === "tools" && pendingToolRuns.length ? `${item.label}. ${pendingToolRuns.length} tool actions to review.` : item.label}
              title={item.label}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.id === "tools" && pendingToolRuns.length > 0 && <b aria-label={`${pendingToolRuns.length} tool actions to review`}>{pendingToolRuns.length}</b>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <NavLink className="profile" to={NAV_BY_ID.connections.path} aria-label="Connections and preferences">
            <span className="avatar" aria-hidden="true">{data?.settings?.name?.[0] || "O"}</span>
            <span className="profile-copy">
              <strong>{data?.settings?.name || "Your workspace"}</strong>
              <small>Connections & preferences</small>
            </span>
            <Icon name="settings" size={18} />
          </NavLink>
        </div>
      </aside>
      <main className="workspace" id="main-content" tabIndex="-1">
        <header className="topbar">
          <span className="breadcrumb">{currentSection?.title || "Today"}</span>
          <button
            type="button"
            className={`sync-status status-${status}`}
            disabled={busy || status === "syncing" || status === "waking"}
            onClick={sync}
            title={`${statusText}. ${lastSyncedText}. Select to retry sync.`}
            aria-label={`Sync status: ${statusText}. ${lastSyncedText}. Select to retry sync.`}
          >
            <span className="sync-indicator" aria-hidden="true" />
            <span className="sync-label">{statusText}</span>
          </button>
        </header>
        {error && (
          <div className="global-notice error-notice" role="alert">
            <div>
              <strong>Something needs attention</strong>
              <p>{error}</p>
            </div>
            <div className="notice-actions">
              {(status === "offline" || status === "error") && (
                <button className="button secondary" type="button" disabled={busy} onClick={sync}>Retry sync</button>
              )}
              <button className="icon-button" type="button" aria-label="Dismiss message" onClick={() => setError("")}>
                <Icon name="close" />
              </button>
            </div>
          </div>
        )}
        {outbox.length > 0 && (
          <section className="queue-notice" aria-label="Offline changes waiting to sync">
            <div>
              <strong>{outbox.length} local change{outbox.length === 1 ? "" : "s"} queued — not synced</strong>
              <p>These operations are saved only in this browser. Review them, then retry sync when you are ready.</p>
            </div>
            <div className="notice-actions">
              <button className="button secondary" type="button" aria-expanded={outboxOpen} onClick={() => setOutboxOpen((value) => !value)}>
                {outboxOpen ? "Hide queued changes" : "Review queued changes"}
              </button>
              <button className="button ghost" type="button" disabled={busy || status === "syncing" || status === "waking"} onClick={sync}>
                <Icon name="refresh" size={17} /> Try syncing
              </button>
            </div>
          </section>
        )}
        {outboxOpen && outbox.length > 0 && (
          <section className="outbox-panel" aria-label="Queued operation details">
            <h2>Saved on this browser only</h2>
            <p className="muted">These changes have not reached ORA’s workspace. Retry keeps each operation’s original request ID.</p>
            <ul className="outbox-list">
              {outbox.map((item) => (
                <li key={item.request_id}>
                  <strong>{queuedDescription(item)}</strong>
                  <small>Local only · not synced</small>
                </li>
              ))}
            </ul>
            <div className="button-row">
              <button className="button ghost" type="button" disabled={busy || status === "syncing" || status === "waking"} onClick={sync}>Retry sync</button>
              <button
                className="button destructive"
                type="button"
                onClick={() => {
                  const count = outbox.length;
                  if (window.confirm(`Discard all ${count} queued change${count === 1 ? "" : "s"}? This permanently removes these local operations from this browser. They have not synced and cannot be recovered after discard.`)) {
                    save("outbox", []);
                    setOutbox([]);
                    setOutboxOpen(false);
                  }
                }}
              >
                Discard all {outbox.length} queued changes…
              </button>
            </div>
          </section>
        )}
        <div className={`page-content ${page === "chat" ? "chat-page" : ""}`} id="page-content" tabIndex="-1">
          {page === "projects" && <WorkPage />}
          {page === "tools" && (
            <ToolsPage
              onAsk={(prompt) => {
                setDraft(prompt);
                save("draft", prompt);
                setPage("chat");
              }}
            />
          )}
          {page === "today" && (
            <>
              <header className="page-heading">
                <div>
                  <time className="eyebrow" dateTime={new Date().toISOString().slice(0, 10)}>
                    {new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}
                  </time>
                  <h1>Your day, in focus.</h1>
                  <p className="muted">
                    {data?.settings?.name ? `Welcome back, ${data.settings.name}.` : "A calm place to start with what matters."}
                  </p>
                </div>
              </header>

              <section className="quick-start" aria-labelledby="quick-start-title">
                <div>
                  <span className="eyebrow">THINK IT THROUGH</span>
                  <h2 id="quick-start-title">What’s on your mind?</h2>
                  <p>Talk through an idea, find a next step, or make sense of a busy day. ORA helps you think; you stay in control.</p>
                </div>
                <button className="button primary" type="button" onClick={() => setPage("chat")}>
                  {draft.trim() ? "Continue your draft" : "Ask ORA"}
                  <Icon name="arrow" />
                </button>
              </section>

              <div className="summary-strip" role="group" aria-label="Workspace overview">
                <button className="summary-item" type="button" onClick={() => setPage("plan")} aria-label={data ? `${pending.length} active tasks. Open your plan.` : "Open your plan; task count is loading."}>
                  <strong>{data ? pending.length : "—"}</strong>
                  <span>Active tasks in your plan</span>
                </button>
                <button
                  className="summary-item"
                  type="button"
                  onClick={() => pendingToolRuns.length > 0 ? setPage("tools") : scrollToSection("needs-review")}
                  aria-label={data ? `${actions.length + pendingToolRuns.length} actions awaiting your review` : "Review queue count is loading"}
                >
                  <strong>{data ? actions.length + pendingToolRuns.length : "—"}</strong>
                  <span>Actions awaiting your review</span>
                </button>
                <button className="summary-item" type="button" onClick={() => setPage("memory")} aria-label={data ? `${data.memories?.length || 0} confirmed memories. Open Memory.` : "Open Memory; count is loading."}>
                  <strong>{data ? data.memories?.length || 0 : "—"}</strong>
                  <span>Confirmed memories</span>
                </button>
              </div>

              <section id="needs-review" aria-labelledby="review-heading">
                <div className="section-heading">
                  <h2 id="review-heading">Needs your review</h2>
                  <span className="muted">ORA proposes. You decide.</span>
                </div>
                {!data ? (
                  <div className="panel"><Empty>Loading your review queue…</Empty></div>
                ) : actions.length > 0 ? (
                  <div className="approval-grid">{approvalCards}</div>
                ) : (
                  <div className="panel"><Empty>No ORA proposals need a decision right now.</Empty></div>
                )}
                {pendingToolRuns.length > 0 && (
                  <div className="panel tool-history">
                    <span>{pendingToolRuns.length} tool action{pendingToolRuns.length === 1 ? "" : "s"} also waiting for your approval.</span>
                    <button className="button secondary" type="button" onClick={() => setPage("tools")}>Review tools & activity</button>
                  </div>
                )}
              </section>

              <section aria-labelledby="next-tasks-heading" className="next-tasks-section">
                <div className="section-heading">
                  <h2 id="next-tasks-heading">Next tasks</h2>
                  <button className="text-button" type="button" onClick={() => setPage("plan")}>View plan</button>
                </div>
                <div className="panel task-list">
                  {!data ? (
                    <Empty>Loading your plan…</Empty>
                  ) : pending.length ? (
                    [...pending]
                      .sort((a, b) => {
                        const dueA = a.due_at ? new Date(a.due_at).getTime() : Number.MAX_SAFE_INTEGER;
                        const dueB = b.due_at ? new Date(b.due_at).getTime() : Number.MAX_SAFE_INTEGER;
                        return dueA - dueB || (a.priority || 2) - (b.priority || 2);
                      })
                      .slice(0, 4)
                      .map(taskRow)
                  ) : (
                    <div>
                      <Empty>No active tasks yet. Add one small next step to your plan.</Empty>
                      <div className="button-row"><button className="button secondary" type="button" onClick={() => setPage("plan")}>Add a task</button></div>
                    </div>
                  )}
                </div>
              </section>

              {data?.suggestions?.length > 0 && (
                <section className="suggestion-section" aria-labelledby="suggestion-heading">
                  <div className="section-heading">
                    <h2 id="suggestion-heading">A few ways to begin</h2>
                  </div>
                  <div className="suggestions">
                    {data.suggestions.map((suggestion, index) => (
                      <button className="suggestion" key={`${suggestion.title}-${index}`} disabled={busy} onClick={() => send(suggestion.prompt)}>
                        <span className="suggestion-number">{index + 1}</span>
                        <div><strong>{suggestion.title}</strong><p>{suggestion.detail}</p></div>
                        <Icon name="arrow" size={18} />
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
          {page === "chat" && pendingToolRuns.length > 0 && (
            <button className="tool-history" type="button" onClick={() => setPage("tools")}>
              <span>{pendingToolRuns.length} tool action{pendingToolRuns.length === 1 ? "" : "s"} awaiting your approval</span>
              <span>Review in Tools & activity →</span>
            </button>
          )}
          {page === "chat" && (
            <>
              <div className="chat-heading">
                <Orb small />
                <div>
                  <h1>Talk to ORA</h1>
                  <p className="muted">A private conversation you can return to.</p>
                </div>
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Stop voice playback"
                  onClick={() => window.speechSynthesis?.cancel()}
                >
                  <Icon name="sound" />
                </button>
              </div>
              <p className={`chat-status ${chatStatus.includes("not confirmed") ? "error" : ""}`} role="status" aria-live="polite">{chatStatus}</p>
              {voiceStatus && <p className="chat-status" role="status" aria-live="polite">{voiceStatus}</p>}
              <div
                className="conversation"
                ref={conversation}
                aria-label="Conversation history"
                aria-busy={busy || transcribing}
                onScroll={(event) => {
                  const element = event.currentTarget;
                  followChat.current = element.scrollHeight - element.scrollTop - element.clientHeight < 140;
                }}
              >
                {!(data?.messages || []).some((message) => !message.project_id) && (
                  <div className="chat-welcome">
                    <Icon name="spark" size={32} />
                    <h2>Big idea? Busy mind?</h2>
                    <p>I’m here for both. Tell me what you’re working on.</p>
                    <div className="chips">
                      {["Help me plan today", "Let’s brainstorm an AI project", "What do you remember about me?"].map((text) => (
                        <button type="button" disabled={busy} key={text} onClick={() => send(text)}>{text}</button>
                      ))}
                    </div>
                  </div>
                )}
                {(data?.messages || []).filter((message) => !message.project_id).map((message) => (
                  <article key={message.id} className={`message ${message.role}`}>
                    <span className="message-label">{message.role === "user" ? "You" : "ORA"}</span>
                    <div className="message-body">
                      <ReactMarkdown>{message.text}</ReactMarkdown>
                      {message.role === "assistant" && (
                        <button type="button" className="read-button" aria-label="Read this ORA response aloud" onClick={() => speak(message.text)}>
                          <Icon name="sound" size={17} />
                        </button>
                      )}
                    </div>
                  </article>
                ))}
                {pendingChat && (
                  <article className="message user">
                    <span className="message-label">Unconfirmed draft · not sent</span>
                    <div className="message-body">
                      {pendingChat.text}
                      {!busy && (
                        <div className="button-row">
                          <button type="button" className="button secondary" onClick={() => send(pendingChat.text)}>Retry the same message</button>
                          <button type="button" className="button quiet" onClick={() => {
                            if (window.confirm("Discard this retry reference? The message may already have reached ORA if the connection failed after processing. This does not delete any saved conversation copy.")) {
                              setPendingChat(null);
                              save("pendingChat", null);
                              setChatStatus("Retry reference discarded. If the message had already reached ORA, it may still appear after sync.");
                            }
                          }}>Discard retry reference…</button>
                        </div>
                      )}
                    </div>
                  </article>
                )}
                {busy && <div className="thinking">ORA is preparing a reply…</div>}
                <div ref={bottom} aria-hidden="true" />
              </div>
              <form
                className="composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  send();
                }}
              >
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="Tell ORA what’s on your mind…"
                  aria-label="Message ORA"
                  rows={2}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      send();
                    }
                  }}
                />
                <div className="composer-bottom">
                  <span>Draft stays in this browser until sent.</span>
                  <div>
                    <button
                      type="button"
                      className={`icon-button ${recording ? "recording" : ""}`}
                      disabled={busy || transcribing}
                      aria-label={recording ? "Stop voice note recording" : transcribing ? "Transcribing voice note" : "Record a voice note"}
                      onClick={record}
                    >
                      <Icon name="mic" />
                    </button>
                    <button type="submit" className="send-button" disabled={busy || !draft.trim()} aria-label="Send message">
                      <Icon name="arrow" />
                    </button>
                  </div>
                </div>
              </form>
              <small className="composer-hint">Enter to send · Shift+Enter for a new line · Voice transcripts are editable drafts, never sent automatically.</small>
            </>
          )}
          {page === "plan" && (
            <>
              <header className="page-heading">
                <div>
                  <span className="eyebrow">A PLAN THAT CAN CHANGE</span>
                  <h1>My plan</h1>
                  <p className="muted">Capture a task, give it a time if useful, and keep the next step visible.</p>
                </div>
              </header>
              <form
                className="task-form panel"
                aria-busy={busy}
                onSubmit={(event) => {
                  event.preventDefault();
                  run(async () => {
                    await change("task.create", {
                      title: task.trim(),
                      due_at: when ? new Date(when).toISOString() : null,
                      priority: taskPriority,
                    });
                    setTask("");
                    setWhen("");
                    setTaskPriority(2);
                  });
                }}
              >
                <label>
                  Task
                  <input value={task} maxLength={240} onChange={(event) => setTask(event.target.value)} placeholder="What is one useful next step?" required />
                </label>
                <label>
                  Reminder time <span className="muted">(optional)</span>
                  <input type="datetime-local" value={when} onChange={(event) => setWhen(event.target.value)} />
                </label>
                <label>
                  Priority
                  <select value={taskPriority} onChange={(event) => setTaskPriority(Number(event.target.value))}>
                    <option value={1}>High</option>
                    <option value={2}>Normal</option>
                    <option value={3}>Low</option>
                  </select>
                </label>
                <button disabled={busy} className="button primary" type="submit">
                  <Icon name="plus" /> Add task
                </button>
                <small className="task-form-note">A web reminder is saved with the task. Your paired Android needs to sync before it can schedule a local phone reminder.</small>
              </form>
              <div className="task-filters" role="group" aria-label="Filter tasks">
                {[
                  ["active", data ? `Active (${pending.length})` : "Active"],
                  ["completed", data ? `Completed (${tasks.filter((item) => item.done).length})` : "Completed"],
                  ["all", data ? `All (${tasks.length})` : "All"],
                ].map(([filter, label]) => (
                  <button key={filter} type="button" aria-pressed={taskFilter === filter} onClick={() => setTaskFilter(filter)}>{label}</button>
                ))}
              </div>
              <div className="panel task-list" aria-busy={!data}>
                {!data ? (
                  <Empty>Loading your plan…</Empty>
                ) : tasks.filter((item) => taskFilter === "all" || (taskFilter === "completed" ? item.done : !item.done)).length ? (
                  tasks
                    .filter((item) => taskFilter === "all" || (taskFilter === "completed" ? item.done : !item.done))
                    .slice()
                    .sort((a, b) => {
                      const dueA = a.due_at ? new Date(a.due_at).getTime() : Number.MAX_SAFE_INTEGER;
                      const dueB = b.due_at ? new Date(b.due_at).getTime() : Number.MAX_SAFE_INTEGER;
                      return Number(a.done) - Number(b.done) || dueA - dueB || (a.priority || 2) - (b.priority || 2);
                    })
                    .map(taskRow)
                ) : (
                  <div>
                    <Empty>{taskFilter === "completed" ? "No completed tasks yet. Completed tasks will appear here." : taskFilter === "all" ? "Your plan is empty. Add a first small step above." : "No active tasks. You can add one above or review completed tasks."}</Empty>
                    {taskFilter === "active" && <div className="button-row"><button className="button secondary" type="button" onClick={() => setTaskFilter("completed")}>View completed tasks</button></div>}
                  </div>
                )}
              </div>
            </>
          )}
          {page === "memory" && (
            <>
              <header className="page-heading">
                <div>
                  <span className="eyebrow">YOUR CONTEXT, YOUR CHOICE</span>
                  <h1>Memory</h1>
                  <p className="muted">Memories are personal facts you ask ORA to keep. Source documents are files you choose to ground answers.</p>
                </div>
              </header>
              <div className="memory-tabs" role="group" aria-label="Choose a memory collection">
                <button type="button" aria-pressed={memoryView === "memories"} onClick={() => setMemoryView("memories")}>Memories</button>
                <button type="button" aria-pressed={memoryView === "documents"} onClick={() => setMemoryView("documents")}>Knowledge documents</button>
              </div>
              {memoryView === "memories" ? (
                <section aria-labelledby="memories-heading">
                  <h2 id="memories-heading">Confirmed memories</h2>
                  <p className="muted">Save a useful, stable fact you explicitly want ORA to remember. You can forget it later.</p>
                  <form className="panel memory-form" aria-busy={busy} onSubmit={(event) => {
                    event.preventDefault();
                    run(async () => {
                      await change("memory.save", { text: memory.trim() });
                      setMemory("");
                    });
                  }}>
                    <label>
                      What should ORA remember?
                      <textarea rows={3} maxLength={1000} value={memory} onChange={(event) => setMemory(event.target.value)} placeholder="A preference, ongoing focus, or stable detail you want ORA to retain…" required />
                      <small>{memory.length}/1000 characters</small>
                    </label>
                    <button disabled={busy || !memory.trim()} className="button primary" type="submit">Remember this <Icon name="plus" /></button>
                  </form>
                  {!data ? (
                    <div className="panel"><Empty>Loading confirmed memories…</Empty></div>
                  ) : data.memories?.length ? (
                    <div className="memory-grid">
                      {data.memories.map((item) => (
                        <article className="panel memory-card" key={item.id}>
                          <Icon name="brain" />
                          <p>{item.text}</p>
                          <button className="button quiet" type="button" disabled={busy} onClick={() => {
                            if (window.confirm(`Forget this memory: “${item.text.slice(0, 140)}${item.text.length > 140 ? "…" : ""}”? This removes it from ORA’s active memory after sync. Historical messages, operation receipts, and provider backups may still contain it.`)) {
                              run(() => change("memory.delete", { id: item.id }));
                            }
                          }}>Forget memory</button>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="panel"><Empty>No confirmed memories yet. Save only what you want ORA to retain.</Empty></div>
                  )}
                </section>
              ) : (
                <section aria-labelledby="documents-heading">
                  <div className="section-heading">
                    <div>
                      <h2 id="documents-heading">Knowledge documents</h2>
                      <p className="muted">Choose files one at a time. ORA does not scan your device or folders.</p>
                    </div>
                    <label className="upload-label">
                      Choose a document
                      <input
                        type="file"
                        accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
                        disabled={uploadState === "uploading"}
                        aria-label="Choose a PDF, text, or Markdown document"
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          if (file) uploadDocument(file);
                          event.target.value = "";
                        }}
                      />
                    </label>
                  </div>
                  <p className="muted">Supported: readable PDF, UTF-8 TXT, and Markdown (MD), up to 2 MB. PDFs must contain extractable text; scanned PDFs need OCR first. ORA stores extracted text for answer context, not a copy of the original file.</p>
                  {uploadFile && (
                    <div className="file-status">
                      <div>
                        <strong>{uploadFile.name}</strong>
                        <p role={uploadState === "error" ? "alert" : "status"} aria-live="polite">{uploadMessage}</p>
                      </div>
                      {uploadState === "error" && <button className="button secondary" type="button" onClick={() => uploadDocument(uploadFile)}>Retry upload</button>}
                      {uploadState === "uploading" && <span className="status-pill warning">Uploading</span>}
                    </div>
                  )}
                  {!data ? (
                    <div className="panel"><Empty>Loading your knowledge documents…</Empty></div>
                  ) : data.documents?.length ? (
                    <div className="document-list">
                      {data.documents.map((item) => (
                        <article className="document" key={item.id}>
                          <Icon name="folder" />
                          <div><strong>{item.name}</strong><small>Used as answer context · uploaded <time dateTime={item.created_at}>{dateLabel(item.created_at, data?.settings?.timezone)}</time></small></div>
                          <button className="button destructive" type="button" disabled={busy} onClick={() => {
                            if (window.confirm(`Delete “${item.name}” from ORA’s active knowledge? This removes the extracted text from active context on web and phone after sync. It does not delete your original file or erase historical messages, receipts, or provider backups.`)) {
                              run(() => change("document.delete", { id: item.id }));
                            }
                          }}>Delete document</button>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="panel"><Empty>No source documents yet. Choose one readable file to ground ORA’s answers.</Empty></div>
                  )}
                </section>
              )}
            </>
          )}
          {page === "connections" && (
            <>
              <header className="page-heading">
                <div>
                  <span className="eyebrow">YOUR ACCESS, YOUR CHOICES</span>
                  <h1>Connections</h1>
                  <p className="muted">Manage this browser, connected services, your phone, voice, and workspace preferences.</p>
                </div>
              </header>
              <div className="connections-layout">
                <nav className="connections-nav" aria-label="Connections settings sections">
                  {CONNECTION_SECTIONS.map(([id, label]) => (
                    <button key={id} type="button" aria-controls={id} onClick={() => scrollToSection(id)}>{label}</button>
                  ))}
                </nav>
                <div className="connections-content">
                  <section id="account-session" className="panel settings-panel">
                    <h2>Account & session</h2>
                    <p>Export a copy of your workspace or disconnect this browser. Disconnecting clears its session, cached workspace, drafts, and local queued changes; it does not delete the server workspace or revoke paired phones.</p>
                    <div className="button-row">
                      <button
                        className="button secondary"
                        type="button"
                        disabled={busy}
                        onClick={() => run(async () => {
                          const content = await api("/export");
                          const url = URL.createObjectURL(new Blob([JSON.stringify(content, null, 2)], { type: "application/json" }));
                          const anchor = document.createElement("a");
                          anchor.href = url;
                          anchor.download = "ora-workspace.json";
                          anchor.click();
                          setTimeout(() => URL.revokeObjectURL(url), 1000);
                        })}
                      >Export my workspace</button>
                      <button className="button destructive" type="button" onClick={logout} disabled={busy}>Disconnect this browser</button>
                    </div>
                    <small>The export is a user-triggered JSON download. Keep it somewhere private.</small>
                  </section>

                  <section id="google-workspace" aria-label="Google Workspace connection">
                    <GoogleConnection />
                  </section>

                  <section id="phone" className="panel settings-panel">
                    <h2>Phone</h2>
                    <p>Pair the ORA Android companion with a one-use code. The phone gets its own revocable session and syncs the shared workspace when it connects.</p>
                    <button
                      disabled={busy}
                      className="button primary"
                      type="button"
                      onClick={() => run(async () => {
                        const result = await api("/pairing-code", {});
                        setPairCode(result.code);
                        setPairCopied(false);
                      })}
                    >Generate pairing code <Icon name="arrow" /></button>
                    {pairCode && (
                      <div className="pair-code">
                        <div>
                          <strong>{pairCode}</strong>
                          <small>One-use code · expires in 10 minutes. After it is entered once, it is invalid.</small>
                        </div>
                        <button className="button secondary" type="button" onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(pairCode);
                            setPairCopied(true);
                          } catch {
                            setError("Could not copy the pairing code automatically. You can select and copy it instead.");
                          }
                        }}><Icon name="copy" size={17} /> Copy code</button>
                        {pairCopied && <small role="status" aria-live="polite">Pairing code copied.</small>}
                      </div>
                    )}
                    <h3>Paired devices</h3>
                    {!data ? <p className="muted">Loading paired devices…</p> : data.devices?.length ? (
                      data.devices.map((device) => (
                        <article className="document" key={device.id}>
                          <span className="avatar" aria-hidden="true"><Icon name="message" /></span>
                          <div>
                            <strong>{device.label}</strong>
                            <small>Last heard {device.last_seen ? <time dateTime={device.last_seen}>{dateLabel(device.last_seen, data?.settings?.timezone)}</time> : "not yet"} · {device.paused ? "Awareness paused" : "Paired and available to sync"}</small>
                          </div>
                          <button className="button destructive" type="button" disabled={busy} onClick={() => {
                            if (window.confirm(`Revoke “${device.label}”? This phone will lose access to this workspace the next time it connects. If it is offline, revocation cannot reach it until it reconnects.`)) {
                              run(() => change("device.revoke", { id: device.id }));
                            }
                          }}>Revoke phone</button>
                        </article>
                      ))
                    ) : <p className="muted">No phone is paired yet.</p>}
                    <small>Phone awareness is user-controlled and limited to the permissions you grant in Android. ORA does not continuously listen through this web page.</small>
                  </section>

                  <section id="telegram" className="panel settings-panel">
                    <div className="section-heading">
                      <h2>Telegram</h2>
                      <button className="button quiet" type="button" disabled={telegramLoading} onClick={refreshTelegram}>{telegramLoading ? "Checking…" : "Refresh status"}</button>
                    </div>
                    <p>Link a private Telegram conversation to chat with ORA there. The bot and webhook must be configured on your backend first.</p>
                    {telegramLoading && !telegram && <p role="status">Checking Telegram setup…</p>}
                    {telegramError && <div className="global-notice error-notice" role="alert"><div><strong>Could not check Telegram</strong><p>{telegramError}</p></div><button className="button secondary" type="button" onClick={refreshTelegram}>Retry</button></div>}
                    {telegram && (
                      <p><span className={`status-pill ${telegram.linked ? "success" : telegram.configured ? "warning" : ""}`}>{telegram.linked ? `Connected${telegram.first_name ? ` as ${telegram.first_name}` : ""}` : telegram.configured ? "Configured · not linked" : "Not configured"}</span></p>
                    )}
                    {telegram?.username && <p className="muted">Bot: @{telegram.username}</p>}
                    {telegram?.setup_error && <p role="alert" className="error">{telegram.setup_error}</p>}
                    {telegram?.webhook_active === false && telegram?.configured && <p className="muted">The Telegram webhook is inactive. You can retry activation below.</p>}
                    {telegram?.delivery_error && <p role="alert" className="error">Delivery issue: {telegram.delivery_error}</p>}
                    {telegram?.webhook_error && <p role="alert" className="error">Webhook issue: {telegram.webhook_error}</p>}
                    {telegram?.pending_updates > 0 && <p className="muted">{telegram.pending_updates} Telegram update(s) waiting for delivery.</p>}
                    {telegram?.configured && telegram?.public_url_configured && (
                      <button disabled={busy} className="button secondary" type="button" onClick={() => run(async () => {
                        await api("/telegram/setup", {});
                        await refreshTelegram();
                      })}>{telegram.webhook_active ? "Refresh Telegram webhook" : "Activate Telegram webhook"}</button>
                    )}
                    {telegram?.linked ? (
                      <button disabled={busy} className="button destructive" type="button" onClick={() => {
                        if (window.confirm("Disconnect Telegram from ORA? The bot will no longer be linked to this workspace. Your Telegram account itself is unchanged.")) {
                          run(async () => {
                            await api("/telegram/link", null, "DELETE");
                            setTelegramLink(null);
                            await refreshTelegram();
                          });
                        }
                      }}>Disconnect Telegram</button>
                    ) : telegram?.configured && telegram?.public_url_configured && telegram?.webhook_active ? (
                      <>
                        <button disabled={busy} className="button primary" type="button" onClick={() => run(async () => setTelegramLink(await api("/telegram/pairing-code", {})))}>Generate Telegram link</button>
                        {telegramLink && <div className="pair-code"><a href={telegramLink.url} target="_blank" rel="noreferrer">Open @{telegram.username} in Telegram</a><small>One-time link · expires in 10 minutes.</small></div>}
                      </>
                    ) : telegram && !telegram.configured ? (
                      <p className="muted">Telegram bot setup is not available on this backend yet.</p>
                    ) : telegram?.configured && !telegram.public_url_configured ? (
                      <p className="muted">Set the backend’s public HTTPS URL before Telegram can create a link.</p>
                    ) : null}
                    {telegram?.linked && <p className="muted">Send text or a voice note to the bot. ORA prepares changes for review; a message draft is not sent until you choose a recipient and send it in your messaging app.</p>}
                  </section>

                  <section id="voice" className="panel settings-panel">
                    <h2>Voice</h2>
                    <label>
                      Available browser voices
                      <select value={voice} onChange={(event) => {
                        setVoice(event.target.value);
                        save("voice", event.target.value);
                      }}>
                        <option value="">System default</option>
                        {voices.map((item) => <option key={item.voiceURI} value={item.voiceURI}>{item.name} · {item.lang}</option>)}
                      </select>
                    </label>
                    {!voices.length && <small>No installed browser voices are available yet. The system default may still work.</small>}
                    <button className="button secondary" type="button" onClick={() => speak("Hello. I’m ORA. Let’s make a little room for your next useful step.")}><Icon name="sound" /> Preview voice</button>
                    <label className="toggle">
                      <input type="checkbox" checked={autoSpeak} onChange={(event) => setAutoSpeak(event.target.checked)} />
                      Read replies aloud in this session only
                    </label>
                    <p className="muted">Playback uses an available browser speech engine. Voice selection and automatic playback are kept for this session’s preferences only.</p>
                  </section>

                  <section id="your-rhythm" className="panel settings-panel">
                    <h2>Your rhythm</h2>
                    <p>Set the name and timezone ORA should use, along with quiet-hour preferences for supported planning nudges.</p>
                    <form className="rhythm" aria-busy={busy} onSubmit={(event) => {
                      event.preventDefault();
                      const form = new FormData(event.currentTarget);
                      run(() => change("settings.update", {
                        name: form.get("name"),
                        timezone: form.get("timezone"),
                        quiet_start: Number(form.get("quiet_start")),
                        quiet_end: Number(form.get("quiet_end")),
                      }));
                    }} key={`${data?.settings?.name}-${data?.settings?.timezone}`}>
                      <label>Your name<input name="name" defaultValue={data?.settings?.name} maxLength={60} required /></label>
                      <label>Timezone<input name="timezone" defaultValue={data?.settings?.timezone} required placeholder="Africa/Nairobi" /></label>
                      <label>Quiet hours start (0–23)<input name="quiet_start" type="number" min="0" max="23" defaultValue={data?.settings?.quiet_start} /></label>
                      <label>Quiet hours end (0–23)<input name="quiet_end" type="number" min="0" max="23" defaultValue={data?.settings?.quiet_end} /></label>
                      <button className="button primary" type="submit" disabled={busy}>Save preferences</button>
                    </form>
                  </section>

                  <section id="share-drafts" className="panel settings-panel">
                    <h2>Ready to share</h2>
                    <p>These are drafts prepared by ORA and approved by you. ORA has not sent them.</p>
                    {(data?.actions || []).filter((item) => item.status === "ready_to_share").length ? (
                      (data?.actions || []).filter((item) => item.status === "ready_to_share").map((item) => (
                        <article className="share-draft" key={item.id}>
                          <h3>Draft for {item.payload.recipient || "your chosen recipient"}</h3>
                          <blockquote>{item.payload.body}</blockquote>
                          <button className="button secondary" type="button" onClick={() => run(async () => {
                            setShareStatus("");
                            if (navigator.share) {
                              try {
                                await navigator.share({ text: item.payload.body });
                                setShareStatus("Share sheet opened. Choose the recipient and send it yourself; ORA has not sent it.");
                              } catch (error) {
                                if (error.name === "AbortError") {
                                  setShareStatus("Share sheet closed. The draft was not sent.");
                                  return;
                                }
                                throw error;
                              }
                            } else {
                              await navigator.clipboard.writeText(item.payload.body);
                              setShareStatus("Draft copied. Choose a recipient and send it in your messaging app; ORA has not sent it.");
                            }
                          })}>Share or copy draft</button>
                          {shareStatus && <p role="status" aria-live="polite">{shareStatus}</p>}
                        </article>
                      ))
                    ) : <Empty>No approved message drafts are waiting to be shared.</Empty>}
                  </section>

                  <section id="connection-health" className="panel settings-panel readiness-panel">
                    <div className="section-heading">
                      <h2>Connection health</h2>
                      <button className="button quiet" type="button" disabled={readinessLoading} onClick={refreshReadiness}>{readinessLoading ? "Checking…" : "Refresh status"}</button>
                    </div>
                    {readinessLoading && !readiness && <p role="status">Checking backend readiness…</p>}
                    {readinessError && <div role="alert" className="global-notice error-notice"><div><strong>Could not check backend readiness</strong><p>{readinessError}</p></div><button className="button secondary" type="button" onClick={refreshReadiness}>Retry</button></div>}
                    {readiness && <>
                      <p><strong>AI provider:</strong> {readiness.ai_configured ? "Configuration is present. Send a message to verify a reply." : "Needs setup on the backend."}</p>
                      <p><strong>Automation:</strong> {readiness.scheduler_configured ? "Scheduler credential configured." : "Scheduler credential missing."}</p>
                      <p className="muted">Last completed run: {readiness.scheduler_last_completed_at ? <time dateTime={readiness.scheduler_last_completed_at}>{dateLabel(readiness.scheduler_last_completed_at, data?.settings?.timezone)}</time> : "No completed run recorded yet."}</p>
                    </>}
                    <p className="muted">Phone reminders are scheduled locally after the paired Android syncs. This page reports backend configuration; it does not represent continuous monitoring.</p>
                  </section>
                </div>
              </div>
            </>
          )}
        </div>
        <footer className="page-footer">
          <span>ORA Mini · Personal workspace</span>
          <span>Built around you.</span>
        </footer>
      </main>
      <MoreSheet open={moreOpen} onClose={() => setMoreOpen(false)} currentPage={page} />
      <nav className="mobile-nav" aria-label="Mobile primary navigation">
        {CORE_NAV_ITEMS.map((item) => (
          <NavLink key={item.id} to={item.path}>
            <Icon name={item.icon} size={20} />
            <span>{item.label}</span>
          </NavLink>
        ))}
        <button
          type="button"
          className={MORE_NAV_ITEMS.some((item) => item.id === page) || moreOpen ? "selected" : ""}
          aria-haspopup="dialog"
          aria-expanded={moreOpen}
          aria-pressed={MORE_NAV_ITEMS.some((item) => item.id === page)}
          aria-label={MORE_NAV_ITEMS.some((item) => item.id === page) ? `More workspace. Current section: ${currentSection?.title}` : "More workspace sections"}
          onClick={() => setMoreOpen(true)}
        >
          <Icon name="settings" size={20} />
          <span>More</span>
        </button>
      </nav>
    </div>
  );
}

