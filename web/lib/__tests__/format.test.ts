import { describe, expect, it } from "vitest";
import { deadline, inr, parseRupees, safeHref, splitExcerpt, splitList } from "../format";

describe("inr", () => {
  it("matches the backend's formatting", () => {
    expect([inr(4_000_000), inr(12_000_000), inr(37_000), inr(1_850_000), inr(null)])
      .toEqual(["₹40 L", "₹1.2 Cr", "₹37,000", "₹18.5 L", "—"]);
  });
});

describe("deadline", () => {
  const now = new Date("2026-10-24T12:00:00+05:30");
  it("counts down and flags urgency", () => {
    expect(deadline("2026-10-28T12:00:00+05:30", now)).toEqual({ text: "closes in 4 days", closed: false, urgent: false });
    expect(deadline("2026-10-24T17:00:00+05:30", now)).toEqual({ text: "closes in 5 h", closed: false, urgent: true });
    expect(deadline("2026-10-24T12:30:00+05:30", now).text).toBe("closes in 30 min");
  });
  it("reports closed tenders", () => {
    expect(deadline("2026-10-22T12:00:00+05:30", now)).toEqual({ text: "closed 2 days ago", closed: true, urgent: false });
    expect(deadline("2026-10-24T09:00:00+05:30", now).text).toBe("closed 3 h ago");
  });
});

describe("splitExcerpt", () => {
  it("splits around the highlight and clamps bad offsets", () => {
    const ex = { text: "abc CLAUSE xyz", highlight_start: 4, highlight_end: 10, prefix_truncated: false, suffix_truncated: false };
    expect(splitExcerpt(ex)).toEqual(["abc ", "CLAUSE", " xyz"]);
    expect(splitExcerpt({ ...ex, highlight_start: 50, highlight_end: 99 })).toEqual(["abc CLAUSE xyz", "", ""]);
  });
});

describe("safeHref", () => {
  it("only allows http(s)", () => {
    expect(safeHref("https://gem.gov.in")).toBe("https://gem.gov.in");
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
    expect(safeHref(null)).toBeUndefined();
  });
});

describe("form parsing", () => {
  it("splits lists and parses rupee amounts", () => {
    expect(splitList(" steel rack, , almirah ")).toEqual(["steel rack", "almirah"]);
    expect([parseRupees("1.2 Cr"), parseRupees("40 lakh"), parseRupees("₹12,00,000"), parseRupees("abc")])
      .toEqual([12_000_000, 4_000_000, 1_200_000, null]);
  });
});

import { EMPTY, toProfileInput } from "../profileForm";

describe("toProfileInput", () => {
  const ok = { ...EMPTY, name: " Ramesh ", products: "steel racks, almirah", turnover: "1.2 Cr", years: "8",
               certs: ["Udyam"], otherCerts: "BIS", states: "Haryana, Delhi" };
  it("builds the API body", () => {
    expect(toProfileInput(ok).input).toEqual({
      name: "Ramesh", phone: null, email: null, products: ["steel racks", "almirah"], keywords: [], hsn_codes: [],
      annual_turnover: 12_000_000, years_in_business: 8, certifications: ["Udyam", "BIS"], states_served: ["Haryana", "Delhi"],
    });
  });
  it("rejects bad input with a readable message", () => {
    expect(toProfileInput({ ...ok, name: "" }).error).toMatch(/name/);
    expect(toProfileInput({ ...ok, turnover: "lots" }).error).toMatch(/Turnover/);
    expect(toProfileInput({ ...ok, years: "2.5" }).error).toMatch(/whole number/);
    expect(toProfileInput({ ...ok, products: "", keywords: "" }).error).toMatch(/product/);
  });
});

import { compactExcerpt } from "../format";

describe("compactExcerpt", () => {
  it("collapses whitespace and trims context at word boundaries", () => {
    const before = "word ".repeat(60);
    const ex = { text: `${before}Minimum Average\nAnnual Turnover\n40 Lakh (s)\n${"tail ".repeat(60)}`,
                 highlight_start: before.length, highlight_end: before.length + "Minimum Average\nAnnual Turnover\n40 Lakh (s)".length,
                 prefix_truncated: true, suffix_truncated: false };
    const out = compactExcerpt(ex, 20);
    expect(out.clause).toBe("Minimum Average Annual Turnover 40 Lakh (s)");
    expect(out.before.startsWith("…") && out.before.length <= 22).toBe(true);
    expect(out.after.endsWith("…") && !out.after.includes("\n")).toBe(true);
  });
  it("keeps short context untouched", () => {
    const ex = { text: "EMD Amount 100000", highlight_start: 0, highlight_end: 10, prefix_truncated: false, suffix_truncated: false };
    expect(compactExcerpt(ex)).toEqual({ before: "", clause: "EMD Amount", after: " 100000" });
  });
});

describe("verdictLabel", () => {
  it("speaks plainly and names the failing criterion", async () => {
    const { verdictLabel } = await import("../format");
    expect(verdictLabel("ELIGIBLE")).toBe("You can bid");
    expect(verdictLabel("CHECK_DOCS")).toBe("Keep proof ready");
    expect(verdictLabel("NOT_ELIGIBLE", [{ kind: "ok", criterion: "emd" }, { kind: "fail", criterion: "turnover" }])).toBe("Turnover short");
    expect(verdictLabel("NOT_ELIGIBLE", [{ kind: "fail", criterion: "deadline" }])).toBe("Deadline passed");
    expect(verdictLabel("NOT_ELIGIBLE", [{ kind: "fail", criterion: "states" }])).toBe("State not served");
    expect(verdictLabel("NOT_ELIGIBLE")).toBe("Can’t bid");
  });
});
