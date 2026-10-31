"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ErrorBox from "@/components/ErrorBox";
import MatchView from "@/components/MatchView";
import Logo from "@/components/ui/Logo";
import { api, ApiError } from "@/lib/api";
import type { MatchDetail } from "@/lib/types";
import ProfileShell from "./ProfileShell";

/** /matches/[id]: load the match, then show it inside its profile's shell (same tabs, same live sweep). */
export default function MatchRoute({ matchId }: { matchId: number }) {
  const [m, setM] = useState<MatchDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.match(matchId).then(
      (d) => { setM(d); setError(null); },
      (e) => setError(e instanceof ApiError && e.status === 404 ? `There is no match ${matchId}.`
        : e instanceof Error ? e.message : "Couldn’t load this match."),
    );
  }, [matchId]);
  useEffect(load, [load]);

  if (m) return <ProfileShell profileId={m.profile_id}><MatchView m={m} reload={load} /></ProfileShell>;
  return (
    <>
      <header className="border-b border-slate-800/80 bg-navy">
        <div className="mx-auto flex h-20 max-w-7xl items-center px-4 sm:px-6 lg:px-8"><Logo /></div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
        {error ? (
          <div className="flex flex-col gap-3">
            <ErrorBox message={error} onRetry={load} />
            <Link href="/start#open" className="text-sm font-semibold text-slate-700 underline">Open a profile</Link>
          </div>
        ) : <div className="h-64 animate-pulse rounded-2xl border border-slate-200 bg-white" aria-busy="true" aria-label="Loading match" />}
      </main>
    </>
  );
}
