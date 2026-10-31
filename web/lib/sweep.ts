import type { StepEvent } from "./types";

export const AGENT_CARDS = [
  { key: "gem", label: "GeM", hint: "bidplus.gem.gov.in" },
  { key: "cppp", label: "CPPP", hint: "eprocure.gov.in" },
  { key: "haryana", label: "Haryana e-proc", hint: "etenders.hry.nic.in" },
  { key: "corrigenda", label: "Corrigenda", hint: "TinyFish Search" },
] as const;

export type CardKey = (typeof AGENT_CARDS)[number]["key"];
export type CardStatus = "idle" | "running" | "done" | "error";

export interface CardState {
  status: CardStatus;
  steps: number;
  message: string;
  count: number | null;
  directUrl: string | null;
}

export interface SweepState {
  cards: Record<CardKey, CardState>;
  pipeline: string;
  error: string | null;
  finished: boolean;
  summary: string | null;
  /** After all/done: new documents still being read ("Reading 3 new documents…"), null once settled. */
  background: string | null;
}

const idleCard = (): CardState => ({ status: "idle", steps: 0, message: "Waiting", count: null, directUrl: null });

export function initialSweep(): SweepState {
  return {
    cards: { gem: idleCard(), cppp: idleCard(), haryana: idleCard(), corrigenda: idleCard() },
    pipeline: "",
    error: null,
    finished: false,
    summary: null,
    background: null,
  };
}

/** Fold one §3.3 event into the panel state. Idempotent under a full replay (reconnects replay the log). */
export function applyEvent(s: SweepState, ev: StepEvent): SweepState {
  if (ev.agent === "all") {
    if (ev.type === "done") {
      // A card still running when the sweep ends never reported back (sweep lost or stopped).
      const cards = Object.fromEntries(Object.entries(s.cards).map(([k, c]) =>
        [k, c.status === "running" ? { ...c, status: "error" as const, message: "Ended without a result" } : c],
      )) as SweepState["cards"];
      const pending = ev.pending ?? 0;
      return { ...s, cards, finished: true, summary: ev.message, pipeline: "",
               background: pending > 0 ? `Reading ${pending} new document${pending === 1 ? "" : "s"} in the background` : null };
    }
    if (ev.type === "update") return s.background === null ? s : { ...s, background: ev.message };
    if (ev.type === "settled") return { ...s, background: null, summary: s.summary ? `${s.summary}. ${ev.message}.` : `${ev.message}.` };
    if (ev.type === "error") return { ...s, error: ev.message };
    return { ...s, pipeline: ev.message };
  }
  const key = ev.agent as CardKey;
  const prev = s.cards[key];
  if (!prev) return s;
  let next: CardState;
  switch (ev.type) {
    case "started":
      next = { ...idleCard(), status: "running", message: ev.message };
      break;
    case "step":
      next = { ...prev, status: prev.status === "idle" ? "running" : prev.status,
               steps: Math.max(prev.steps, ev.step), message: ev.message };
      break;
    case "result":
      next = { ...prev, status: "done", steps: Math.max(prev.steps, ev.step), message: ev.message, count: ev.count ?? 0 };
      break;
    case "error":
      next = { ...prev, status: "error", steps: Math.max(prev.steps, ev.step), message: ev.message,
               directUrl: ev.direct_url };
      break;
    default:
      return s;
  }
  return { ...s, cards: { ...s.cards, [key]: next } };
}
