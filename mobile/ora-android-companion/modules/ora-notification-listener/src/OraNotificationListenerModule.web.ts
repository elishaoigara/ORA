import { registerWebModule, NativeModule } from "expo";

type NativeNotificationSource = {
  packageName: string;
  appLabel: string;
  contentMode: "metadata" | "redacted" | "full";
  enabled: boolean;
};

// The feature is Android-only and intentionally unavailable on web previews.
class OraNotificationListenerModule extends NativeModule<{}> {
  getListenerStatus() {
    return { available: false, accessGranted: false, configured: false, queuedEventCount: 0 };
  }

  openNotificationListenerSettings() {
    return false;
  }

  configure(_enabled: boolean, _sources: NativeNotificationSource[]) {}

  getPendingEvents() {
    return [];
  }

  clearPendingEvents() {}
  acknowledgeEvents(_ids: string[]) {}
}

export default registerWebModule(OraNotificationListenerModule, "OraNotificationListener");

