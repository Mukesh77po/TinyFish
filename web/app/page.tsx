import Link from "next/link";
import { SiteFooter, SiteHeader } from "@/components/site/SiteChrome";

// Landing page, from the Stitch "TenderHawk - Home" screen. Pricing is pitch only: no billing behind it.

const STEPS = [
  ["Tell us your business", "Products, HSN codes, turnover, Udyam / Startup India / ISO, states you serve. Two minutes."],
  ["Agents sweep the portals", "TinyFish web agents search GeM, CPPP and Haryana e-procurement page by page, like a person would."],
  ["We read the bid document", "Turnover, experience, EMD and certification rules are pulled out and checked against your profile."],
  ["You get one WhatsApp", "Verdict, reasons, deadline and a document checklist. Deadline extensions arrive the same way."],
];

const PLANS = [
  { name: "Free", price: "₹0", per: "", blurb: "1 category · weekly digest", cta: "Start free", featured: false },
  { name: "Pro", price: "₹999", per: "/ month", blurb: "All categories · daily WhatsApp alerts · verdicts and checklists",
    cta: "Start 14-day trial", featured: true },
  { name: "Consultant", price: "₹4,999", per: "/ month", blurb: "25 client profiles · one sweep serves every client",
    cta: "Talk to us", featured: false },
];

