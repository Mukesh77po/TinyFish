"use client";

import { useEffect, useState } from "react";
import { api, API_URL } from "@/lib/api";
import { istDate } from "@/lib/format";
import type { Health } from "@/lib/types";

/** Thin status strip: API unreachable / DB or Redis down / fallback (recorded) mode. */
export default function HealthBanner() {
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    let alive = true;
    const check = () =>
      api.health().then(
        (h) => { if (alive) { setHealth(h); setDown(false); } },
        () => { if (alive) setDown(true); },
      );
    check();
    const t = setInterval(check, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (down) {
    return (
      <div role="alert" className="bg-bad-bg text-bad text-sm">
        <div className="mx-auto max-w-6xl px-4 py-2">
          Can’t reach the TenderHawk API at <code>{API_URL}</code>. Start it with{" "}
          <code>uvicorn api.main:app</code>.
        </div>
      </div>
    );
  }
  if (!health) return null;
  const problems = [!health.db && "database", !health.redis && "Redis"].filter(Boolean);
  if (problems.length) {
    return (
      <div role="alert" className="bg-bad-bg text-bad text-sm">
        <div className="mx-auto max-w-6xl px-4 py-2">API is up, but {problems.join(" and ")} is down.</div>
      </div>
    );
  }
  if (health.fallback_mode) {
    return (
      <div role="status" className="bg-info-bg text-info text-sm">
        <div className="mx-auto max-w-6xl px-4 py-2">
          <b className="mr-2 rounded bg-info px-1.5 py-0.5 text-xs uppercase tracking-wide text-info-bg">Replay mode</b>
          Sweeps replay recorded TinyFish runs (no network, no credits)
          {health.clock && health.clock !== "real" && <> · deadlines as of {istDate(health.now)}</>}.
        </div>
      </div>
    );
  }
  return null;
}
