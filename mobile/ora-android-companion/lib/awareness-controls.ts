import { Platform } from "react-native";
import Constants from "expo-constants";
import * as Location from "expo-location";
import * as Notifications from "expo-notifications";

import {
  getAwarenessState,
  registerAwarenessPushToken,
  replaceAwarenessZones,
  setAwarenessConsent,
  testAwarenessPush,
  type AwarenessState,
  type AwarenessZone,
  type DeviceSession,
} from "@/lib/ora-device";
import {
  CONTINUOUS_LOCATION_TASK,
  getRuntimeSettings,
  saveRuntimeSettings,
  ZONE_TASK,
} from "@/lib/awareness-runtime";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

const LOCATION_FOREGROUND_OPTIONS: Location.LocationTaskOptions = {
  accuracy: Location.Accuracy.Balanced,
  timeInterval: 15 * 60 * 1000,
  distanceInterval: 250,
  deferredUpdatesInterval: 15 * 60 * 1000,
  foregroundService: {
    notificationTitle: "ORA location routine is active",
    notificationBody: "ORA is updating your private location routine. Tap ORA to manage or stop it.",
    notificationColor: "#00E6A7",
  },
};

function requireNativeAndroid() {
  if (Platform.OS !== "android") throw new Error("This awareness capability is available only in the Android Companion.");
}

async function requestForegroundThenBackgroundLocation() {
  requireNativeAndroid();
  if (!(await Location.hasServicesEnabledAsync())) {
    throw new Error("Turn on Android Location services before enabling this routine.");
  }
  const foreground = await Location.requestForegroundPermissionsAsync();
  if (foreground.status !== "granted") {
    throw new Error("Foreground location was not granted. ORA cannot start this routine.");
  }
  const background = await Location.requestBackgroundPermissionsAsync();
  if (background.status !== "granted") {
    throw new Error("Background location was not granted. The routine remains off.");
  }
}

async function applyGeofences(zones: AwarenessZone[]) {
  if (await Location.hasStartedGeofencingAsync(ZONE_TASK)) {
    await Location.stopGeofencingAsync(ZONE_TASK);
  }
  if (zones.length) {
    await Location.startGeofencingAsync(
      ZONE_TASK,
      zones.filter((zone) => zone.enabled).map((zone) => ({
        identifier: zone.id,
        latitude: zone.latitude,
        longitude: zone.longitude,
        radius: zone.radius_m,
        notifyOnEnter: true,
        notifyOnExit: true,
      })),
    );
  }
}

export async function enablePushAlerts(session: DeviceSession): Promise<AwarenessState> {
  requireNativeAndroid();
  await Notifications.setNotificationChannelAsync("ora-alerts", {
    name: "ORA alerts",
    importance: Notifications.AndroidImportance.HIGH,
    vibrationPattern: [0, 200, 120, 200],
    lightColor: "#00E6A7",
  });
  const permission = await Notifications.requestPermissionsAsync();
  if (permission.status !== "granted") {
    throw new Error("Android notification permission was not granted. Push alerts remain off.");
  }

  const projectId = Constants.expoConfig?.extra?.expoPushProjectId as string | undefined;
  if (!projectId) {
    throw new Error("Push is not configured for this build yet. Add the Expo push project ID, rebuild, and try again.");
  }

  await setAwarenessConsent(session, "push_alerts", true);
  try {
    const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
    await registerAwarenessPushToken(session, token);
    await testAwarenessPush(session);
    return await getAwarenessState(session);
  } catch (error) {
    await setAwarenessConsent(session, "push_alerts", false).catch(() => undefined);
    throw error;
  }
}

export async function disablePushAlerts(session: DeviceSession): Promise<AwarenessState> {
  return setAwarenessConsent(session, "push_alerts", false);
}

export async function enableZoneRoutines(session: DeviceSession): Promise<AwarenessState> {
  await requestForegroundThenBackgroundLocation();
  const next = await setAwarenessConsent(session, "zone_routines", true);
  const runtime = await getRuntimeSettings();
  await applyGeofences(runtime.zones);
  return next;
}

export async function disableZoneRoutines(session: DeviceSession): Promise<AwarenessState> {
  if (Platform.OS === "android" && (await Location.hasStartedGeofencingAsync(ZONE_TASK))) {
    await Location.stopGeofencingAsync(ZONE_TASK);
  }
  const runtime = await getRuntimeSettings();
  await saveRuntimeSettings({ ...runtime, zones: [] });
  return setAwarenessConsent(session, "zone_routines", false);
}

export async function saveCurrentPlaceAsZone(
  session: DeviceSession,
  existingZones: AwarenessZone[],
  id: "home" | "work" | "commute",
  label: string,
): Promise<AwarenessState> {
  requireNativeAndroid();
  const foreground = await Location.requestForegroundPermissionsAsync();
  if (foreground.status !== "granted") throw new Error("Allow foreground location to save this named place.");
  const location = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
  const nextZones = [
    ...existingZones.filter((zone) => zone.id !== id),
    {
      id,
      label,
      latitude: location.coords.latitude,
      longitude: location.coords.longitude,
      radius_m: 200,
    },
  ];
  const zones = await replaceAwarenessZones(session, nextZones);
  const runtime = await getRuntimeSettings();
  await saveRuntimeSettings({ ...runtime, zones });
  await applyGeofences(zones);
  return getAwarenessState(session);
}

export async function enableContinuousLocation(session: DeviceSession, retentionHours = 24): Promise<AwarenessState> {
  await requestForegroundThenBackgroundLocation();
  const next = await setAwarenessConsent(session, "continuous_location", true, retentionHours);
  try {
    if (!(await Location.hasStartedLocationUpdatesAsync(CONTINUOUS_LOCATION_TASK))) {
      await Location.startLocationUpdatesAsync(CONTINUOUS_LOCATION_TASK, LOCATION_FOREGROUND_OPTIONS);
    }
    const runtime = await getRuntimeSettings();
    await saveRuntimeSettings({ ...runtime, continuousEnabled: true });
    return next;
  } catch (error) {
    await setAwarenessConsent(session, "continuous_location", false, retentionHours).catch(() => undefined);
    throw error;
  }
}

export async function disableContinuousLocation(session: DeviceSession): Promise<AwarenessState> {
  if (Platform.OS === "android" && (await Location.hasStartedLocationUpdatesAsync(CONTINUOUS_LOCATION_TASK))) {
    await Location.stopLocationUpdatesAsync(CONTINUOUS_LOCATION_TASK);
  }
  const runtime = await getRuntimeSettings();
  await saveRuntimeSettings({ ...runtime, continuousEnabled: false });
  return setAwarenessConsent(session, "continuous_location", false);
}
