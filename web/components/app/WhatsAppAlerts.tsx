"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import Icon, { type IconName } from "@/components/ui/Icon";
import VerdictChip from "@/components/VerdictChip";
import { api } from "@/lib/api";
import { istDate } from "@/lib/format";
import type { AlertResult, AlertStatus, MatchSummary, Verdict } from "@/lib/types";
import { useShell } from "./ProfileShell";

const ORDER: Record<Verdict, number> = { ELIGIBLE: 0, CHECK_DOCS: 1, NOT_ELIGIBLE: 2 };
const SHOWN = 4;

const channelLabel = (s: string) =>
  s === "sent" ? "Sent" : s === "not_configured" ? "Not set up" : s.replace(/^failed: /, "Failed: ");

/** Stitch "WhatsApp Tender Radar": the real alert text for this business's matches, and how it gets delivered. */
export default function WhatsAppAlerts() {
  const s = useShell();
  const [status, setStatus] = useState<AlertStatus | null>(null);
  const [statusError, setStatusError] = useState(false);
  useEffect(() => {
    api.alertStatus().then(setStatus, () => setStatusError(true));
  }, []);

  // The alerts worth showing: relevant matches, eligible first (those are the ones auto-alerted).
  const picks = useMemo(() => [...(s.matches ?? [])].filter((m) => m.relevant)
    .sort((a, b) => ORDER[a.verdict] - ORDER[b.verdict]).slice(0, SHOWN), [s.matches]);
  const p = s.profile;
  const initials = (p?.name ?? "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div className="space-y-1.5">
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <span className="h-2 w-2 rounded-full bg-amber-500" aria-hidden />Alerts
            <span className="text-slate-300">/</span>WhatsApp via Twilio sandbox, plus email
          </p>
          <h1 className="text-3xl font-bold text-slate-900 sm:text-4xl">WhatsApp Tender Radar</h1>
          <p className="max-w-2xl text-sm leading-relaxed text-slate-600 sm:text-base">
            One message per tender: the verdict in plain words, the reasons, the deadline, the documents to keep ready
            and the portal link. These previews are the exact text that gets sent.
          </p>
        </div>
        <div className="flex items-center gap-3.5 self-start rounded-xl border border-slate-200 bg-white p-3 px-4 shadow-sm md:self-auto">
          <div className="flex flex-col text-right">
            <span className="text-xs font-medium text-slate-500">After each sweep</span>
            <span className="font-heading text-lg font-bold text-slate-900">
              {status ? (status.auto_alert ? `Up to ${status.auto_alert_max} alerts` : "Auto-alert off") : "…"}
            </span>
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-100 text-amber-700"><Icon name="bolt" className="h-5 w-5" /></div>
        </div>
      </div>

      <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-12">
        <div className="flex flex-col gap-6 lg:col-span-5">
          <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center gap-3.5 border-b border-slate-100 pb-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-slate-800 bg-navy font-heading text-lg font-bold text-amber-400 shadow-sm">{initials || "—"}</div>
              <div className="min-w-0">
                <h2 className="truncate text-base font-bold text-slate-900">{p?.name ?? "…"}</h2>
                <p className="font-mono text-xs text-slate-500">{p?.phone || "no WhatsApp number in profile"}{p?.email ? ` • ${p.email}` : ""}</p>
              </div>
            </div>
            {statusError ? (
              <p className="mt-4 text-sm text-rose-700">Couldn’t read the alert setup from the API.</p>
            ) : (
              <ul className="mt-4 flex flex-col gap-3">
                <Channel icon="chat" name="WhatsApp" ready={status?.whatsapp} detail={status?.whatsapp
                  ? `Twilio sandbox → ${status.whatsapp_to ?? p?.phone ?? "profile number"}`
                  : "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM"} />
                <Channel icon="send" name="Email" ready={status?.email} detail={status?.email
                  ? `SMTP → ${status.email_to ?? p?.email ?? "profile email"}` : "Set SMTP_URL (optional)"} />
              </ul>
            )}
          </section>

          <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="border-b border-slate-100 pb-2 text-base font-bold text-slate-900">How alerts are delivered</h2>
            <Rule icon="bolt" title="After every sweep" body={`New tenders you can bid on (relevant, still open, not alerted before) are sent automatically${status ? `, at most ${status.auto_alert_max} per sweep` : ""}.`} />
            <Rule icon="chat" title="On demand" body="“Send now” here or on any match sends that tender immediately, whatever its verdict." />
            <Rule icon="doc" title="Deadline changes" body="Corrigenda and extensions found by the corrigenda agent appear as notes on the match and in its next alert." />
            <Rule icon="warn" title="Sandbox rule" body="The phone must have sent the sandbox join message in the last 24 h, or Twilio accepts the message but never delivers it." />
          </section>
        </div>

        <div className="flex flex-col lg:col-span-7">
          <div className="flex w-full flex-col overflow-hidden rounded-2xl border border-slate-800 bg-navy text-slate-100 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 bg-[#111C2E] px-5 py-3.5">
              <div className="flex items-center gap-3">
                <div className="relative flex h-10 w-10 items-center justify-center rounded-full border border-slate-700 bg-[#18263D] text-amber-400"><Icon name="radar" className="h-5 w-5" /></div>
                <div className="flex flex-col">
                  <span className="font-heading text-sm font-bold text-white sm:text-base">TenderHawk</span>
                  <span className="text-xs text-slate-400">WhatsApp preview · {p?.name ?? "…"}</span>
                </div>
              </div>
            </div>
            <div className="max-h-[760px] space-y-4 overflow-y-auto bg-[#080E1A] p-5">
              {!s.matches ? (
                <div className="h-40 animate-pulse rounded-2xl bg-[#111C2E]" aria-busy="true" aria-label="Loading alerts" />
              ) : picks.length ? picks.map((m) => <AlertBubble key={m.id} m={m} onSent={s.loadMatches} />) : (
                <div className="rounded-2xl rounded-tl-none border border-slate-800 bg-[#111C2E] p-4 text-sm text-slate-300">
                  No tenders to alert about yet. Run a sweep from <Link href={`/profiles/${s.profileId}`} className="font-semibold text-amber-400 underline">Live Matches</Link>.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AlertBubble({ m, onSent }: { m: MatchSummary; onSent: () => void }) {
  const [preview, setPreview] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<AlertResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.alertPreview(m.id).then((r) => setPreview(r.preview), () => setFailed(true));
  }, [m.id]);

  async function send() {
    setBusy(true); setErr(null);
    try {
      const r = await api.alert(m.id);
      setRes(r);
      if (r.sent) onSent();
    } catch (e) { setErr(e instanceof Error ? e.message : "Sending failed."); }
    setBusy(false);
  }

  return (
    <article className="flex max-w-xl flex-col items-start">
      <div className="w-full space-y-3 rounded-2xl rounded-tl-none border border-slate-800 bg-[#111C2E] p-4 text-slate-200 shadow-md">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2">
          <VerdictChip verdict={m.verdict} reasons={m.reasons} />
          <span className="font-mono text-xs text-slate-400">{m.alerted_at ? `sent ${istDate(m.alerted_at)}` : "not sent yet"}</span>
        </div>
        {failed ? <p className="text-xs text-rose-300">Couldn’t build the preview for this tender.</p>
          : preview == null ? <div className="h-24 animate-pulse rounded-lg bg-[#18263D]" aria-busy="true" />
          : <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-slate-100">{preview}</pre>}
        {err && <p role="alert" className="text-xs text-rose-300">{err}</p>}
        {res && (
          <p className="text-xs text-slate-300">
            WhatsApp: <b className="text-white">{channelLabel(res.channels.whatsapp)}</b> · Email: <b className="text-white">{channelLabel(res.channels.email)}</b>
          </p>
        )}
        <div className="flex items-center justify-between gap-2 border-t border-slate-800 pt-2">
          <Link href={`/matches/${m.id}`} className="text-xs font-semibold text-amber-400 underline">Verdict &amp; clause</Link>
          <button onClick={send} disabled={busy || !preview}
                  className="flex items-center gap-1.5 rounded-lg bg-[#00a884] px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-60">
            <Icon name="send" className="h-3.5 w-3.5" />{busy ? "Sending…" : m.alerted_at ? "Send again" : "Send now"}
          </button>
        </div>
      </div>
    </article>
  );
}

function Channel({ icon, name, ready, detail }: { icon: IconName; name: string; ready?: boolean; detail: string }) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-slate-200/80 bg-slate-50 p-3.5">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-navy text-amber-400"><Icon name={icon} className="h-4 w-4" /></div>
        <div className="min-w-0">
          <p className="text-xs font-semibold text-slate-900">{name}</p>
          <p className="truncate text-[11px] text-slate-500" title={detail}>{detail}</p>
        </div>
      </div>
      <span className={`shrink-0 rounded border px-2 py-0.5 font-mono text-[11px] font-semibold ${ready == null ? "border-slate-200 text-slate-400"
        : ready ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
        {ready == null ? "…" : ready ? "READY" : "NOT SET UP"}
      </span>
    </li>
  );
}

function Rule({ icon, title, body }: { icon: IconName; title: string; body: string }) {
  return (
    <div className="flex items-start gap-3.5 rounded-lg border border-slate-200/70 bg-slate-50 p-3.5">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-amber-600"><Icon name={icon} className="h-4 w-4" /></div>
      <div>
        <p className="text-xs font-bold text-slate-900">{title}</p>
        <p className="mt-1 text-xs leading-relaxed text-slate-600">{body}</p>
      </div>
    </div>
  );
}
