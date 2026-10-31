"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { compactExcerpt, deadline, inr, istDate, provenanceLine, safeHref } from "@/lib/format";
import type { AlertResult, MatchDetail, Reason } from "@/lib/types";
import VerdictChip from "./VerdictChip";

const KIND: Record<Reason["kind"], { icon: string; label: string; cls: string }> = {
  fail: { icon: "✕", label: "Fails", cls: "border-bad/40 bg-bad-bg/40" },
  warn: { icon: "!", label: "Check", cls: "border-warn/40 bg-warn-bg/40" },
  ok: { icon: "✓", label: "Met", cls: "border-ok/30 bg-ok-bg/40" },
  info: { icon: "i", label: "Note", cls: "border-info/30 bg-info-bg/40" },
};

const CRITERIA: Record<string, string> = {
  min_turnover: "Minimum turnover", past_experience_years: "Past experience (years)", emd_amount: "EMD",
  emd_exemption_for_mse: "EMD exemption for MSEs", mse_relaxation_experience_turnover: "MSE relaxation",
  startup_relaxation_experience_turnover: "Startup relaxation", required_certifications: "Certifications",
  documents_required: "Documents required", states: "State restriction",
};

function showValue(key: string, v: unknown): string {
  if (v == null) return "Not stated";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "None";
  if (typeof v === "number" && (key === "min_turnover" || key === "emd_amount")) return inr(v);
  return String(v);
}

function ReasonCard({ r }: { r: Reason }) {
  const k = KIND[r.kind];
  const link = safeHref(r.source_url);
  return (
    <li className={`flex flex-col gap-2 rounded-xl border p-4 ${k.cls}`}>
      <p className="flex items-start gap-2 font-semibold">
        <span aria-hidden className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ink text-xs text-paper">{k.icon}</span>
        <span><span className="sr-only">{k.label}: </span>{r.text}
          {link && <> · <a href={link} target="_blank" rel="noopener noreferrer" className="underline">notice ↗</a></>}</span>
      </p>
      {r.excerpt ? (
        <blockquote className="rounded-lg border border-amber-200/80 bg-yellow-50 p-3 text-sm leading-relaxed text-slate-500">
          {(() => {
            const { before, clause, after } = compactExcerpt(r.excerpt);
            return <>{before}<mark className="font-semibold text-ink">{clause}</mark>{after}</>;
          })()}
          <span className="mt-1 block text-xs">From the bid document</span>
        </blockquote>
      ) : r.source_clause ? (
        <blockquote className="rounded-lg bg-white/80 p-3 text-sm italic text-slate-500">“{r.source_clause}”</blockquote>
      ) : null}
    </li>
  );
}

function AlertBox({ matchId, alertedAt, onSent }: { matchId: number; alertedAt: string | null; onSent: () => void }) {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<AlertResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const label = (s: string) => (s === "sent" ? "Sent" : s === "not_configured" ? "Not configured" : s.replace(/^failed: /, "Failed: "));
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-bold text-slate-900">Alert</h2>
        <button disabled={busy} onClick={async () => {
          setBusy(true); setErr(null);
          try {
            const r = await api.alert(matchId);
            setRes(r);
            if (r.sent) onSent();
          } catch (e) { setErr(e instanceof Error ? e.message : "Alert failed."); }
          setBusy(false);
        }} className="rounded-lg bg-[#00a884] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60">
          {busy ? "Sending…" : "Send WhatsApp / email alert"}
        </button>
      </div>
      {alertedAt && !res && <p className="text-sm text-ok">Last alert sent {istDate(alertedAt)}.</p>}
      {err && <p role="alert" className="text-sm text-bad">{err}</p>}
      {res && (
        <>
          <p className="text-sm">WhatsApp: <b>{label(res.channels.whatsapp)}</b> · Email: <b>{label(res.channels.email)}</b></p>
          <pre className="max-w-md whitespace-pre-wrap rounded-2xl rounded-tl-none bg-[#dcf8c6] p-3 font-sans text-sm text-ink shadow">{res.preview}</pre>
        </>
      )}
    </div>
  );
}

