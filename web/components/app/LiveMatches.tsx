"use client";

import Link from "next/link";
import { useState } from "react";
import ErrorBox from "@/components/ErrorBox";
import Icon, { type IconName } from "@/components/ui/Icon";
import VerdictChip from "@/components/VerdictChip";
import { deadline, inr, istDate, safeHref, verdictLabel } from "@/lib/format";
import { byVerdict, PORTAL_NAME, portalSummary, quotedReason, verdictCounts, type VerdictFilter } from "@/lib/matches";
import type { MatchSummary, Reason, Verdict } from "@/lib/types";
import AgentStrip, { sweepTouched } from "./AgentStrip";
import { useShell } from "./ProfileShell";

const WHY: Record<Verdict, string> = {
  ELIGIBLE: "Why you qualify",
  CHECK_DOCS: "What you need ready",
  NOT_ELIGIBLE: "Why you can’t bid",
};
const REASON_ICON: Record<Reason["kind"], { name: IconName; cls: string }> = {
  ok: { name: "check", cls: "text-emerald-600" },
  warn: { name: "warn", cls: "text-amber-600" },
  fail: { name: "x", cls: "text-rose-600" },
  info: { name: "info", cls: "text-blue-600" },
};

/** Stitch "Live Matches": the radar bar, the live agents, then every match with its reasons and quoted clause. */
export default function LiveMatches() {
  const s = useShell();
  const [filter, setFilter] = useState<VerdictFilter>("all");
  const [showLow, setShowLow] = useState(false);
  const relevant = (s.matches ?? []).filter((m) => m.relevant);
  const low = (s.matches ?? []).filter((m) => !m.relevant);
  const counts = verdictCounts(relevant);
  const soon = relevant.filter((m) => { const d = deadline(m.tender.end_date); return !d.closed && d.urgent; }).length;
  const shown = byVerdict(relevant, filter);
  const p = s.profile;

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div className="flex items-center gap-4">
            <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-slate-100 text-navy">
              <Icon name="radar" className="h-6 w-6" />
              {s.running && <span className="absolute right-2 top-2 h-2 w-2 animate-pulse rounded-full bg-amber" />}
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-lg font-bold text-slate-900">{s.running ? "Hawk radar sweeping" : "Hawk radar"}</h1>
                {s.fallback && <span className="rounded border border-blue-200 bg-blue-50 px-2 py-0.5 font-mono text-xs font-medium text-blue-800">replay</span>}
              </div>
              <p className="mt-1 text-xs text-slate-500">
                TinyFish agents on GeM, CPPP and Haryana e-Procurement
                {p && <> · searching for <b className="text-slate-700">{(p.keywords.length ? p.keywords : p.products).join(", ") || "—"}</b></>}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {p?.phone && (
              <span className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700">
                <Icon name="chat" className="h-4 w-4 text-amber-600" />{p.phone}
              </span>
            )}
            {s.running && (
              <button onClick={s.stopWatching} className="rounded-lg border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50">
                Stop watching
              </button>
            )}
          </div>
        </div>
        <dl className="mt-6 grid grid-cols-2 gap-4 border-t border-slate-100 pt-5 lg:grid-cols-4">
          <Metric label="Your turnover" value={p ? inr(p.annual_turnover) : "…"} note={p?.states_served.join(", ") || "states not set"} />
          <Metric label="Relevant tenders" value={s.matches ? String(relevant.length) : "…"} note={portalSummary(relevant) || "none yet"} />
          <Metric label="You can bid" value={s.matches ? String(counts.ELIGIBLE) : "…"} note="verdicts from the bid documents" tone="ok" />
          <Metric label="Closing within 48 h" value={s.matches ? String(soon) : "…"} note="act on these first" />
        </dl>
      </section>

      {s.lost && <p role="status" className="text-sm text-amber-700">Lost the live connection. Reconnecting…</p>}
      {sweepTouched(s.sweep) && <AgentStrip state={s.sweep} portalsHref={`/profiles/${s.profileId}/portals`} />}

      <section className="flex flex-col gap-4">
        <div className="flex flex-col justify-between gap-3 md:flex-row md:items-center">
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by verdict">
            {([["all", `All matches (${relevant.length})`], ["ELIGIBLE", `${verdictLabel("ELIGIBLE")} (${counts.ELIGIBLE})`],
               ["CHECK_DOCS", `${verdictLabel("CHECK_DOCS")} (${counts.CHECK_DOCS})`],
               ["NOT_ELIGIBLE", `Can’t bid (${counts.NOT_ELIGIBLE})`]] as [VerdictFilter, string][]).map(([f, label]) => (
              <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
                      className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-colors ${filter === f
                        ? "bg-navy text-white shadow-sm" : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-100"}`}>
                {label}
              </button>
            ))}
          </div>
          <button onClick={s.loadMatches} className="self-start text-xs font-semibold text-slate-600 underline md:self-auto">Refresh</button>
        </div>

        {s.matchError ? <ErrorBox message={s.matchError} onRetry={s.loadMatches} />
          : !s.matches ? <Skeleton />
          : !s.matches.length ? (
            <Empty title="No matches yet" body="Press Sweep now: the agents search the portals for your products and read each bid document." />
          ) : !shown.length ? (
            <Empty title="Nothing here" body={relevant.length ? "No relevant tender has this verdict." : "No tenders matched your products in this sweep."} />
          ) : (
            <ul className="flex flex-col gap-5">{shown.map((m) => <TenderCard key={m.id} m={m} />)}</ul>
          )}

        {low.length > 0 && (
          <div className="flex flex-col gap-3">
            <button onClick={() => setShowLow(!showLow)} aria-expanded={showLow} className="self-start text-sm font-semibold text-slate-600 underline">
              {showLow ? "Hide" : "Show"} {low.length} low-relevance tender{low.length === 1 ? "" : "s"}
            </button>
            {showLow && <ul className="flex flex-col gap-5 opacity-80">{low.map((m) => <TenderCard key={m.id} m={m} />)}</ul>}
          </div>
        )}
      </section>

      <section className="flex flex-col justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm md:flex-row md:items-center">
        <div className="flex items-center gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-amber-500/20 bg-amber-500/10 text-amber-600"><Icon name="shield" className="h-6 w-6" /></div>
          <div>
            <h2 className="text-base font-bold text-slate-900">Every verdict shows its clause</h2>
            <p className="mt-0.5 text-xs text-slate-600">
              Rules check turnover, experience, EMD, certifications, states and the deadline against the bid document. If a
              criterion can&apos;t be verified, the verdict is “keep proof ready”, never a false green.
            </p>
          </div>
        </div>
        <Link href={`/profiles/${s.profileId}/profile`} className="shrink-0 rounded-lg border border-slate-200 bg-slate-100 px-4 py-2 text-xs font-semibold text-slate-900 hover:bg-slate-200">
          Business profile
        </Link>
      </section>
    </div>
  );
}

