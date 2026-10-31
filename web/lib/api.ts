import { syncFromServer } from "./clock";
import type { AlertResult, AlertStatus, Health, MatchDetail, MatchSummary, Profile, ProfileInput } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers || {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, `Can't reach the TenderHawk API at ${API_URL}. Is it running?`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

async function health(): Promise<Health> {
  const h = await call<Health>("/health");
  syncFromServer(h.now);
  return h;
}

/** Deadlines are shown against the API's clock, so sync it once before the first match data renders. */
let clockSynced: Promise<unknown> | null = null;
function withClock<T>(load: () => Promise<T>): Promise<T> {
  clockSynced ??= health().catch(() => { clockSynced = null; });
  return clockSynced.then(load);
}

export const api = {
  health,
  createProfile: (p: ProfileInput) => call<{ id: number }>("/profiles", { method: "POST", body: JSON.stringify(p) }),
  profile: (id: number) => call<Profile>(`/profiles/${id}`),
  startSweep: (profileId: number) =>
    call<{ sweep_id: string }>("/sweeps", { method: "POST", body: JSON.stringify({ profile_id: profileId }) }),
  matches: (profileId: number) => withClock(() => call<MatchSummary[]>(`/profiles/${profileId}/matches`)),
  match: (id: number) => withClock(() => call<MatchDetail>(`/matches/${id}`)),
  alert: (id: number) => call<AlertResult>(`/matches/${id}/alert`, { method: "POST" }),
  alertPreview: (id: number) => call<{ preview: string }>(`/matches/${id}/alert/preview`),
  alertStatus: () => call<AlertStatus>("/alerts/status"),
  rematch: (profileId: number) => call<{ counts: Record<string, number> }>(`/profiles/${profileId}/match`, { method: "POST" }),
};

export const sweepEventsUrl = (sweepId: string) => `${API_URL}/sweeps/${encodeURIComponent(sweepId)}/events`;
