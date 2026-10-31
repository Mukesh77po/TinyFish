"""Live-sweep behaviour of agents/client.py, with TinyFish replaced by fakes (no credits)."""
import asyncio
from datetime import datetime, timedelta

import pytest

from agents import client
from agents.goals import goal_for
from agents.schemas import IST

REAL = [
    "The Haryana e-procurement site requires a captcha to perform tender searches.",
    "The GEM Bid Plus website (bidplus.gem.gov.in) is unreachable. ERR_TUNNEL_CONNECTION_FAILED",
    "Login required to see this list",
]
NOT_REAL = [  # all seen in TinyFish's run history on 25 Oct
    "Site has 842 results for 'rack' and 686 results for 'storage rack', but none of the bids on the first 2 "
    "pages of either search are for physical storage racks.",
    "Cleared the page description task and returned blocked status",
    "none", "", None,
]


@pytest.mark.parametrize("reason", REAL)
def test_real_blocks(reason):
    assert client.is_real_block(reason)


@pytest.mark.parametrize("reason", NOT_REAL)
def test_nothing_relevant_is_not_a_block(reason):
    assert not client.is_real_block(reason)


def _bid(n=1):
    end = (datetime.now(IST) + timedelta(days=10)).strftime("%d-%m-%Y %I:%M %p")
    return {"bid_no": f"GEM/2026/B/{n}", "title": "Steel Almirah / Cabinets (V4)", "end_date": end,
            "doc_url": f"https://bidplus.gem.gov.in/showbidDocument/{n}"}


def _sweep(monkeypatch, result, portal="gem"):
    monkeypatch.setenv("FALLBACK_MODE", "false")
    monkeypatch.delenv("LIVE_PORTALS", raising=False)

    async def fake_run(p, kw, on_step):
        on_step(1, "Search")
        return {"run_id": "r", "url": "u", "goal": "g", "steps": [{"step": 1, "message": "Search"}], "result": result}

    monkeypatch.setattr(client, "run_agent", fake_run)
    events = []
    bids = asyncio.run(client.sweep_portal(portal, "steel almirah", events.append))
    return bids, events[-1]


def test_agent_saying_blocked_without_access_problem_is_a_zero_result(monkeypatch):
    bids, last = _sweep(monkeypatch, {"bids": [], "blocked": True, "blocked_reason": NOT_REAL[0]})
    assert bids == [] and last.type == "result" and last.count == 0 and "No relevant open bids" in last.message


def test_captcha_is_still_an_error_with_the_portal_link(monkeypatch):
    bids, last = _sweep(monkeypatch, {"bids": [], "blocked": True, "blocked_reason": REAL[0]})
    assert bids == [] and last.type == "error" and last.direct_url and "captcha" in last.message


def test_bids_win_over_a_blocked_flag(monkeypatch):
    bids, last = _sweep(monkeypatch, {"bids": [_bid(1), _bid(2)], "blocked": True, "blocked_reason": REAL[0]})
    assert len(bids) == 2 and last.type == "result" and last.count == 2


def test_live_portals_replays_the_others_labelled(monkeypatch):
    monkeypatch.setenv("FALLBACK_MODE", "false")
    monkeypatch.setenv("LIVE_PORTALS", "gem")
    calls = []

    async def fake_replay(portal, category, emit, sweep_id, labelled=False):
        calls.append((portal, labelled))
        return []

    async def fake_run(p, kw, on_step):
        calls.append((p, "live"))
        return {"run_id": "r", "url": "u", "goal": "g", "steps": [], "result": {"bids": []}}

    monkeypatch.setattr(client, "_replay", fake_replay)
    monkeypatch.setattr(client, "run_agent", fake_run)
    for p in ("gem", "cppp", "haryana"):
        asyncio.run(client.sweep_portal(p, "storage rack", lambda e: None))
    assert calls == [("gem", "live"), ("cppp", True), ("haryana", True)]
    assert client.live_portals() == {"gem"}
    monkeypatch.delenv("LIVE_PORTALS")
    assert client.live_portals() == {"gem", "cppp", "haryana"}


def test_labelled_replay_says_it_is_a_recording(monkeypatch):
    events = []
    asyncio.run(client._replay("cppp", "storage rack", events.append, "s", labelled=True))
    assert events[0].type == "started" and events[0].message.startswith("Replaying the recorded run from")


def test_defaults_match_live_run_durations_and_gem_ordering():
    assert client.AGENT_TIMEOUT >= 480          # live GeM runs took 300-512 s
    _, goal = goal_for("gem", "steel almirah")
    tomorrow = (datetime.now(IST) + timedelta(days=1)).strftime("%d %b %Y")
    assert f"on or after {tomorrow}" in goal    # GeM lists closing-soonest first
