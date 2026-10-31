"use client";

import Link from "next/link";
import Icon from "@/components/ui/Icon";
import { safeHref } from "@/lib/format";
import { AGENT_CARDS, type CardStatus, type SweepState } from "@/lib/sweep";

export const STATUS: Record<CardStatus, { label: string; text: string; dot: string }> = {
  idle: { label: "Waiting", text: "text-slate-500", dot: "bg-slate-300" },
  running: { label: "Running", text: "text-amber-700", dot: "bg-amber-400 animate-pulse" },
  done: { label: "Done", text: "text-emerald-700", dot: "bg-emerald-500" },
  error: { label: "Needs you", text: "text-rose-700", dot: "bg-rose-500" },
};

export const sweepTouched = (s: SweepState) =>
  Object.values(s.cards).some((c) => c.status !== "idle") || !!s.summary || !!s.error || !!s.pipeline;

/** Compact live agents row for Live Matches; the full cards are on Watched Portals. */
export default function AgentStrip({ state, portalsHref }: { state: SweepState; portalsHref: string }) {
  return (
    <div className="flex flex-col gap-3" aria-live="polite">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {AGENT_CARDS.map(({ key, label }) => {
          const c = state.cards[key];
          const st = STATUS[c.status];
          const href = safeHref(c.directUrl);
          return (
            <div key={key} className="flex flex-col gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-3">
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                  <span aria-hidden className={`h-2 w-2 rounded-full ${st.dot}`} />{label}
                </span>
                <span className={`text-[11px] font-semibold uppercase tracking-wide ${st.text}`}>{st.label}</span>
              </div>
              <div className="flex items-baseline gap-3 font-mono text-xs text-slate-600">
                <span><b className="text-base text-slate-900 tabular-nums">{c.steps}</b> steps</span>
                {c.count != null && <span><b className="text-base text-slate-900 tabular-nums">{c.count}</b> {key === "corrigenda" ? "new" : "bids"}</span>}
              </div>
              <p className="line-clamp-2 text-xs text-slate-500">{c.message}</p>
              {c.status === "error" && href && (
                <a href={href} target="_blank" rel="noopener noreferrer"
                   className="inline-flex items-center gap-1 self-start text-xs font-semibold text-slate-900 underline">
                  Open on portal <Icon name="out" className="h-3 w-3" />
                </a>
              )}
            </div>
          );
        })}
      </div>
      <SweepStatus state={state} />
      <Link href={portalsHref} className="self-start text-xs font-semibold text-slate-700 underline">Watch every agent step →</Link>
    </div>
  );
}

export function SweepStatus({ state }: { state: SweepState }) {
  if (!state.pipeline && !state.summary && !state.error && !state.background) return null;
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-700">
      {state.error && <p role="alert" className="text-rose-700">{state.error}</p>}
      {state.pipeline && <p><b className="text-slate-900">Working:</b> {state.pipeline}…</p>}
      {state.summary && <p><b className="text-slate-900">Done.</b> {state.summary}</p>}
      {state.background && <p role="status"><b className="text-slate-900">Still reading:</b> {state.background}…</p>}
    </div>
  );
}
