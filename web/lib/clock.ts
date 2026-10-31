/**
 * The API's clock (api/clock.py). In FALLBACK_MODE the API runs on a frozen demo clock (DEMO_NOW, or the
 * newest fixture's recorded_at) so recorded deadlines never expire; countdowns must use the same "now".
 * Live, the server and browser clocks agree and the offset is ~0.
 */
let offsetMs = 0;

export function syncFromServer(serverNowIso: string | null | undefined, localNow: number = Date.now()): void {
  const t = serverNowIso ? new Date(serverNowIso).getTime() : NaN;
  offsetMs = Number.isNaN(t) ? 0 : t - localNow;
}

export function now(): Date {
  return new Date(Date.now() + offsetMs);
}
