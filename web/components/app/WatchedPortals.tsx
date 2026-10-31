"use client";

import Icon, { type IconName } from "@/components/ui/Icon";
import { safeHref } from "@/lib/format";
import { isMse, readyCount } from "@/lib/matches";
import type { CardKey } from "@/lib/sweep";
import { STATUS, SweepStatus } from "./AgentStrip";
import { useShell } from "./ProfileShell";

const PORTALS: { key: CardKey; name: string; host: string; tag: string; icon: IconName; body: string }[] = [
  { key: "gem", name: "GeM", host: "bidplus.gem.gov.in", tag: "Bid listings", icon: "building",
    body: "Searches the GeM bid list for your keywords, sorts by closing date and reads up to three result pages. Each bid document is downloaded and its eligibility read." },
  { key: "cppp", name: "Central CPPP", host: "eprocure.gov.in", tag: "Latest active", icon: "building",
    body: "Reads the Latest Active Tenders list and keeps tenders whose titles match your products. CPPP only links documents through expiring sessions, so open those on the portal." },
  { key: "haryana", name: "Haryana e-Proc", host: "etenders.hry.nic.in", tag: "Home state", icon: "building",
    body: "Opens the latest tenders list. Searching it needs a captcha: the agent never solves one and hands you the portal link instead." },
  { key: "corrigenda", name: "Corrigenda", host: "TinyFish Search", tag: "Daily", icon: "doc",
    body: "Looks for corrigenda and deadline extensions on every open bid, in each sweep and once a day. Only a real notice near the bid number counts." },
];

