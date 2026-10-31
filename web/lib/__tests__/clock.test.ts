import { afterEach, describe, expect, it } from "vitest";
import { now, syncFromServer } from "../clock";
import { deadline } from "../format";

describe("server clock", () => {
  afterEach(() => syncFromServer(null));

  it("countdowns follow the API's frozen demo clock, not the browser's", () => {
    // Fixture recorded on 20 Oct; the browser says 10 Nov. The bid must still read "closes in 3 days".
    syncFromServer("2026-10-20T12:00:00+05:30", new Date("2026-11-10T12:00:00+05:30").getTime());
    const d = deadline(new Date(now().getTime() + 3 * 864e5).toISOString());
    expect(d).toEqual({ text: "closes in 3 days", closed: false, urgent: false });
  });

  it("falls back to the browser clock without a usable server time", () => {
    syncFromServer("not a date");
    expect(Math.abs(now().getTime() - Date.now())).toBeLessThan(1000);
  });
});

describe("IST display", () => {
  it("shows portal times in IST whatever the browser's zone", async () => {
    const { istDate } = await import("../format");
    expect(istDate("2026-10-24T09:30:00Z").toLowerCase()).toContain("3:00");
    expect(istDate("2026-10-24T09:30:00Z")).toContain("24");
  });
});
