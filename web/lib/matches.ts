import type { MatchSummary, Profile, Reason, Verdict } from "./types";

export const PORTAL_NAME: Record<string, string> = { gem: "GeM", cppp: "CPPP", haryana: "Haryana e-Proc" };

export type VerdictFilter = "all" | Verdict;

/** Udyam / MSE registration: the matcher applies MSE relaxations and the EMD exemption for these profiles. */
export function isMse(p: Pick<Profile, "certifications">): boolean {
  return p.certifications.some((c) => /udyam|\bmse\b|msme/i.test(c));
}

/** "4 ready" in the nav: relevant matches the owner can bid on. */
export function readyCount(ms: MatchSummary[]): number {
  return ms.filter((m) => m.relevant && m.verdict === "ELIGIBLE").length;
}

export function verdictCounts(ms: MatchSummary[]): Record<Verdict, number> {
  const c: Record<Verdict, number> = { ELIGIBLE: 0, CHECK_DOCS: 0, NOT_ELIGIBLE: 0 };
  for (const m of ms) c[m.verdict] += 1;
  return c;
}

export function byVerdict(ms: MatchSummary[], f: VerdictFilter): MatchSummary[] {
  return f === "all" ? ms : ms.filter((m) => m.verdict === f);
}

/** The reason worth quoting on a card: the first failing, then needs-proof, then met criterion with a clause. */
export function quotedReason(reasons: Reason[]): Reason | null {
  for (const kind of ["fail", "warn", "ok"] as const) {
    const r = reasons.find((x) => x.kind === kind && x.source_clause);
    if (r) return r;
  }
  return null;
}

/** Portals with matches, e.g. "GeM (2), CPPP (1)". */
export function portalSummary(ms: MatchSummary[]): string {
  const n: Record<string, number> = {};
  for (const m of ms) n[m.tender.portal] = (n[m.tender.portal] || 0) + 1;
  return Object.entries(n).map(([p, k]) => `${PORTAL_NAME[p] ?? p} (${k})`).join(", ");
}
