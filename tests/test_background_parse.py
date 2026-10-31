"""A live sweep finishes on stage: known documents are reused, new ones are read after all/done (PLAN §3.3)."""
import asyncio
import json

import pytest

from agents.schemas import StepEvent
from api import events as ev_mod
from api import sweeps


@pytest.fixture
def events(monkeypatch):
    out = []
    monkeypatch.setattr(sweeps, "publish", out.append)
    return out


def _final(**kw) -> bool:
    return ev_mod._is_final(StepEvent(sweep_id="s", agent="all", **kw).model_dump_json())


def test_stream_ends_at_done_only_when_nothing_is_pending():
    assert _final(type="done", pending=0)
    assert _final(type="done")
    assert not _final(type="done", pending=3)
    assert not _final(type="update", tender_id=1)
    assert _final(type="settled")
    assert not ev_mod._is_final(StepEvent(sweep_id="s", agent="gem", type="done").model_dump_json())


def test_known_documents_are_reused_from_db_then_fixtures(monkeypatch):
    saved_text, saved_el = [], []
    monkeypatch.setattr(sweeps, "tenders_needing_documents",
                        lambda ids: [(1, "u-db", False), (2, "u-fx", False), (3, "u-new", False), (4, "u-db", True)])
    monkeypatch.setattr(sweeps, "known_documents", lambda urls: {
        "u-db": {"text": "db text", "doc_source": "direct", "eligibility": {"a": 1}, "eligibility_source": "llm"}})
    monkeypatch.setattr(sweeps, "_fixture_documents", lambda: {
        "u-fx": {"text": "fx text", "doc_source": "fixture", "eligibility": {"b": 2}, "eligibility_source": "recorded"},
        "u-db": {"text": "stale", "doc_source": "fixture", "eligibility": {"old": 0}, "eligibility_source": "recorded"}})
    monkeypatch.setattr(sweeps, "save_doc_text", lambda tid, t, s: saved_text.append((tid, t, s)))
    monkeypatch.setattr(sweeps, "save_eligibility", lambda tid, el, s: saved_el.append((tid, el, s)))

    assert asyncio.run(sweeps._reuse_known_documents([1, 2, 3, 4])) == 3
    assert saved_text == [(1, "db text", "direct"), (2, "fx text", "fixture")]   # 4 already had its text
    assert saved_el == [(1, {"a": 1}, "llm"), (2, {"b": 2}, "recorded"), (4, {"a": 1}, "llm")]


def _fake_sweep(monkeypatch, pending_after_reuse):
    calls = []

    async def portal(sweep_id, p, kws):
        return []
    async def reuse(ids):
        calls.append("reuse")
        return 1
    async def corr(ids, card):
        return {"new": 0}
    async def rematch(pid, ids=None, *, only=False):
        calls.append(("rematch", ids, only))
        return {"counts": {"ELIGIBLE": 1}, "relevant": 1, "total": 1}
    async def alert(sweep_id, pid):
        calls.append("alert")
        return 0
    async def fetch_docs(sweep_id, ids):
        calls.append("fetch")
        return len(ids)
    async def parse(sweep_id, ids, on_parsed=None):
        calls.append("parse")
        for tid in ids:
            await on_parsed(tid)
        return len(ids)

    monkeypatch.setattr(sweeps, "_load_keywords", lambda pid: ["storage rack"])
    monkeypatch.setattr(sweeps, "card_emitter", lambda sid, pub: lambda *a: None)
    monkeypatch.setattr(sweeps, "_sweep_portal_all_keywords", portal)
    monkeypatch.setattr(sweeps, "upsert_tenders", lambda bids: ([7, 8], [8]))
    monkeypatch.setattr(sweeps, "_reuse_known_documents", reuse)
    monkeypatch.setattr(sweeps, "check_corrigenda", corr)
    monkeypatch.setattr(sweeps, "rematch", rematch)
    monkeypatch.setattr(sweeps, "_auto_alert", alert)
    monkeypatch.setattr(sweeps, "tenders_needing_documents", lambda ids: [(t, "u", False) for t in pending_after_reuse])
    monkeypatch.setattr(sweeps, "bid_numbers", lambda ids: {8: "GEM/2026/B/8"})
    monkeypatch.setattr(sweeps, "_fetch_docs", fetch_docs)
    monkeypatch.setattr(sweeps, "_parse_docs", parse)
    return calls


def test_done_fires_before_new_documents_are_read(monkeypatch, events):
    calls = _fake_sweep(monkeypatch, pending_after_reuse=[8])
    asyncio.run(sweeps.run_sweep("s", 1))

    kinds = [(e.agent, e.type) for e in events]
    done = kinds.index(("all", "done"))
    assert events[done].pending == 1 and "background" in events[done].message
    assert kinds[done + 1:].count(("all", "update")) == 1 and kinds[-1] == ("all", "settled")
    assert events[done + 1:][[k for k in kinds[done + 1:]].index(("all", "update"))].tender_id == 8
    assert calls.index("fetch") > calls.index("alert")              # documents read only after done
    assert ("rematch", [8], True) in calls and calls[-1] == "alert"  # late parse re-matches that tender, then alerts


def test_nothing_new_means_done_is_final(monkeypatch, events):
    calls = _fake_sweep(monkeypatch, pending_after_reuse=[])
    asyncio.run(sweeps.run_sweep("s", 1))
    assert events[-1].type == "done" and not events[-1].pending
    assert "fetch" not in calls


def test_background_crash_still_settles(monkeypatch, events):
    _fake_sweep(monkeypatch, pending_after_reuse=[8])

    async def boom(*a, **k):
        raise RuntimeError("redis went away")
    monkeypatch.setattr(sweeps, "_fetch_docs", boom)
    asyncio.run(sweeps.run_sweep("s", 1))
    assert [e.type for e in events if e.agent == "all"][-2:] == ["done", "settled"]


def test_groq_failures_leave_eligibility_null_never_crash(monkeypatch, events):
    """429 after retries, 5xx, timeouts all surface as an exception from the parser: the tender stays unparsed."""
    from api.llm import LLMError
    saved = []
    monkeypatch.setattr(sweeps, "tenders_missing_eligibility", lambda ids: [(1, "u1", "a"), (2, "u2", "b"), (3, "u3", "c")])
    monkeypatch.setattr(sweeps, "save_eligibility", lambda tid, el, s=None: saved.append(tid))

    async def parse(text):
        if text == "a":
            raise LLMError("Groq rate limit (free tier: 8k tokens/min); try again in a minute")
        if text == "b":
            raise asyncio.TimeoutError()
        return {"min_turnover": {"value": 1, "source_clause": "x"}}
    monkeypatch.setattr(sweeps, "parse_eligibility", parse)
    assert asyncio.run(sweeps._parse_docs("s", [1, 2, 3])) == 1 and saved == [3]
