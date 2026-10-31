import Link from "next/link";
import Logo from "@/components/ui/Logo";

/** Header for the public pages (landing, onboarding). The signed-in app has its own (components/app/AppHeader). */
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-slate-800/80 bg-navy/95 backdrop-blur-md">
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Logo />
        <nav aria-label="Sections" className="hidden items-center gap-9 text-sm font-medium text-slate-300 md:flex">
          <Link href="/#how-it-works" className="hover:text-white">How it works</Link>
          <Link href="/#shows-work" className="hover:text-white">Shows its work</Link>
          <Link href="/#pricing" className="hover:text-white">Pricing</Link>
        </nav>
        <div className="flex items-center gap-5">
          <Link href="/start#open" className="hidden text-sm font-medium text-slate-300 hover:text-white sm:inline">
            Open a profile
          </Link>
          <Link href="/start" className="rounded-lg bg-amber px-4 py-2.5 text-sm font-semibold text-slate-950 shadow-sm hover:bg-amber-hover">
            Get started free
          </Link>
        </div>
      </div>
    </header>
  );
}

export function SiteFooter({ cta = true }: { cta?: boolean }) {
  return (
    <footer className="mt-auto border-t border-slate-800 bg-navy pb-12 pt-16 text-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {cta && (
          <div className="flex flex-col items-start justify-between gap-6 border-b border-slate-800 pb-16 md:flex-row md:items-center">
            <h2 className="text-2xl font-bold text-white sm:text-3xl">Stop checking portals at night.</h2>
            <Link href="/start" className="shrink-0 rounded-lg bg-amber px-6 py-3 text-sm font-semibold text-slate-950 shadow-sm hover:bg-amber-hover">
              Create your free profile
            </Link>
          </div>
        )}
        <p className={`${cta ? "pt-8" : ""} max-w-4xl text-xs leading-relaxed text-slate-400`}>
          TenderHawk · built at HackIIITD 2026 by team L.C Hard, JIIT Noida · Read-only: never submits bids, never
          bypasses captchas · Sources: Ministry of Commerce &amp; Industry, GeM FY 2025–26 results; Public Procurement
          Policy for MSEs Order, 2012 (amended 2018).
        </p>
      </div>
    </footer>
  );
}
