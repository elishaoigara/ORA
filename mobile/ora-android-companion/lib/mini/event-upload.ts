import type { NativeNotificationEvent } from "@/modules/ora-notification-listener/src/OraNotificationListenerModule";

/** Acknowledge each upload so a later failure cannot replay successful items. */
export async function flushEvents(
  events: NativeNotificationEvent[],
  upload: (event: NativeNotificationEvent) => Promise<unknown>,
  acknowledge: (ids: string[]) => void,
  clock = Date.now(),
) {
  for (const event of events) {
    const observed = Date.parse(event.occurredAt);
    if (!Number.isFinite(observed) || clock - observed > 86400000 || observed - clock > 300000) {
      acknowledge([event.id]);
      continue;
    }
    await upload(event);
    acknowledge([event.id]);
  }
}
