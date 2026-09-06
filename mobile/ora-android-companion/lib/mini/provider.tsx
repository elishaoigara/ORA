import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { applyLocal, validateTask } from "./offline";
import { notificationListeners, registerPush } from "./notification-center";
import { AppState } from "react-native";
import {
  ApiError,
  clearSession,
  makeId,
  Op,
  pair,
  readLocal,
  request,
  session,
  Session,
  Snapshot,
  writeLocal,
} from "./api";
import { cancelReminders, reconcileReminders } from "./reminders";
import NativeListener from "@/modules/ora-notification-listener/src/OraNotificationListenerModule";
type Context = {
  session: Session | null;
  data: Snapshot | null;
  status: string;
  error: string;
  queue: Op[];
  sync: () => Promise<void>;
  connect: (url: string, code: string) => Promise<void>;
  mutate: (kind: string, payload: Record<string, unknown>) => Promise<void>;
  ask: (text: string) => Promise<string>;
  disconnect: () => Promise<void>;
  clearQueue: () => Promise<void>;
  setError: (value: string) => void;
};
const MiniContext = createContext<Context | null>(null);
export function MiniProvider({ children }: { children: React.ReactNode }) {
  const [active, setActive] = useState<Session | null>(null);
  const [data, setData] = useState<Snapshot | null>(null);
  const [status, setStatus] = useState("Opening your workspace");
  const [error, setError] = useState("");
  const [queue, setQueue] = useState<Op[]>([]);
  const syncing = useRef(false);
  const sync = useCallback(async () => {
    if (syncing.current || !(await session())) return;
    syncing.current = true;
    setStatus("Connecting · allow a minute");
    try {
      const pending = await readLocal<Op[]>("outbox", []);
      for (const op of [...pending]) {
        try {
          await request("/operations", op);
        } catch (e) {
          if (e instanceof ApiError && e.status > 0 && e.status < 500) {
            setError("A queued change needs attention: " + e.message);
            break;
          }
          throw e;
        }
        const remaining = (await readLocal<Op[]>("outbox", [])).filter(
          (item) => item.request_id !== op.request_id,
        );
        await writeLocal("outbox", remaining);
        setQueue(remaining);
      }
      const server = await request<Snapshot>("/sync");
      const next = (await readLocal<Op[]>("outbox", [])).reduce(
        applyLocal,
        server,
      );
      setData(next);
      await writeLocal("snapshot", next);
      let count = 0;
      try {
        count = await reconcileReminders(next);
      } catch {
        setError(
          "Tasks are saved. Open the notification center to allow notifications and precise reminder timing, then sync.",
        );
      }
      await writeLocal("lastSync", new Date().toISOString());
      if (
        (await readLocal("pushEnabled", false)) &&
        (await readLocal("pushRetryAt", 0)) < Date.now()
      ) {
        await writeLocal("pushRetryAt", Date.now() + 3600000);
        void registerPush().catch((e) =>
          writeLocal("notificationError", String(e)),
        );
      }
      const device = next.devices.find((d) => d.id === next.device_id);
      if (!device || device.paused || !device.permissions.notifications) {
        NativeListener?.configure(false, []);
      }
      try {
        if (device && !device.paused && device.permissions.notifications) {
          const events = NativeListener?.getPendingEvents() || [];
          for (const e of events) {
            if (Date.now() - Date.parse(e.occurredAt) > 86400000) continue;
            await request("/events", {
              request_id: e.id,
              kind: "notifications",
              text: `${e.appLabel}: ${e.title} ${e.body}`.slice(0, 1200),
              observed_at: e.occurredAt,
            });
          }
          // Acknowledge only the events included in this snapshot; preserve new arrivals.
          NativeListener?.acknowledgeEvents(events.map((e) => e.id));
        }
      } catch {
        setError(
          "Workspace synced. Phone context upload will retry separately.",
        );
      }
      setStatus(`Synced · ${count} phone reminders`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
      setStatus("Offline · saved workspace");
      if (e instanceof ApiError && e.status === 401) {
        NativeListener?.configure(false, []);
        await cancelReminders();
        await clearSession();
        setActive(null);
        setData(null);
        setQueue([]);
      }
    } finally {
      syncing.current = false;
    }
  }, []);
  useEffect(() => {
    let alive = true;
    (async () => {
      const s = await session();
      if (!alive) return;
      setActive(s);
      if (s) {
        const cached = await readLocal<Snapshot | null>("snapshot", null);
        setData(cached);
        if (cached) {
          try {
            await reconcileReminders(cached);
          } catch {
            setError(
              "Check notification and exact-alarm permissions in the notification center.",
            );
          }
        }
        setQueue(await readLocal<Op[]>("outbox", []));
        await sync();
      } else setStatus("Pair your phone");
    })();
    const subscription = AppState.addEventListener("change", (s) => {
      if (s === "active") sync();
    });
    const timer = setInterval(() => {
      if (AppState.currentState === "active") sync();
    }, 60000);
    return () => {
      alive = false;
      subscription.remove();
      clearInterval(timer);
    };
  }, [sync]);
  const connect = async (url: string, code: string) => {
    setActive(await pair(url, code));
    await sync();
  };
  const mutationChain = useRef<Promise<unknown>>(Promise.resolve());
  const performMutation = async (
    kind: string,
    payload: Record<string, unknown>,
  ) => {
    const op = { request_id: makeId(), kind, payload };
    if (
      [
        "task.create",
        "task.complete",
        "task.update",
        "task.delete",
        "memory.save",
      ].includes(kind)
    ) {
      if (kind === "task.create" || kind === "task.update")
        validateTask(payload);
      const cached = await readLocal<Snapshot | null>("snapshot", null);
      if (!cached)
        throw new Error(
          "Sync your workspace once before creating offline changes.",
        );
      const pending = [...(await readLocal<Op[]>("outbox", [])), op];
      if (pending.length > 100) throw new Error("Sync queued changes first.");
      await writeLocal("outbox", pending);
      const next = applyLocal(cached, op);
      await writeLocal("snapshot", next);
      setQueue(pending);
      setData(next);
      try {
        await reconcileReminders(next);
      } catch {
        setError(
          "Task saved. Allow notifications and precise reminder timing, then sync to schedule it.",
        );
      }
      setStatus("Saved on phone · syncing");
      void sync();
      return;
    }
    try {
      await request("/operations", op);
      await sync();
    } catch (e) {
      if (
        e instanceof ApiError &&
        !e.status &&
        ["task.create", "task.complete", "memory.save"].includes(kind)
      ) {
        const pending = [...(await readLocal<Op[]>("outbox", [])), op];
        if (pending.length > 100)
          throw new Error("Sync or clear queued changes before adding more.");
        await writeLocal("outbox", pending);
        setQueue(pending);
        setStatus("Change saved on this phone · waiting to sync");
      } else throw e;
    }
  };
  const mutate = (
    kind: string,
    payload: Record<string, unknown>,
  ): Promise<void> => {
    const next = mutationChain.current.then(() =>
      performMutation(kind, payload),
    );
    mutationChain.current = next.catch(() => {});
    return next;
  };
  useEffect(
    () => notificationListeners((kind, payload) => mutate(kind, payload), sync),
    [active],
  );
  const ask = async (text: string) => {
    const old = await readLocal<{ request_id: string; text: string } | null>(
      "pendingChat",
      null,
    );
    const payload = old?.text === text ? old : { request_id: makeId(), text };
    await writeLocal("pendingChat", payload);
    const result = await request<{ reply: string }>("/chat", payload);
    await writeLocal("pendingChat", null);
    await sync();
    return result.reply;
  };
  const disconnect = async () => {
    NativeListener?.configure(false, []);
    await cancelReminders();
    try {
      await request("/operations", {
        request_id: makeId(),
        kind: "device.revoke",
        payload: {},
      });
    } catch {
      setError(
        "Local data cleared. Revoke this device from the web if the server was offline.",
      );
    }
    await clearSession();
    setActive(null);
    setData(null);
    setQueue([]);
  };
  const clearQueue = async () => {
    await writeLocal("outbox", []);
    setQueue([]);
    await sync();
  };
  return (
    <MiniContext.Provider
      value={{
        session: active,
        data,
        status,
        error,
        queue,
        sync,
        connect,
        mutate,
        ask,
        disconnect,
        clearQueue,
        setError,
      }}
    >
      {children}
    </MiniContext.Provider>
  );
}
export function useMini() {
  const value = useContext(MiniContext);
  if (!value) throw new Error("MiniProvider missing");
  return value;
}
