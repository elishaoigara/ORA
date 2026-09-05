import { NativeModule, requireOptionalNativeModule } from "expo";

export type NotificationContentMode = "metadata" | "redacted" | "full";

export type NativeNotificationSource = {
  packageName: string;
  appLabel: string;
  contentMode: NotificationContentMode;
  enabled: boolean;
};

export type NativeNotificationEvent = {
  id: string;
  packageName: string;
  appLabel: string;
  title: string;
  body: string;
  contentMode: NotificationContentMode;
  occurredAt: string;
};

export type ListenerStatus = {
  available: boolean;
  accessGranted: boolean;
  configured: boolean;
  queuedEventCount: number;
};

declare class OraNotificationListenerModule extends NativeModule<{
  onNotificationPosted: (event: NativeNotificationEvent) => void;
}> {
  getListenerStatus(): ListenerStatus;
  openNotificationListenerSettings(): boolean;
  configure(enabled: boolean, sources: NativeNotificationSource[]): void;
  getPendingEvents(): NativeNotificationEvent[];
  clearPendingEvents(): void;
  acknowledgeEvents(ids: string[]): void;
}

export default requireOptionalNativeModule<OraNotificationListenerModule>("OraNotificationListener");

