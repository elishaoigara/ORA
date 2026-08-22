import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  acknowledgeCommandAlert,
  checkIn,
  clearDeviceSession,
  completeCommandTask,
  type AwarenessState,
  type CommandCenter,
  type CommandPreferences,
  type DeviceRecord,
  type DeviceSession,
  getAwarenessState,
  getCommandCenter,
  getCurrentDevice,
  loadDeviceSession,
  pairWithOra,
  revokeCurrentDevice,
  updateCommandPreferences as persistCommandPreferences,
} from "@/lib/ora-device";
import { clearedDeviceState, pairedDeviceState } from "@/lib/device-session-state";

type PairInput = { backendUrl: string; pairingCode: string; deviceName: string };

type DeviceContextValue = {
  session: DeviceSession | null;
  device: DeviceRecord | null;
  awareness: AwarenessState | null;
  commandCenter: CommandCenter | null;
  loading: boolean;
  busy: boolean;
  error: string | null;
  pair: (input: PairInput) => Promise<void>;
  refresh: () => Promise<void>;
  refreshAwareness: () => Promise<void>;
  refreshCommandCenter: () => Promise<void>;
  sendCheckIn: () => Promise<void>;
  completeTask: (taskId: number) => Promise<void>;
  acknowledgeAlert: (alertId: number) => Promise<void>;
  updateCommandPreferences: (updates: Partial<CommandPreferences>) => Promise<void>;
  revoke: () => Promise<void>;
  forgetLocalSession: () => Promise<void>;
};

const DeviceContext = createContext<DeviceContextValue | null>(null);

export function DeviceProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<DeviceSession | null>(null);
  const [device, setDevice] = useState<DeviceRecord | null>(null);
  const [awareness, setAwareness] = useState<AwarenessState | null>(null);
  const [commandCenter, setCommandCenter] = useState<CommandCenter | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const latest = await getCurrentDevice(session);
      setDevice(latest);
      setSession((current) => (current ? { ...current, device: latest } : null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to refresh device status.");
    } finally {
      setBusy(false);
    }
  }, [session]);

  const refreshAwareness = useCallback(async () => {
    if (!session) {
      setAwareness(null);
      return;
    }
    try {
      setAwareness(await getAwarenessState(session));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load awareness settings.");
    }
  }, [session]);

  const refreshCommandCenter = useCallback(async () => {
    if (!session) {
      setCommandCenter(null);
      return;
    }
    try {
      setCommandCenter(await getCommandCenter(session));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load the ORA command center.");
    }
  }, [session]);

  useEffect(() => {
    let active = true;
    loadDeviceSession()
      .then((stored) => {
        if (!active || !stored) return;
        const next = pairedDeviceState(stored);
        setSession(next.session);
        setDevice(next.device);
      })
      .catch(() => {
        if (active) setError("Unable to load the local companion credential.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (session) void refresh();
  }, [refresh, session]);

  useEffect(() => {
    if (session) void refreshAwareness();
  }, [refreshAwareness, session]);

  useEffect(() => {
    if (session) void refreshCommandCenter();
  }, [refreshCommandCenter, session]);

  const pair = useCallback(async (input: PairInput) => {
    setBusy(true);
    setError(null);
    try {
      const next = await pairWithOra(input);
      const paired = pairedDeviceState(next);
      setSession(paired.session);
      setDevice(paired.device);
      setAwareness(null);
      setCommandCenter(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to pair this device.";
      setError(message);
      throw new Error(message);
    } finally {
      setBusy(false);
    }
  }, []);

  const sendCheckIn = useCallback(async () => {
    if (!session) throw new Error("Pair this device before sending a check-in.");
    setBusy(true);
    setError(null);
    try {
      const latest = await checkIn(session);
      setDevice(latest);
      setSession((current) => (current ? { ...current, device: latest } : null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "ORA could not receive the check-in.");
      throw err;
    } finally {
      setBusy(false);
    }
  }, [session]);

  const completeTask = useCallback(async (taskId: number) => {
    if (!session) throw new Error("Pair this device before completing a task.");
    setBusy(true);
    setError(null);
    try {
      await completeCommandTask(session, taskId);
      await refreshCommandCenter();
    } catch (err) {
      const message = err instanceof Error ? err.message : "ORA could not complete this task.";
      setError(message);
      throw new Error(message);
    } finally {
      setBusy(false);
    }
  }, [refreshCommandCenter, session]);

  const acknowledgeAlert = useCallback(async (alertId: number) => {
    if (!session) throw new Error("Pair this device before acknowledging an alert.");
    setBusy(true);
    setError(null);
    try {
      await acknowledgeCommandAlert(session, alertId);
      await refreshCommandCenter();
    } catch (err) {
      const message = err instanceof Error ? err.message : "ORA could not acknowledge this alert.";
      setError(message);
      throw new Error(message);
    } finally {
      setBusy(false);
    }
  }, [refreshCommandCenter, session]);

  const updateCommandPrefs = useCallback(async (updates: Partial<CommandPreferences>) => {
    if (!session) throw new Error("Pair this device before changing command-center preferences.");
    setBusy(true);
    setError(null);
    try {
      await persistCommandPreferences(session, updates);
      await refreshCommandCenter();
    } catch (err) {
      const message = err instanceof Error ? err.message : "ORA could not update these preferences.";
      setError(message);
      throw new Error(message);
    } finally {
      setBusy(false);
    }
  }, [refreshCommandCenter, session]);

  const revoke = useCallback(async () => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      await revokeCurrentDevice(session);
      const cleared = clearedDeviceState();
      setSession(cleared.session);
      setDevice(cleared.device);
      setAwareness(null);
      setCommandCenter(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "ORA could not revoke this device.");
      throw err;
    } finally {
      setBusy(false);
    }
  }, [session]);

  const forgetLocalSession = useCallback(async () => {
    await clearDeviceSession();
    const cleared = clearedDeviceState();
    setSession(cleared.session);
    setDevice(cleared.device);
    setAwareness(null);
    setCommandCenter(null);
    setError(cleared.error);
  }, []);

  const value = useMemo(
    () => ({
      session,
      device,
      awareness,
      commandCenter,
      loading,
      busy,
      error,
      pair,
      refresh,
      refreshAwareness,
      refreshCommandCenter,
      sendCheckIn,
      completeTask,
      acknowledgeAlert,
      updateCommandPreferences: updateCommandPrefs,
      revoke,
      forgetLocalSession,
    }),
    [
      session,
      device,
      awareness,
      commandCenter,
      loading,
      busy,
      error,
      pair,
      refresh,
      refreshAwareness,
      refreshCommandCenter,
      sendCheckIn,
      completeTask,
      acknowledgeAlert,
      updateCommandPrefs,
      revoke,
      forgetLocalSession,
    ],
  );

  return <DeviceContext.Provider value={value}>{children}</DeviceContext.Provider>;
}

export function useDevice() {
  const value = useContext(DeviceContext);
  if (!value) throw new Error("useDevice must be used inside DeviceProvider");
  return value;
}