/** Stitch "Watched Portals": one card per TinyFish agent, driven by the live sweep's events. */
export default function WatchedPortals() {
  const s = useShell();
  const p = s.profile;
  const bids = (["gem", "cppp", "haryana"] as const).reduce((n, k) => n + (s.sweep.cards[k].count ?? 0), 0);
  const keywords = p ? (p.keywords.length ? p.keywords : p.products) : [];
  const searched = s.fallback === false ? keywords.slice(0, 1) : keywords;

  return (
    <div className="flex flex-col gap-6">
      <section className="relative overflow-hidden rounded-2xl border border-slate-800 bg-navy p-6 text-white shadow-md sm:p-8">
        <div aria-hidden className="pointer-events-none absolute -right-16 -top-16 h-80 w-80 rounded-full bg-amber-500/10 blur-3xl" />
        <div className="relative flex flex-col justify-between gap-6 md:flex-row md:items-center">
          <div className="max-w-3xl space-y-2">
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-amber-400">
              <Icon name="radar" className="h-4 w-4" />TinyFish agents
              <span className="text-slate-600">•</span>
              <span className="font-mono normal-case tracking-normal text-slate-400">{s.fallback ? "replaying recorded runs" : "live runs (billed per step)"}</span>
            </p>
            <h1 className="text-2xl font-bold text-white sm:text-3xl lg:text-4xl">Watched Portals &amp; Crawler Agents</h1>
            <p className="text-sm leading-relaxed text-slate-300 sm:text-base">
              Agents open each portal like a person would, search for your products, read every bid document and check
              it against your profile. Read-only: they never submit a bid or solve a captcha.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-3 self-start rounded-xl border border-slate-800 bg-[#111C2E] px-4 py-3 shadow-lg md:self-center">
            <span className={`h-2.5 w-2.5 rounded-full ${s.running ? "animate-pulse bg-amber-400" : "bg-emerald-400"}`} aria-hidden />
            <div className="flex flex-col">
              <span className="text-[11px] font-medium text-slate-400">Agents</span>
              <span className="font-heading text-sm font-bold text-white">{s.running ? "Sweep running" : "Ready"}</span>
            </div>
            <button onClick={s.startSweep} disabled={!p || s.starting || (s.running && !s.lost)}
                    className="ml-2 rounded-lg bg-amber px-3 py-1.5 text-xs font-semibold text-slate-950 hover:bg-amber-hover disabled:opacity-60">
              {s.running ? "Sweeping…" : "Sweep now"}
            </button>
          </div>
        </div>
        <dl className="mt-6 grid grid-cols-2 gap-4 border-t border-slate-800/80 pt-6 sm:grid-cols-4">
          <Stat label="Bids found this sweep" value={String(bids)} />
          <Stat label="Relevant tenders" value={s.matches ? String(s.matches.filter((m) => m.relevant).length) : "…"} />
          <Stat label="Ready to bid" value={s.matches ? String(readyCount(s.matches)) : "…"} tone="amber" />
          <Stat label="MSE rules" value={p ? (isMse(p) ? "Applied" : "Not an MSE") : "…"} tone={p && isMse(p) ? "ok" : undefined} />
        </dl>
      </section>

      {s.lost && <p role="status" className="text-sm text-amber-700">Lost the live connection. Reconnecting…</p>}

      <section className="grid grid-cols-1 gap-6 md:grid-cols-2" aria-live="polite">
        {PORTALS.map((pt) => {
          const c = s.sweep.cards[pt.key];
          const st = STATUS[c.status];
          const href = safeHref(c.directUrl);
          return (
            <article key={pt.key} className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-navy text-amber-400 shadow-sm"><Icon name={pt.icon} className="h-5 w-5" /></div>
                    <div>
                      <h2 className="text-base font-bold text-slate-900">{pt.name}</h2>
                      <span className="text-xs text-slate-500">{pt.host}</span>
                    </div>
                  </div>
                  <span className={`inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-2.5 py-1 text-xs font-medium ${st.text}`}>
                    <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${st.dot}`} />{st.label}
                  </span>
                </div>
                <span className="inline-block rounded border border-amber-500/30 bg-amber-500/15 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-amber-800">{pt.tag}</span>
                <p className="text-sm leading-relaxed text-slate-600">{pt.body}</p>
                <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                  <div className="flex items-baseline gap-4 font-mono text-xs text-slate-600">
                    <span><b className="font-heading text-xl text-slate-900 tabular-nums">{c.steps}</b> steps</span>
                    {c.count != null && <span><b className="font-heading text-xl text-slate-900 tabular-nums">{c.count}</b> {pt.key === "corrigenda" ? "new" : "bids"}</span>}
                  </div>
                  <p className="mt-1.5 line-clamp-3 min-h-[3rem] text-xs text-slate-600">{c.message}</p>
                </div>
              </div>
              {c.status === "error" && href ? (
                <a href={href} target="_blank" rel="noopener noreferrer"
                   className="mt-5 inline-flex items-center justify-center gap-1 rounded-lg bg-navy px-3.5 py-2 text-xs font-semibold text-white hover:bg-slate-800">
                  Open on portal <Icon name="out" className="h-3.5 w-3.5" />
                </a>
              ) : <div className="mt-5 border-t border-slate-100 pt-3 text-[11px] text-slate-400">{c.status === "idle" ? "Waiting for a sweep" : "Updated live"}</div>}
            </article>
          );
        })}
      </section>
      <SweepStatus state={s.sweep} />

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-7">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-navy text-amber-400"><Icon name="tag" className="h-4 w-4" /></div>
            <h2 className="text-lg font-bold text-slate-900">What the agents search for</h2>
          </div>
          <p className="text-sm leading-relaxed text-slate-600">
            {s.fallback === false
              ? "Each live sweep searches every portal for your first keyword (each search is a billed agent run)."
              : "Replay mode searches every keyword in the recorded runs."}{" "}
            Product fit ranks the results by how many of your products and keywords a tender title mentions.
          </p>
          <TagRow label="Searched on the portals" tags={searched} strong />
          {p && <TagRow label="Products (used for product fit)" tags={p.products} />}
          {p && p.hsn_codes.length > 0 && <TagRow label="HSN codes" tags={p.hsn_codes} mono />}
        </div>
        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-navy text-amber-400"><Icon name="shield" className="h-4 w-4" /></div>
            <h2 className="text-lg font-bold text-slate-900">How a verdict is decided</h2>
          </div>
          <ul className="space-y-3">
            <Rule icon="x" tone="text-rose-600" title="Can’t bid" body="Turnover below the bid’s minimum, the tender limited to states you don’t serve, or the deadline has passed." />
            <Rule icon="warn" tone="text-amber-600" title="Keep proof ready" body="Past experience, a certification you haven’t listed, or a document that couldn’t be read." />
            <Rule icon="check" tone="text-emerald-600" title="MSE rules" body="With Udyam / MSE, turnover and experience are skipped when the bid allows MSE relaxation, and EMD when the MSE exemption applies." />
          </ul>
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "amber" | "ok" }) {
  return (
    <div>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className={`mt-1 font-heading text-xl font-bold ${tone === "amber" ? "text-amber-400" : tone === "ok" ? "text-emerald-400" : "text-white"}`}>{value}</dd>
    </div>
  );
}

function TagRow({ label, tags, strong, mono }: { label: string; tags: string[]; strong?: boolean; mono?: boolean }) {
  return (
    <div className="space-y-2">
      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
      <div className="flex flex-wrap gap-2">
        {tags.length ? tags.map((t) => (
          <span key={t} className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium ${strong ? "border-amber-200 bg-amber-50 text-amber-900" : "border-slate-200 bg-slate-50 text-slate-800"} ${mono ? "font-mono" : ""}`}>{t}</span>
        )) : <span className="text-xs text-slate-500">None set</span>}
      </div>
    </div>
  );
}

function Rule({ icon, tone, title, body }: { icon: IconName; tone: string; title: string; body: string }) {
  return (
    <li className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3.5">
      <Icon name={icon} className={`mt-0.5 h-5 w-5 ${tone}`} />
      <div>
        <p className="text-xs font-bold text-slate-900">{title}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-slate-600">{body}</p>
      </div>
    </li>
  );
}
