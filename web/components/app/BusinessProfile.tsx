"use client";

import Link from "next/link";
import Icon, { type IconName } from "@/components/ui/Icon";
import { inr, verdictLabel } from "@/lib/format";
import { isMse } from "@/lib/matches";
import type { MatchSummary, Reason } from "@/lib/types";
import { useShell } from "./ProfileShell";

/** What each certification changes in the matcher (api/matcher.py), in plain words. */
function certEffect(c: string): string {
  if (/udyam|\bmse\b|msme/i.test(c)) return "MSE relaxations: turnover and experience are skipped when the bid allows it, and EMD when the MSE exemption applies.";
  if (/startup/i.test(c)) return "Shown to buyers; checked when a bid asks for it.";
  if (/gem/i.test(c)) return "Needed to bid on GeM.";
  return "Matched against the certifications a bid requires.";
}

const REASON_ICON: Record<Reason["kind"], { name: IconName; cls: string }> = {
  ok: { name: "check", cls: "text-emerald-600" }, warn: { name: "warn", cls: "text-amber-600" },
  fail: { name: "x", cls: "text-rose-600" }, info: { name: "info", cls: "text-blue-600" },
};

/** Stitch "Business Profile & MSME Intelligence", filled only with what the profile actually holds. */
export default function BusinessProfile() {
  const s = useShell();
  const p = s.profile;
  if (!p) return <div className="h-96 animate-pulse rounded-2xl border border-slate-200 bg-white" aria-busy="true" aria-label="Loading profile" />;
  const latest = pickLatest(s.matches ?? []);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div className="flex flex-col gap-1">
          <span className="self-start rounded-full border border-amber-200/80 bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-900">
            Profile #{p.id}
          </span>
          <h1 className="mt-1 text-2xl font-bold text-slate-900 sm:text-3xl">Business Profile &amp; MSME Intelligence</h1>
          <p className="max-w-2xl text-sm leading-relaxed text-slate-600">
            Every bid document is read against these facts. Turnover, experience, EMD, certifications and states are
            checked automatically, and each verdict quotes the clause it came from.
          </p>
        </div>
        <Link href="/start" className="self-start rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 md:self-auto">
          Create another profile
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="flex flex-col gap-6 lg:col-span-8">
          <section className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-7">
            <div aria-hidden className="pointer-events-none absolute right-0 top-0 -mr-20 -mt-20 h-72 w-72 rounded-full bg-amber-500/5 blur-3xl" />
            <div className="relative flex flex-col gap-5">
              {isMse(p) && (
                <span className="inline-flex items-center gap-2 self-start rounded-full border border-emerald-200/80 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">
                  <Icon name="shield" className="h-4 w-4 text-emerald-600" />Udyam / MSE (as declared in your profile)
                </span>
              )}
              <div>
                <h2 className="text-2xl font-bold text-slate-900 sm:text-3xl">{p.name}</h2>
                <p className="mt-1 text-sm text-slate-600">{p.certifications.join(" · ") || "No certifications listed"}</p>
              </div>
              <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Fact icon="rupee" label="Annual turnover" value={inr(p.annual_turnover)} note="compared with each bid’s minimum" />
                <Fact icon="clock" label="Years in business" value={p.years_in_business != null ? `${p.years_in_business} years` : "—"} note="past supply still needs proof" />
                <Fact icon="building" label="States served" value={p.states_served.length ? String(p.states_served.length) : "—"} note={p.states_served.join(", ") || "add states to check restrictions"} />
              </dl>
              {(p.phone || p.email) && (
                <div className="flex flex-wrap gap-2">
                  {p.phone && <span className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700"><Icon name="chat" className="h-4 w-4 text-amber-600" />{p.phone}</span>}
                  {p.email && <span className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700"><Icon name="send" className="h-4 w-4 text-amber-600" />{p.email}</span>}
                </div>
              )}
            </div>
          </section>

          <section className="flex flex-col gap-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-7">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Capabilities &amp; catalogue matching</h2>
              <p className="text-xs text-slate-500 sm:text-sm">Tender titles are ranked against these products; the agents search the portals for the keywords.</p>
            </div>
            <Tags label="Products" tags={p.products} />
            <Tags label="Portal search keywords" tags={p.keywords} amber />
            {p.hsn_codes.length > 0 && <Tags label="HSN codes" tags={p.hsn_codes} mono />}
          </section>

          <section className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-7">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Certifications &amp; what they change</h2>
              <p className="text-xs text-slate-500 sm:text-sm">As declared in this profile. Keep the certificates ready: buyers ask for them with the bid.</p>
            </div>
            {p.certifications.length ? (
              <ul className="flex flex-col gap-3">
                {p.certifications.map((c) => (
                  <li key={c} className="flex items-start gap-3 rounded-xl border border-slate-200/80 bg-slate-50 p-4">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-navy text-white"><Icon name="doc" className="h-5 w-5" /></div>
                    <div>
                      <p className="text-sm font-bold text-slate-900">{c}</p>
                      <p className="mt-0.5 text-xs leading-relaxed text-slate-600">{certEffect(c)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-slate-500">No certifications listed. Bids that require one will show “keep proof ready”.</p>}
          </section>
        </div>

        <div className="flex flex-col gap-6 lg:col-span-4">
          <section className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-navy text-white"><Icon name="shield" className="h-5 w-5" /></div>
              <div>
                <h2 className="text-base font-bold text-slate-900">Checked on every bid</h2>
                <span className="text-xs text-slate-500">From this profile, against the bid document</span>
              </div>
            </div>
            <ul className="flex flex-col gap-2.5">
              <Check ok title="Minimum turnover" body={`Your ${inr(p.annual_turnover)} against the bid’s average annual turnover clause.`} />
              <Check title="Past experience" body="Always “keep proof ready”: years in business aren’t the same as years of past supply." />
              <Check ok title="EMD" body={isMse(p) ? "Waived when the bid grants the MSE EMD exemption." : "Shown with the amount; no MSE exemption on this profile."} />
              <Check ok title="States" body={p.states_served.length ? `A tender limited to other states is “can’t bid”.` : "Add the states you serve to catch state-only tenders."} />
            </ul>
          </section>

          <section className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-base font-bold text-slate-900">Latest verdict</h2>
            {latest ? (
              <>
                <p className="text-xs leading-relaxed text-slate-600 sm:text-sm">
                  How TenderHawk read <b className="font-semibold text-slate-900">{latest.tender.title}</b>
                  {latest.tender.buyer ? <> for {latest.tender.buyer}</> : null}.
                </p>
                <ul className="flex flex-col gap-2">
                  {latest.reasons.filter((r) => r.kind !== "info").slice(0, 4).map((r, i) => (
                    <li key={i} className="flex items-start gap-2.5 rounded-xl border border-slate-200/80 bg-slate-50 p-3 text-xs text-slate-700">
                      <Icon name={REASON_ICON[r.kind].name} className={`mt-0.5 h-4 w-4 ${REASON_ICON[r.kind].cls}`} />{r.text}
                    </li>
                  ))}
                </ul>
                <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-800 bg-navy p-4 text-white">
                  <div>
                    <p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-400">TenderHawk verdict</p>
                    <p className="font-heading text-sm font-bold text-amber-400 sm:text-base">{verdictLabel(latest.verdict, latest.reasons)}</p>
                  </div>
                  <Link href={`/matches/${latest.id}`} className="rounded-lg bg-amber px-3.5 py-1.5 text-xs font-semibold text-slate-950 hover:bg-amber-hover">Review</Link>
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-500">No verdicts yet. Run a sweep from Live Matches.</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

/** The verdict worth showing off: a relevant eligible match, else any relevant one. */
function pickLatest(ms: MatchSummary[]): MatchSummary | null {
  const rel = ms.filter((m) => m.relevant);
  return rel.find((m) => m.verdict === "ELIGIBLE") ?? rel[0] ?? null;
}

function Fact({ icon, label, value, note }: { icon: IconName; label: string; value: string; note: string }) {
  return (
    <div className="flex flex-col justify-between rounded-xl border border-slate-200/80 bg-slate-50/80 p-4">
      <dt className="flex items-center justify-between text-xs font-medium text-slate-500">{label}<Icon name={icon} className="h-4 w-4 text-navy" /></dt>
      <dd className="mt-3 font-heading text-xl font-bold text-slate-900">{value}</dd>
      <dd className="mt-0.5 truncate text-xs text-slate-500" title={note}>{note}</dd>
    </div>
  );
}

function Tags({ label, tags, amber, mono }: { label: string; tags: string[]; amber?: boolean; mono?: boolean }) {
  return (
    <div className="space-y-2">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</p>
      <div className="flex flex-wrap gap-2">
        {tags.length ? tags.map((t) => (
          <span key={t} className={`rounded-lg border px-3 py-1.5 text-xs font-medium sm:text-sm ${amber ? "border-amber-200 bg-amber-50 text-amber-900" : "border-slate-200 bg-slate-100 text-slate-800"} ${mono ? "font-mono" : ""}`}>{t}</span>
        )) : <span className="text-xs text-slate-500">None set</span>}
      </div>
    </div>
  );
}

function Check({ ok, title, body }: { ok?: boolean; title: string; body: string }) {
  return (
    <li className="flex items-start gap-2.5 rounded-xl border border-slate-200/80 bg-slate-50 p-3">
      <Icon name={ok ? "check" : "warn"} className={`mt-0.5 h-4 w-4 ${ok ? "text-emerald-600" : "text-amber-600"}`} />
      <div>
        <p className="text-xs font-semibold text-slate-900">{title}</p>
        <p className="mt-0.5 text-xs text-slate-600">{body}</p>
      </div>
    </li>
  );
}

