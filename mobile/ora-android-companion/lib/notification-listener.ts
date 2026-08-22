import { Platform } from "react-native";

import NativeOraNotificationListener, {
  type ListenerStatus,
  type NativeNotificationEvent,
} from "@/modules/ora-notification-listener/src/OraNotificationListenerModule";
import type { DeviceSession, NotificationSource } from "@/lib/ora-device";
import { submitNotificationAuditEvent } from "@/lib/ora-device";

const unavailableStatus: ListenerStatus = {
  available: false,
  accessGranted: false,
  configured: false,
  queuedEventCount: 0,
};

function nativeModule() {
  return Platform.OS === "android" ? NativeOraNotificationListener : null;
}

export function getNotificationListenerStatus(): ListenerStatus {
  return nativeModule()?.getListenerStatus() ?? unavailableStatus;
}

export function openNotificationListenerSettings(): boolean {
  return nativeModule()?.openNotificationListenerSettings() ?? false;
}

export function configureNotificationListener(enabled: boolean, sources: NotificationSource[]): void {
  nativeModule()?.configure(
    enabled,
    sources.map((source) => ({
      packageName: source.package_name,
      appLabel: source.app_label,
      contentMode: source.content_mode,
      enabled: source.enabled,
    })),
  );
}

export function clearQueuedNotificationEvents(): void {
  nativeModule()?.clearPendingEvents();
}

/**
 * Upload only events already admitted by the device-local allowlist. The queue
 * remains intact on an error so the user can decide whether to retry or clear it.
 */
export async function synchronizeQueuedNotificationEvents(session: DeviceSession): Promise<number> {
  const module = nativeModule();
  if (!module) return 0;
  const queued: NativeNotificationEvent[] = module.getPendingEvents();
  for (const event of queued) {
    await submitNotificationAuditEvent(session, {
      package_name: event.packageName,
      title: event.title,
      body: event.body,
    });
  }
  module.clearPendingEvents();
  return queued.length;
}