export default function MatchView({ m, reload }: { m: MatchDetail; reload: () => void }) {
  const [done, setDone] = useState<Set<number>>(new Set());
  const t = m.tender;
  const d = deadline(t.end_date);
  const source = safeHref(t.source_url);
  const doc = safeHref(t.doc_url);
  const order = { fail: 0, warn: 1, ok: 2, info: 3 } as const;
  const reasons = [...m.reasons].sort((a, b) => order[a.kind] - order[b.kind]);

  return (
    <div className="flex flex-col gap-6">
      <Link href={`/profiles/${m.profile_id}`} className="self-start text-sm font-semibold text-slate-600 underline">← Live matches</Link>

      <section className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <VerdictChip verdict={m.verdict} reasons={m.reasons} large />
          <span className="rounded border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs font-semibold uppercase text-slate-700">{t.portal}</span>
          <span className="font-mono text-sm text-slate-500">{t.bid_no}</span>
        </div>
        <h1 className="break-words text-2xl font-bold text-slate-900 sm:text-3xl">{t.title}</h1>
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div><dt className="text-slate-500">Buyer</dt><dd className="font-semibold">{t.buyer || "—"}</dd></div>
          <div><dt className="text-slate-500">Estimated value</dt><dd className="font-semibold">{inr(t.est_value)}</dd></div>
          <div><dt className="text-slate-500">Closes</dt>
            <dd className={`font-semibold ${d.closed ? "text-bad" : d.urgent ? "text-warn" : ""}`}>{istDate(t.end_date)} ({d.text})</dd></div>
          <div><dt className="text-slate-500">Quantity</dt><dd className="font-semibold">{t.quantity || "—"}</dd></div>
        </dl>
        <div className="flex flex-wrap gap-2">
          {source && <a href={source} target="_blank" rel="noopener noreferrer" className="rounded-lg bg-navy px-3.5 py-2 text-sm font-semibold text-white hover:bg-slate-800">Open on portal ↗</a>}
          {doc && doc !== source && <a href={doc} target="_blank" rel="noopener noreferrer" className="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50">Bid document ↗</a>}
        </div>
        {m.provenance && <p className="text-xs text-slate-500">{provenanceLine(m.provenance)}</p>}
      </section>

      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-bold text-slate-900">Why this verdict</h2>
          <ul className="flex flex-col gap-3">{reasons.map((r, i) => <ReasonCard key={i} r={r} />)}</ul>
        </section>

        <aside className="flex flex-col gap-4">
          <AlertBox matchId={m.id} alertedAt={m.alerted_at} onSent={reload} />
          <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="font-bold text-slate-900">Document checklist</h2>
            {m.missing_docs.length ? (
              <ul className="flex flex-col gap-1.5">
                {m.missing_docs.map((doc, i) => (
                  <li key={i}>
                    <label className="flex items-start gap-2 text-sm">
                      <input type="checkbox" className="mt-0.5" checked={done.has(i)}
                             onChange={() => { const n = new Set(done); if (n.has(i)) n.delete(i); else n.add(i); setDone(n); }} />
                      <span className={done.has(i) ? "text-slate-500 line-through" : ""}>{doc}</span>
                    </label>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-slate-500">Nothing extra listed.</p>}
          </div>
          {m.corrigenda.length > 0 && (
            <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="font-bold text-slate-900">Corrigenda</h2>
              <ul className="flex flex-col gap-2 text-sm">
                {m.corrigenda.map((c, i) => {
                  const href = safeHref(c.source_url);
                  return <li key={i}>{c.summary} {href && <a href={href} target="_blank" rel="noopener noreferrer" className="underline">source ↗</a>}</li>;
                })}
              </ul>
            </div>
          )}
        </aside>
      </div>

      {m.eligibility && (
        <details className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <summary className="cursor-pointer font-bold">Eligibility read from the bid document</summary>
          <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[32rem] text-left text-sm">
            <thead><tr className="text-slate-500"><th className="py-1 pr-4">Criterion</th><th className="py-1 pr-4">Value</th><th className="py-1">Source clause</th></tr></thead>
            <tbody>
              {Object.entries(m.eligibility).map(([k, c]) => (
                <tr key={k} className="border-t border-slate-200 align-top">
                  <td className="py-2 pr-4 font-semibold">{CRITERIA[k] || k}</td>
                  <td className="py-2 pr-4">{showValue(k, c?.value)}</td>
                  <td className="py-2 italic text-slate-500">{c?.source_clause ? `“${c.source_clause}”` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </details>
      )}
    </div>
  );
}
