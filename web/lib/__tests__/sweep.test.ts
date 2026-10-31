import { describe, expect, it } from "vitest";
import { applyEvent, initialSweep } from "../sweep";
import type { StepEvent } from "../types";

const ev = (agent: StepEvent["agent"], type: StepEvent["type"], step = 0, message = "", extra: Partial<StepEvent> = {}): StepEvent =>
  ({ sweep_id: "s", agent, type, step, message, count: null, direct_url: null, ts: "", ...extra });

const LOG: StepEvent[] = [
  ev("gem", "started", 0, "Searching"),
  ev("corrigenda", "started", 0, "Waiting for bids"),
  ev("gem", "step", 1, "[storage rack] Navigate"),
  ev("cppp", "started", 0, "Searching"),
  ev("cppp", "error", 1, "Blocked: captcha", { direct_url: "https://eprocure.gov.in" }),
  ev("gem", "step", 2, "[storage rack] Extract"),
  ev("gem", "result", 2, "Found 7 bids", { count: 7 }),
  ev("corrigenda", "step", 1, "Checking 7 open bids"),
  ev("corrigenda", "result", 2, "Found 0 new corrigenda", { count: 0 }),
  ev("all", "step", 0, "Matching tenders against your profile"),
  ev("all", "done", 0, "7 tenders found. 1 eligible"),
];

describe("applyEvent", () => {
  it("drives each card and the pipeline line", () => {
    const s = LOG.reduce(applyEvent, initialSweep());
    expect(s.cards.gem).toMatchObject({ status: "done", steps: 2, count: 7 });
    expect(s.cards.cppp).toMatchObject({ status: "error", directUrl: "https://eprocure.gov.in" });
    expect(s.cards.haryana.status).toBe("idle");
    expect(s.cards.corrigenda).toMatchObject({ status: "done", count: 0 });
    expect(s).toMatchObject({ finished: true, summary: "7 tenders found. 1 eligible", pipeline: "" });
  });

  it("ends in the same state when a reconnect replays the whole log", () => {
    const once = LOG.reduce(applyEvent, initialSweep());
    const replayed = [...LOG.slice(0, 6), ...LOG].reduce(applyEvent, initialSweep());
    expect(replayed).toEqual(once);
  });

  it("ignores unknown agents and records sweep-level errors", () => {
    const s = applyEvent(applyEvent(initialSweep(), ev("nope" as StepEvent["agent"], "step", 1)), ev("all", "error", 0, "Sweep failed: x"));
    expect(s.error).toBe("Sweep failed: x");
    expect(s.cards.gem.status).toBe("idle");
  });
});

describe("a sweep that ends early", () => {
  it("turns still-running cards into errors instead of pulsing forever", () => {
    const s = [ev("gem", "started", 0, "Searching"), ev("gem", "step", 3, "x"),
               ev("all", "done", 0, "Lost contact with this sweep. Start a new one.")].reduce(applyEvent, initialSweep());
    expect(s.cards.gem).toMatchObject({ status: "error", steps: 3, message: "Ended without a result" });
    expect(s.finished).toBe(true);
  });
});

describe("documents read after the sweep is done", () => {
  it("finishes on done, shows background progress, and clears it on settled", () => {
    const base = LOG.slice(0, -1);
    const done = [...base, ev("all", "done", 0, "7 tenders found", { pending: 2 })].reduce(applyEvent, initialSweep());
    expect(done).toMatchObject({ finished: true, background: "Reading 2 new documents in the background" });

    const upd = applyEvent(done, ev("all", "update", 0, "Read eligibility for GEM/2026/B/8: ELIGIBLE", { tender_id: 8 }));
    expect(upd.background).toBe("Read eligibility for GEM/2026/B/8: ELIGIBLE");

    const settled = applyEvent(upd, ev("all", "settled", 0, "2 new documents read, 2 parsed"));
    expect(settled).toMatchObject({ background: null, summary: "7 tenders found. 2 new documents read, 2 parsed." });
    expect([...base, ev("all", "done", 0, "x", { pending: 0 })].reduce(applyEvent, initialSweep()).background).toBeNull();
  });
});