function Metric({ label, value, note, tone }: { label: string; value: string; note: string; tone?: "ok" }) {
  return (
    <div className={`flex flex-col rounded-xl border p-4 ${tone === "ok" ? "border-emerald-200/70 bg-emerald-50/60" : "border-slate-200/70 bg-slate-50/80"}`}>
      <dt className={`text-[11px] font-semibold uppercase tracking-wider ${tone === "ok" ? "text-emerald-800" : "text-slate-500"}`}>{label}</dt>
      <dd className={`mt-1 font-heading text-xl font-bold ${tone === "ok" ? "text-emerald-700" : "text-slate-900"}`}>{value}</dd>
      <dd className="mt-0.5 truncate text-xs text-slate-500" title={note}>{note}</dd>
    </div>
  );
}

function TenderCard({ m }: { m: MatchSummary }) {
  const t = m.tender;
  const d = deadline(t.end_date);
  const reasons = m.reasons.filter((r) => r.kind !== "info").slice(0, 3);
  const quote = quotedReason(m.reasons);
  const portal = safeHref(t.source_url);
  return (
    <li>
      <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-shadow hover:border-slate-300 hover:shadow-md sm:p-6">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="rounded border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-xs font-semibold text-slate-700">{t.bid_no}</span>
              <span className="text-xs font-medium text-slate-500">{t.buyer || "Buyer not listed"} · {PORTAL_NAME[t.portal] ?? t.portal}</span>
            </div>
            <h3 className="break-words font-heading text-lg font-bold leading-snug text-slate-900 sm:text-xl">{t.title}</h3>
            <div className="mt-2.5 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-slate-600">
              <span className="flex items-center gap-1 text-sm font-bold text-slate-900"><Icon name="rupee" className="h-4 w-4 text-amber-600" />{t.est_value ? inr(t.est_value) : "Value not listed"}</span>
              <span className={`flex items-center gap-1 ${d.closed ? "text-rose-700" : d.urgent ? "font-semibold text-amber-700" : ""}`}>
                <Icon name="clock" className="h-4 w-4 text-slate-400" />{d.text} ({istDate(t.end_date)})
              </span>
            </div>
          </div>
          <div className="flex shrink-0 items-center justify-between gap-2 lg:flex-col lg:items-end">
            <VerdictChip verdict={m.verdict} reasons={m.reasons} />
            {m.fit_score != null && <span className="font-mono text-xs font-semibold text-slate-500" title="Product fit">{Math.round(m.fit_score * 100)}% product fit</span>}
          </div>
        </div>

        <div className="mt-5 flex flex-col gap-3 rounded-xl border border-slate-200/80 bg-slate-50 p-4">
          <p className="text-xs font-bold text-slate-900">{WHY[m.verdict]}</p>
          <ul className="flex flex-col gap-1.5">
            {reasons.length ? reasons.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-xs leading-relaxed text-slate-700">
                <Icon name={REASON_ICON[r.kind].name} className={`mt-0.5 h-4 w-4 ${REASON_ICON[r.kind].cls}`} />{r.text}
              </li>
            )) : <li className="text-xs text-slate-500">No criteria read yet.</li>}
          </ul>
          {quote?.source_clause && (
            <blockquote className="flex items-start gap-2.5 rounded-lg border border-amber-200/80 bg-yellow-100/70 p-3 text-amber-950">
              <Icon name="quote" className="mt-0.5 h-4 w-4 text-amber-700" />
              <div className="flex min-w-0 flex-col">
                <span className="font-mono text-[11px] font-bold text-amber-800">From the bid document</span>
                <p className="mt-0.5 break-words text-xs font-medium italic">“{quote.source_clause}”</p>
              </div>
            </blockquote>
          )}
          {m.missing_docs.length > 0 && (
            <p className="flex items-center gap-1.5 text-xs text-slate-600">
              <Icon name="doc" className="h-4 w-4 text-amber-600" />
              {m.missing_docs.length} document{m.missing_docs.length === 1 ? "" : "s"} to keep ready
            </p>
          )}
        </div>

        <div className="mt-4 flex flex-col justify-between gap-3 border-t border-slate-100 pt-3 sm:flex-row sm:items-center">
          <span className="flex items-center gap-1.5 text-xs text-slate-500">
            <Icon name="chat" className={`h-4 w-4 ${m.alerted_at ? "text-emerald-600" : "text-slate-400"}`} />
            {m.alerted_at ? `WhatsApp alert sent ${istDate(m.alerted_at)}` : "No alert sent yet"}
          </span>
          <div className="flex flex-wrap items-center gap-2">
            {portal && (
              <a href={portal} target="_blank" rel="noopener noreferrer"
                 className="flex items-center gap-1 rounded-lg bg-slate-100 px-3.5 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-200">
                Open on {PORTAL_NAME[t.portal] ?? "portal"} <Icon name="out" className="h-3.5 w-3.5" />
              </a>
            )}
            <Link href={`/matches/${m.id}`} className="flex items-center gap-1 rounded-lg bg-navy px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-slate-800">
              Verdict &amp; clause <span aria-hidden>→</span>
            </Link>
          </div>
        </div>
      </article>
    </li>
  );
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
      <p className="font-heading font-bold text-slate-900">{title}</p>
      <p className="mt-1 text-sm text-slate-500">{body}</p>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="flex flex-col gap-5" aria-busy="true" aria-label="Loading matches">
      {[0, 1].map((i) => <div key={i} className="h-44 animate-pulse rounded-2xl border border-slate-200 bg-white" />)}
    </div>
  );
}
