"""Sweep orchestration: per-portal isolation and the blocked-portal contract (PLAN §3.2/§3.3).
No Redis/DB/web: publish and sweep_portal are replaced with fakes."""
import asyncio
from datetime import datetime, timedelta

import pytest

from agents.schemas import IST, BidListing, StepEvent
from api import sweeps


@pytest.fixture
def events(monkeypatch):
    out = []
    monkeypatch.setattr(sweeps, "publish", out.append)
    return out


def bid(n):
    return BidListing(portal="gem", bid_no=f"GEM/2026/B/{n}", title="Steel rack",
                      end_date=datetime.now(IST) + timedelta(days=3), source_url="https://x")


def test_blocked_first_keyword_emits_error_with_direct_url(monkeypatch, events):
    calls = []

    async def fake(portal, kw, emit, sweep_id):
        calls.append(kw)
        emit(StepEvent(sweep_id=sweep_id, agent=portal, type="error", message="Blocked: captcha. Open on portal.",
                       direct_url="https://portal"))
        return []

    monkeypatch.setattr(sweeps, "sweep_portal", fake)
    out = asyncio.run(sweeps._sweep_portal_all_keywords("s", "cppp", ["steel rack", "almirah", "structure"]))
    assert out == [] and calls == ["steel rack"]          # stops after the captcha
    last = events[-1]
    assert last.type == "error" and last.direct_url and "Blocked" in last.message


def test_portal_crash_becomes_error_event_not_exception(monkeypatch, events):
    async def boom(*a):
        raise ValueError("bad fixture row")

    monkeypatch.setattr(sweeps, "sweep_portal", boom)
    assert asyncio.run(sweeps._sweep_portal_all_keywords("s", "gem", ["steel rack"])) == []
    assert events[-1].type == "error" and events[-1].direct_url


def test_partial_failure_still_returns_bids(monkeypatch, events):
    async def fake(portal, kw, emit, sweep_id):
        if kw == "a":
            emit(StepEvent(sweep_id=sweep_id, agent=portal, type="error", message="timeout"))
            return []
        return [bid(1), bid(1), bid(2)]

    monkeypatch.setattr(sweeps, "sweep_portal", fake)
    out = asyncio.run(sweeps._sweep_portal_all_keywords("s", "gem", ["a", "b"]))
    assert len(out) == 2 and events[-1].type == "result" and events[-1].count == 2


def test_one_bad_document_does_not_sink_the_others(monkeypatch, events):
    saved = []
    monkeypatch.setattr(sweeps, "tenders_missing_text", lambda ids: [(1, "u1"), (2, "u2")])
    monkeypatch.setattr(sweeps, "save_doc_text", lambda tid, text, source=None: saved.append((tid, source)))

    async def fetch(url):
        if url == "u1":
            raise RuntimeError("network")
        return "EMD Amount 100000", "direct"

    monkeypatch.setattr(sweeps, "fetch_doc_text", fetch)
    assert asyncio.run(sweeps._fetch_docs("s", [1, 2])) == 1 and saved == [(2, "direct")]


def test_one_bad_parse_does_not_sink_the_others(monkeypatch, events):
    saved = []
    monkeypatch.setattr(sweeps, "tenders_missing_eligibility", lambda ids: [(1, "u1", "a"), (2, "u2", "b")])
    monkeypatch.setattr(sweeps, "save_eligibility", lambda tid, el, source=None: saved.append(tid))
    monkeypatch.setattr(sweeps, "fallback_mode", lambda: False)

    async def parse(text):
        if text == "a":
            raise KeyError("unexpected")
        return {"min_turnover": {"value": 1, "source_clause": "x"}}

    monkeypatch.setattr(sweeps, "parse_eligibility", parse)
    assert asyncio.run(sweeps._parse_docs("s", [1, 2])) == 1 and saved == [2]


def test_live_portals_search_the_first_keyword_replays_use_all(monkeypatch):
    class P:
        keywords = ["a", "b", "c"]
        products = []
    kws = sweeps._keywords(P)
    assert kws == ["a", "b", "c"]
    monkeypatch.setattr(sweeps, "fallback_mode", lambda: False)
    monkeypatch.setattr(sweeps, "live_portals", lambda: {"gem"})
    assert sweeps._portal_keywords("gem", kws) == ["a"]                 # billed: capped
    assert sweeps._portal_keywords("cppp", kws) == ["a", "b", "c"]      # replayed: free
    monkeypatch.setattr(sweeps, "fallback_mode", lambda: True)
    assert sweeps._portal_keywords("gem", kws) == ["a", "b", "c"]
