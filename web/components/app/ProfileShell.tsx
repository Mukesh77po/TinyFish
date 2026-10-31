"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useReducer, useRef, useState } from "react";
import ErrorBox from "@/components/ErrorBox";
import HealthBanner from "@/components/HealthBanner";
import Icon from "@/components/ui/Icon";
import Logo from "@/components/ui/Logo";
import { api, ApiError, sweepEventsUrl } from "@/lib/api";
import { isMse, readyCount } from "@/lib/matches";
import { applyEvent, initialSweep, type SweepState } from "@/lib/sweep";
import type { MatchSummary, Profile, StepEvent } from "@/lib/types";

type Action = { type: "reset" } | { type: "event"; ev: StepEvent };
const reducer = (s: SweepState, a: Action): SweepState => (a.type === "reset" ? initialSweep() : applyEvent(s, a.ev));

const storeKey = (profileId: number) => `th:sweep:${profileId}`;
const remember = (k: string, v: string | null) => {
  try {
    if (v) sessionStorage.setItem(k, v); else sessionStorage.removeItem(k);
  } catch { /* private mode: the panel just won't resume after a reload */ }
};
const recall = (k: string) => {
  try { return sessionStorage.getItem(k); } catch { return null; }
};

export interface Shell {
  profileId: number;
  profile: Profile | null;
  matches: MatchSummary[] | null;
  matchError: string | null;
  loadMatches: () => void;
  sweep: SweepState;
  /** A sweep's stream is open and it hasn't reached all/done: the Sweep button stays disabled. */
  running: boolean;
  starting: boolean;
  lost: boolean;
  fallback: boolean | null;
  startSweep: () => void;
  follow: (sweepId: string) => void;
  stopWatching: () => void;
}

const ShellContext = createContext<Shell | null>(null);

export function useShell(): Shell {
  const s = useContext(ShellContext);
  if (!s) throw new Error("useShell outside ProfileShell");
  return s;
}

const TABS = [
  { href: "", label: "Live Matches" },
  { href: "/portals", label: "Watched Portals" },
  { href: "/profile", label: "Business Profile" },
  { href: "/alerts", label: "WhatsApp Alerts" },
] as const;

/** The signed-in app for one business profile (Stitch: Live Matches / Watched Portals / Business Profile /
 *  WhatsApp Alerts). Owns the profile, its matches and the one live sweep, so every tab shows the same run. */
export default function ProfileShell({ profileId, children }: { profileId: number; children: React.ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [matches, setMatches] = useState<MatchSummary[] | null>(null);
  const [matchError, setMatchError] = useState<string | null>(null);
  const [sweep, dispatch] = useReducer(reducer, undefined, initialSweep);
  const [starting, setStarting] = useState(false);
  const [lost, setLost] = useState(false);
  const [following, setFollowing] = useState(false);   // a sweep's stream is open (or being opened)
  const [fallback, setFallback] = useState<boolean | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const loadMatches = useCallback(() => {
    api.matches(profileId).then(
      (ms) => { setMatches(ms); setMatchError(null); },
      (e) => setMatchError(e instanceof ApiError ? e.message : "Couldn’t load matches."),
    );
  }, [profileId]);

  const loadProfile = useCallback(() => {
    api.profile(profileId).then(
      (p) => { setProfile(p); setProfileError(null); },
      (e) => setProfileError(e instanceof ApiError && e.status === 404
        ? `There is no profile ${profileId}.` : e instanceof Error ? e.message : "Couldn’t load the profile."),
    );
  }, [profileId]);

  useEffect(() => {
    loadProfile();
    loadMatches();
    api.health().then((h) => setFallback(h.fallback_mode), () => setFallback(null));
  }, [loadProfile, loadMatches]);

  /** Subscribe to a sweep's event stream. Only refs, storage and the EventSource here: state changes
   *  happen in its callbacks, so this is safe to call from an effect (resume) or a click (new sweep). */
  const follow = useCallback((id: string) => {
    esRef.current?.close();
    remember(storeKey(profileId), id);
    const es = new EventSource(sweepEventsUrl(id));
    esRef.current = es;
    es.onopen = () => setFollowing(true);
    es.onmessage = (msg) => {
      let ev: StepEvent;
      try { ev = JSON.parse(msg.data); } catch { return; }
      setLost(false);
      dispatch({ type: "event", ev });
      if (ev.agent !== "all") return;
      // all/done frees the Sweep button; with documents still pending the stream stays open for
      // all/update (a match changed: reload the list) until all/settled.
      const last = ev.type === "settled" || (ev.type === "done" && !ev.pending);
      if (ev.type === "done" || ev.type === "update" || last) loadMatches();
      if (ev.type === "done") setFollowing(false);
      if (last) {
        es.close();
        remember(storeKey(profileId), null);
      }
    };
    // EventSource reconnects by itself and the server replays the log; just tell the user meanwhile.
    es.onerror = () => {
      if (es.readyState !== EventSource.CLOSED) return setLost(true);
      setLost(false);
      setFollowing(false);
      remember(storeKey(profileId), null);   // e.g. the sweep's log expired (404): stop trying to resume it
    };
  }, [profileId, loadMatches]);

  // Resume a sweep that was running before a page reload or a tab change.
  useEffect(() => {
    const saved = recall(storeKey(profileId));
    if (saved) follow(saved);
    return () => esRef.current?.close();
  }, [profileId, follow]);

  const stopWatching = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    remember(storeKey(profileId), null);
    setFollowing(false);
    setLost(false);
    dispatch({ type: "event", ev: { sweep_id: "", agent: "all", type: "done", step: 0,
      message: "Stopped watching this sweep. Results it finishes will still appear under Live Matches.",
      count: null, direct_url: null, ts: "" } });
  }, [profileId]);

  const startSweep = useCallback(async () => {
    setStarting(true);
    try {
      const { sweep_id } = await api.startSweep(profileId);
      dispatch({ type: "reset" });
      setLost(false);
      setFollowing(true);   // keep the button disabled until the stream ends: no double-billed sweeps
      follow(sweep_id);
    } catch (e) {
      dispatch({ type: "reset" });
      dispatch({ type: "event", ev: { sweep_id: "", agent: "all", type: "error", step: 0,
        message: e instanceof Error ? e.message : "Couldn’t start the sweep.", count: null, direct_url: null, ts: "" } });
    } finally {
      setStarting(false);
    }
  }, [profileId, follow]);

  const running = following && !sweep.finished;
  const shell: Shell = { profileId, profile, matches, matchError, loadMatches, sweep, running, starting, lost,
                         fallback, startSweep, follow, stopWatching };

  return (
    <ShellContext.Provider value={shell}>
      <AppHeader shell={shell} />
      <HealthBanner />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
        {profileError ? (
          <div className="flex flex-col gap-3">
            <ErrorBox message={profileError} onRetry={loadProfile} />
            <Link href="/start" className="text-sm font-semibold text-slate-700 underline">Create a profile</Link>
          </div>
        ) : children}
      </main>
      <AppFooter />
    </ShellContext.Provider>
  );
}

