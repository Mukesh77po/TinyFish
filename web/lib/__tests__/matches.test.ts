import { describe, expect, it } from "vitest";
import { byVerdict, isMse, portalSummary, quotedReason, readyCount, verdictCounts } from "../matches";
import type { MatchSummary, Reason, Verdict } from "../types";

const m = (id: number, verdict: Verdict, portal = "gem", relevant = true): MatchSummary => ({
  id, profile_id: 1, verdict, fit_score: 0.5, relevant, reasons: [], missing_docs: [], alerted_at: null,
  tender: { id, portal, bid_no: `B${id}`, title: "Rack", item: null, buyer: null, quantity: null, est_value: null,
            end_date: "2026-11-01T15:00:00+05:30", source_url: "https://x", doc_url: null },
});

describe("match helpers", () => {
  const ms = [m(1, "ELIGIBLE"), m(2, "ELIGIBLE", "cppp", false), m(3, "CHECK_DOCS", "cppp"), m(4, "NOT_ELIGIBLE")];

  it("counts what the nav calls ready: relevant and eligible only", () => {
    expect(readyCount(ms)).toBe(1);
    expect(verdictCounts(ms)).toEqual({ ELIGIBLE: 2, CHECK_DOCS: 1, NOT_ELIGIBLE: 1 });
    expect(byVerdict(ms, "CHECK_DOCS").map((x) => x.id)).toEqual([3]);
    expect(byVerdict(ms, "all")).toHaveLength(4);
    expect(portalSummary(ms)).toBe("GeM (2), CPPP (2)");
  });

  it("recognises MSE profiles by Udyam / MSE / MSME", () => {
    expect(isMse({ certifications: ["GeM Seller", "Udyam"] })).toBe(true);
    expect(isMse({ certifications: ["MSE"] })).toBe(true);
    expect(isMse({ certifications: ["ISO 9001", "Startup India"] })).toBe(false);
  });

  it("quotes the most decisive reason that has a clause", () => {
    const r = (kind: Reason["kind"], clause: string | null): Reason => ({ kind, criterion: "x", text: kind, source_clause: clause });
    expect(quotedReason([r("ok", "a"), r("warn", "b"), r("fail", null)])?.source_clause).toBe("b");
    expect(quotedReason([r("ok", "a"), r("fail", "c")])?.source_clause).toBe("c");
    expect(quotedReason([r("info", "d")])).toBeNull();
  });
});