export default function Landing() {
  return (
    <>
      <SiteHeader />
      <main>
        <section className="relative overflow-hidden border-b border-slate-800 bg-navy pb-20 pt-14 text-white lg:pb-28 lg:pt-20">
          <div className="mx-auto grid max-w-7xl grid-cols-1 items-center gap-12 px-4 sm:px-6 lg:grid-cols-12 lg:gap-8 lg:px-8">
            <div className="flex flex-col items-start lg:col-span-7 lg:pr-6">
              <span className="mb-6 rounded-full border border-slate-700/60 bg-navy-3 px-3 py-1 text-xs font-medium text-slate-300">
                For MSMEs on GeM, CPPP and state portals
              </span>
              <h1 className="mb-6 text-4xl font-bold leading-[1.08] text-white sm:text-5xl lg:text-[62px]">
                Every tender you can win, before your morning chai.
              </h1>
              <p className="mb-8 max-w-xl text-base leading-relaxed text-slate-300 sm:text-lg">
                AI agents watch government tender portals for your business, read every bid document, and tell you on
                WhatsApp which tenders you qualify for, and why.
              </p>
              <div className="mb-4 flex w-full flex-col gap-4 sm:w-auto sm:flex-row sm:items-center">
                <Link href="/start" className="inline-flex items-center justify-center gap-2 rounded-lg bg-amber px-6 py-3.5 text-base font-semibold text-slate-950 shadow-sm hover:bg-amber-hover">
                  Create your free profile <span aria-hidden>→</span>
                </Link>
                <Link href="#shows-work" className="inline-flex items-center justify-center rounded-lg border border-slate-700 bg-navy-2 px-6 py-3.5 text-base font-medium text-white hover:bg-slate-800">
                  See a sample alert
                </Link>
              </div>
              <p className="text-xs text-slate-400">Read-only · never submits bids · every verdict cites the bid clause</p>
            </div>

            <div className="relative flex flex-col gap-4 lg:col-span-5" aria-label="Example of what TenderHawk shows">
              <div className="rounded-xl border border-slate-800 bg-[#111C2E] p-5 shadow-2xl">
                <div className="mb-3.5 flex items-center justify-between border-b border-slate-800/80 pb-3.5">
                  <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-400">Agents sweeping · example</span>
                  <span className="text-[11px] text-slate-400">Powered by <span className="font-medium text-slate-300">TinyFish</span></span>
                </div>
                <ul className="space-y-3 text-xs">
                  <li className="flex items-center justify-between">
                    <span className="flex items-center gap-2.5 font-medium text-slate-200"><span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />GeM · bid listings</span>
                    <span className="rounded bg-[#24334D] px-2 py-0.5 font-mono text-[11px] font-medium text-amber-300">step 14</span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span className="flex items-center gap-2.5 font-medium text-slate-200"><span className="h-2 w-2 rounded-full bg-emerald-400" />CPPP · latest tenders</span>
                    <span className="font-mono text-xs font-semibold text-emerald-400">3 bids</span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span className="flex items-center gap-2.5 font-medium text-slate-200"><span className="h-2 w-2 rounded-full bg-rose-400" />Haryana e-proc</span>
                    <span className="font-mono text-xs font-semibold text-rose-300">captcha · open on portal</span>
                  </li>
                </ul>
              </div>
              <div className="rounded-xl border border-slate-200/90 bg-white p-5 text-slate-900 shadow-2xl lg:translate-x-2">
                <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-emerald-700">
                  <span>TenderHawk</span><span>·</span><span>WhatsApp</span><span>·</span><span className="text-slate-400">example</span>
                </div>
                <h2 className="text-base font-bold leading-snug text-slate-900">New match on GeM: steel storage racks</h2>
                <p className="mb-3.5 mt-1 text-xs font-medium text-slate-500">Ministry of Defence · ₹18.5 L · closes 28 Oct</p>
                <div className="space-y-2 border-t border-slate-100 pt-3 text-xs">
                  <p className="flex items-start gap-1.5 font-medium leading-relaxed text-emerald-700"><b aria-hidden>✓</b>You can bid: turnover met, MSE EMD exemption applies</p>
                  <p className="flex items-start gap-1.5 font-medium leading-relaxed text-amber-700"><b aria-hidden>!</b>Keep proof ready: 3 years of past-supply proof</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="border-b border-slate-200 bg-[#F8F9FA] py-12" aria-label="Market size">
          <div className="mx-auto grid max-w-7xl grid-cols-1 gap-8 px-4 sm:px-6 md:grid-cols-3 md:gap-12 lg:px-8">
            {[["₹5 lakh Cr", "procured through GeM in FY 2025–26"], ["11 lakh+", "micro and small enterprises on GeM"],
              ["25%", "of central procurement reserved for MSEs"]].map(([n, t]) => (
              <div key={n} className="flex flex-col">
                <span className="font-heading text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl lg:text-[42px]">{n}</span>
                <span className="mt-2 text-sm text-slate-600">{t}</span>
              </div>
            ))}
          </div>
        </section>

        <section id="how-it-works" className="scroll-mt-20 bg-white py-24">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-amber-700">How it works</p>
            <h2 className="mb-14 text-3xl font-bold text-slate-900 sm:text-4xl">Profile once. Agents do the hunting.</h2>
            <ol className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {STEPS.map(([title, body], i) => (
                <li key={title} className="rounded-xl border border-slate-200 bg-white p-6 hover:border-slate-300 hover:shadow-sm">
                  <span className="mb-4 block font-mono text-xs font-semibold text-slate-400">0{i + 1}</span>
                  <h3 className="mb-3 text-lg font-bold text-slate-900">{title}</h3>
                  <p className="text-sm leading-relaxed text-slate-600">{body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="shows-work" className="scroll-mt-20 border-y border-slate-200 bg-[#F8F9FA] py-24">
          <div className="mx-auto grid max-w-7xl grid-cols-1 items-center gap-12 px-4 sm:px-6 lg:grid-cols-12 lg:gap-14 lg:px-8">
            <div className="lg:col-span-6">
              <p className="mb-2 text-xs font-bold uppercase tracking-wider text-amber-700">Shows its work</p>
              <h2 className="mb-5 text-3xl font-bold leading-tight text-slate-900 sm:text-4xl">
                Not just “a tender exists”.<br />Whether you qualify, with proof.
              </h2>
              <p className="mb-6 text-base leading-relaxed text-slate-600">
                Every reason links to the exact clause in the bid document. If we can&apos;t verify something, we say
                “keep proof ready”, never a false green.
              </p>
              <Link href="/start" className="group inline-flex items-center text-sm font-semibold text-amber-700 hover:text-amber-800">
                Try it on your business <span aria-hidden className="ml-1 transition-transform group-hover:translate-x-1">→</span>
              </Link>
            </div>
            <div className="lg:col-span-6">
              <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
                <div className="mb-6 flex flex-wrap items-center gap-3">
                  <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800">You can bid</span>
                  <h3 className="text-base font-bold text-slate-900">Supply of steel storage racks</h3>
                  <span className="text-xs text-slate-400">example</span>
                </div>
                <div className="mb-6 space-y-2">
                  <p className="flex items-center gap-1.5 text-sm font-bold text-slate-900"><span className="text-emerald-600" aria-hidden>✓</span>Turnover met · ₹1.2 Cr yours ≥ ₹50 L</p>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-700">
                    Minimum Average Annual Turnover of the bidder (For 3 Years): <mark className="font-semibold">50 Lakh (s)</mark>
                  </div>
                </div>
                <div className="space-y-2">
                  <p className="flex items-center gap-1.5 text-sm font-bold text-slate-900"><span className="text-amber-600" aria-hidden>!</span>Keep proof ready · 3 years past supply</p>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-700">
                    Years of Past Experience Required for same/similar service: <mark className="font-semibold">3 Year (s)</mark>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="pricing" className="scroll-mt-20 bg-white py-24">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <div className="mx-auto mb-16 max-w-2xl text-center">
              <p className="mb-2 text-xs font-bold uppercase tracking-wider text-amber-700">Pricing</p>
              <h2 className="text-3xl font-bold text-slate-900 sm:text-4xl">Less than one day of a consultant.</h2>
            </div>
            <div className="mx-auto grid max-w-6xl grid-cols-1 items-stretch gap-8 lg:grid-cols-3">
              {PLANS.map((p) => (
                <div key={p.name} className={`flex flex-col justify-between rounded-2xl p-8 ${p.featured
                  ? "border border-slate-800 bg-navy text-white shadow-xl lg:-translate-y-2"
                  : "border border-slate-200 bg-white hover:border-slate-300"}`}>
                  <div>
                    <div className="mb-4 flex items-center justify-between">
                      <h3 className={`text-lg font-bold ${p.featured ? "text-white" : "text-slate-900"}`}>{p.name}</h3>
                      {p.featured && <span className="rounded-full bg-amber px-2.5 py-0.5 text-xs font-semibold text-slate-950">Most popular</span>}
                    </div>
                    <div className="mb-6 flex items-baseline gap-1">
                      <span className="font-heading text-4xl font-bold">{p.price}</span>
                      {p.per && <span className={`text-sm ${p.featured ? "text-slate-400" : "text-slate-500"}`}>{p.per}</span>}
                    </div>
                    <p className={`mb-8 border-b pb-6 text-sm leading-relaxed ${p.featured ? "border-slate-800 text-slate-300" : "border-slate-100 text-slate-600"}`}>{p.blurb}</p>
                  </div>
                  <Link href="/start" className={`w-full rounded-lg px-4 py-3 text-center text-sm font-semibold ${p.featured
                    ? "bg-amber text-slate-950 hover:bg-amber-hover" : "border border-slate-200 text-slate-800 hover:bg-slate-50"}`}>
                    {p.cta}
                  </Link>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
