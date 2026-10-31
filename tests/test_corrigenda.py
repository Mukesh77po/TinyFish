import asyncio
from datetime import datetime, timedelta

import pytest

from agents.schemas import IST, BidListing, Corrigendum
from api import corrigenda as corr
from api.matcher import ProfileFacts, evaluate

END = datetime(2026, 10, 28, 15, 0, tzinfo=IST)


def c(summary, **kw):
    return Corrigendum(bid_no="GEM/2026/B/1", summary=summary, source_url=kw.pop("url", "https://n/1"), **kw)


@pytest.mark.parametrize("summary,expected", [
    ("Bid end date extended to 02-11-2026", datetime(2026, 11, 2, 15, 0, tzinfo=IST)),
    ("Corrigendum: last date extended to 5 November 2026", datetime(2026, 11, 5, 15, 0, tzinfo=IST)),
    ("Revised closing date 03/11/2026 15:00", datetime(2026, 11, 3, 15, 0, tzinfo=IST)),
    ("Bid opening date changed to 02-11-2026", None),          # not an extension
    ("Bid end date extended to 20-10-2026", None),              # earlier than the current deadline
    ("Technical specification amended", None),
])
def test_extension_date(summary, expected):
    assert corr.extension_date(c(summary), END) == expected


def test_explicit_new_end_date_wins():
    new = datetime(2026, 11, 9, 18, 0, tzinfo=IST)
    assert corr.extension_date(c("anything", new_end_date=new), END) == new


def test_check_merges_dedupes_extends_and_survives_failures(monkeypatch):
    bid1 = BidListing(portal="gem", bid_no="GEM/2026/B/1", title="Steel rack", end_date=END, source_url="u")
    bid2 = BidListing(portal="gem", bid_no="GEM/2026/B/2", title="Almirah", end_date=END, source_url="u")
    existing = [{"source_url": "https://n/old", "summary": "old notice"}]
    monkeypatch.setattr(corr, "_open_tenders", lambda ids: [(1, bid1, list(existing)), (2, bid2, [])])
    saved = {}
    monkeypatch.setattr(corr, "_save", lambda tid, cs, new_end: saved.update({tid: (cs, new_end)}))

    async def search(bid):
        if bid.bid_no.endswith("2"):
            raise TimeoutError
        return [c("old notice", url="https://n/old"), c("End date extended to 04-11-2026", url="https://n/2")]

    monkeypatch.setattr(corr, "search_corrigenda", search)
    events = []
    res = asyncio.run(corr.check_corrigenda([1, 2], lambda *a: events.append(a)))

    assert res == {"checked": 2, "new": 1, "extended": 1, "changed_tender_ids": [1]}
    cs, new_end = saved[1]
    assert len(cs) == 2 and cs[-1]["extends_to"].startswith("2026-11-04")
    assert new_end == datetime(2026, 11, 4, 15, 0, tzinfo=IST)
    assert events[0][0] == "started" and events[-1][0] == "result" and events[-1][2] == 1
    assert any("couldn't search" in e[1] for e in events)


def test_card_emitter_turns_second_started_into_step():
    out = []
    emit = corr.card_emitter("s", out.append)
    emit("started", "Waiting for bids", None)
    emit("started", "Checking 3 open bids", None)
    emit("step", "GEM/1: 0 new", None)
    emit("result", "Found 0 new corrigenda", 0)
    assert [e.type for e in out] == ["started", "step", "step", "result"]
    assert all(e.agent == "corrigenda" for e in out) and out[-1].count == 0


def test_corrigendum_shows_as_info_reason_with_link():
    p = ProfileFacts(12_000_000, 8, ["Udyam"], ["Haryana"])
    el = {"min_turnover": {"value": 1, "source_clause": "x"}}
    r = evaluate(p, END, el, now=END - timedelta(days=1),
                 corrigenda=[{"summary": "End date extended", "source_url": "https://n/2",
                              "extends_to": "2026-11-04T15:00:00+05:30"}])
    info = [x for x in r.reasons if x["criterion"] == "corrigendum"]
    assert info[0]["text"] == "Deadline extended to 04 Nov" and info[0]["source_url"] == "https://n/2"
    assert r.verdict == "ELIGIBLE"  # informational, does not change the verdict


def test_scheduler_registers_daily_job():
    from api import scheduler

    async def run():
        scheduler.start()
        try:
            nxt = datetime.fromisoformat(scheduler.next_run())
            assert nxt.hour == scheduler.CORRIGENDA_HOUR and nxt.minute == 0
        finally:
            scheduler.stop()

    asyncio.run(run())


def test_extension_keeps_ist_time_when_deadline_comes_back_in_utc():
    from datetime import timezone
    utc_end = END.astimezone(timezone.utc)  # 09:30 UTC == 15:00 IST, as Postgres returns it
    assert corr.extension_date(c("End date extended to 02-11-2026"), utc_end) == \
        datetime(2026, 11, 2, 15, 0, tzinfo=IST)