function AppHeader({ shell }: { shell: Shell }) {
  const pathname = usePathname();
  const base = `/profiles/${shell.profileId}`;
  const active = (href: string) => (href === "" ? pathname === base || pathname.startsWith("/matches/")
                                                : pathname.startsWith(base + href));
  const ready = shell.matches ? readyCount(shell.matches) : null;
  const p = shell.profile;
  const busy = shell.starting || (shell.running && !shell.lost);

  const tab = (t: (typeof TABS)[number], mobile = false) => {
    const on = active(t.href);
    return (
      <Link key={t.href} href={base + t.href} aria-current={on ? "page" : undefined}
            className={`flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm transition-colors ${on
              ? "border border-slate-700/80 bg-navy-3 font-semibold text-white"
              : "font-medium text-slate-300 hover:bg-slate-800/60 hover:text-white"} ${mobile ? "py-1.5" : ""}`}>
        <span>{t.label}</span>
        {t.href === "" && ready != null && ready > 0 && (
          <span className="rounded-full bg-amber px-2 py-0.5 text-xs font-bold text-slate-950">{ready} ready</span>
        )}
        {t.href === "/portals" && shell.running && (
          <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" aria-label="sweep running" />
        )}
      </Link>
    );
  };

  return (
    <header className="sticky top-0 z-50 border-b border-slate-800/80 bg-navy/95 text-white backdrop-blur-md">
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <div className="flex shrink-0 items-center gap-6">
          <Logo href={`/profiles/${shell.profileId}`} />
          <nav aria-label="Dashboard" className="hidden items-center gap-1 lg:flex">{TABS.map((t) => tab(t))}</nav>
        </div>
        <div className="flex items-center justify-end gap-3">
          {p && (
            <div className="hidden items-center gap-2 whitespace-nowrap rounded-lg border border-slate-700/80 bg-navy-2 px-3 py-1.5 text-xs 2xl:flex">
              <span className="h-2 w-2 rounded-full bg-emerald-400" aria-hidden />
              <span className="max-w-[200px] truncate font-medium text-slate-200">
                {p.name}{p.states_served[0] ? ` · ${p.states_served[0]}` : ""}
              </span>
              {isMse(p) && <span className="rounded border border-amber-500/30 bg-amber-400/10 px-1.5 py-0.5 text-[11px] font-semibold text-amber-300">Udyam MSE</span>}
            </div>
          )}
          <button onClick={shell.startSweep} disabled={!p || busy}
                  className="flex items-center gap-1.5 whitespace-nowrap rounded-lg bg-amber px-3.5 py-2 text-sm font-semibold text-slate-950 shadow-sm hover:bg-amber-hover disabled:opacity-60">
            <Icon name="sync" className={`h-4 w-4 ${shell.running ? "animate-spin" : ""}`} />
            {shell.running ? "Sweeping…" : shell.starting ? "Starting…" : "Sweep now"}
          </button>
        </div>
      </div>
      <nav aria-label="Dashboard" className="flex gap-1.5 overflow-x-auto px-4 pb-3 lg:hidden">{TABS.map((t) => tab(t, true))}</nav>
    </header>
  );
}

function AppFooter() {
  return (
    <footer className="mt-auto border-t border-slate-800 bg-navy py-8 text-white">
      <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-4 px-4 sm:px-6 md:flex-row md:items-center lg:px-8">
        <div className="flex items-center gap-3">
          <Logo href="/" size="sm" />
          <span className="hidden border-l border-slate-700 pl-3 text-xs text-slate-400 sm:inline">MSME government tender radar</span>
        </div>
        <p className="text-xs text-slate-400">
          Agents: GeM, CPPP &amp; Haryana e-Proc via TinyFish · read-only, never submits bids, never bypasses captchas
        </p>
      </div>
    </footer>
  );
}
