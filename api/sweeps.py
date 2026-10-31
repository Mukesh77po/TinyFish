"""Sweep orchestration: portals x profile keywords -> tenders in Postgres, events on Redis.

Each portal card in the UI gets one started -> steps -> result|error sequence, even though a portal
is searched once per keyword: per-keyword started/result/error events are folded into steps.
Nothing in here may raise out of run_sweep: one bad portal or document never sinks the sweep.

A live sweep must finish on stage, so all/done fires once listings, already-known documents (same doc_url in
the DB or a fixture) and corrigenda are matched. Documents never seen before are then read and parsed in
the background (Groq free tier: one at a time); each one re-matches its tender and publishes all/update,
and all/settled closes the stream.
"""
import asyncio
import json
import logging
import os

from agents.client import live_portals, FIXTURES_DIR, fetch_doc_text, sweep_portal
from agents.goals import PORTALS
from agents.schemas import BidListing, StepEvent
from api import llm
from api.config import fallback_mode
from api.corrigenda import card_emitter, check_corrigenda
from api.db import SessionLocal
from api.eligibility import parse_eligibility
from api.events import publish
from api.matching import rematch
from api.models import Profile
from delivery.alerts import auto_alert
from api.tenders import (bid_numbers, known_documents, save_doc_text, save_eligibility, tenders_missing_eligibility,
                         tenders_missing_text, tenders_needing_documents, upsert_tenders)

log = logging.getLogger("api.sweeps")
DOC_FETCH_CONCURRENCY = 4
DOC_FETCH_TIMEOUT = 90     # seconds per document
PARSE_TIMEOUT = 240        # seconds per document (LLM)
# Each live keyword is one billed TinyFish Agent run per portal (~150 s). Fixture replay is free.
LIVE_MAX_KEYWORDS = int(os.getenv("LIVE_MAX_KEYWORDS", "1"))


def _keywords(profile: Profile) -> list[str]:
    return [k.strip() for k in (profile.keywords or profile.products[:2]) if k and k.strip()]


def _portal_keywords(portal: str, keywords: list[str]) -> list[str]:
    """Live runs are billed, so they search the first LIVE_MAX_KEYWORDS; replays are free and use them all."""
    live = not fallback_mode() and portal in live_portals()
    return keywords[:LIVE_MAX_KEYWORDS] if live else keywords


def _load_keywords(profile_id: int) -> list[str]:
    with SessionLocal() as db:
        return _keywords(db.get(Profile, profile_id))


async def _sweep_portal_all_keywords(sweep_id: str, portal: str, keywords: list[str]) -> list[BidListing]:
    step = 0
    direct_url = PORTALS[portal]["url"]

    def ev(type_: str, message: str, **kw) -> None:
        publish(StepEvent(sweep_id=sweep_id, agent=portal, type=type_, step=step, message=message, **kw))

    ev("started", f"Searching {direct_url} for {', '.join(keywords)}")
    bids: dict[str, BidListing] = {}
    errors: list[str] = []
    try:
        for kw in keywords:
            before = len(errors)

            def relay(e: StepEvent, kw: str = kw) -> None:
                nonlocal step
                step += 1
                if e.type == "error":
                    errors.append(e.message)
                ev("step", f"[{kw}] " + (f"Found {e.count} bids" if e.type == "result" else e.message))

            for b in await sweep_portal(portal, kw, relay, sweep_id):
                bids.setdefault(b.bid_no, b)
            if len(errors) > before and "blocked" in errors[-1].lower():
                break  # captcha / login wall: don't hammer the portal with the other keywords
    except Exception as e:  # bad fixture row, Redis hiccup...: this card fails, the sweep goes on
        log.exception("%s portal sweep crashed", portal)
        errors.append(f"{portal} sweep failed: {e}")

    if not bids and errors:
        ev("error", errors[-1], direct_url=direct_url)
        return []
    ev("result", f"Found {len(bids)} bids", count=len(bids))
    return list(bids.values())


async def _fetch_docs(sweep_id: str, tender_ids: list[int]) -> int:
    todo = await asyncio.to_thread(tenders_missing_text, tender_ids)
    if not todo:
        return 0
    publish(StepEvent(sweep_id=sweep_id, agent="all", type="step", message=f"Reading {len(todo)} bid documents"))
    sem = asyncio.Semaphore(DOC_FETCH_CONCURRENCY)

    async def one(tid: int, url: str) -> bool:
        try:
            async with sem:
                text, source = await asyncio.wait_for(fetch_doc_text(url), DOC_FETCH_TIMEOUT)
            if text:
                await asyncio.to_thread(save_doc_text, tid, text, source)
            return bool(text)
        except Exception as e:
            log.warning("document fetch/save failed for tender %s (%s): %r", tid, url, e)
            return False

    return sum(await asyncio.gather(*(one(t, u) for t, u in todo)))


def _fixture_documents() -> dict[str, dict]:
    """Recorded document texts and parses ({doc_url: {...}}), reused in live and fallback mode."""
    out: dict[str, dict] = {}
    for p in FIXTURES_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text())
        except (OSError, ValueError):
            log.warning("unreadable fixture %s", p)
            continue
        if not isinstance(data, dict):
            continue
        parses = data.get("eligibility") or {}
        for url, text in (data.get("docs") or {}).items():
            if text:
                out[url] = {"text": text, "doc_source": "fixture", "eligibility": parses.get(url),
                            "eligibility_source": "recorded" if parses.get(url) else None}
    return out


async def _reuse_known_documents(tender_ids: list[int]) -> int:
    """Fill text + parse from an earlier read of the same doc_url (DB first, then fixtures). Returns how many."""
    rows = await asyncio.to_thread(tenders_needing_documents, tender_ids)
    if not rows:
        return 0
    known = {**await asyncio.to_thread(_fixture_documents),
             **await asyncio.to_thread(known_documents, [u for _, u, _ in rows])}
    reused = 0
    for tid, url, has_text in rows:
        k = known.get(url)
        if not k:
            continue
        try:
            if not has_text:
                await asyncio.to_thread(save_doc_text, tid, k["text"], k["doc_source"])
            if k["eligibility"] is not None:
                await asyncio.to_thread(save_eligibility, tid, k["eligibility"], k["eligibility_source"])
                reused += 1
        except Exception as e:
            log.warning("reusing the known document for tender %s failed: %r", tid, e)
    return reused


async def _parse_docs(sweep_id: str, tender_ids: list[int], on_parsed=None) -> int:
    """Eligibility for every tender that has text but no parse yet. Failures leave it null (-> CHECK_DOCS).

    on_parsed(tender_id) runs after each successful parse (re-match + update event)."""
    todo = await asyncio.to_thread(tenders_missing_eligibility, tender_ids)
    if not todo:
        return 0
    publish(StepEvent(sweep_id=sweep_id, agent="all", type="step",
                      message=f"Reading eligibility criteria from {len(todo)} documents"))
    sem = asyncio.Semaphore(llm.LLM_CONCURRENCY)

    async def one(tid: int, doc_url: str | None, text: str) -> bool:
        try:
            async with sem:
                el = await asyncio.wait_for(parse_eligibility(text), PARSE_TIMEOUT)
            await asyncio.to_thread(save_eligibility, tid, el, "llm")
        except Exception as e:  # LLMError (incl. Groq 429/5xx), timeout, DB error: stays unparsed -> CHECK_DOCS
            log.warning("eligibility parse failed for tender %s: %r", tid, e)
            return False
        if on_parsed:
            try:
                await on_parsed(tid)
            except Exception:
                log.exception("re-match after parsing tender %s failed", tid)
        return True

    return sum(await asyncio.gather(*(one(*row) for row in todo)))


async def _read_new_documents(sweep_id: str, profile_id: int, tender_ids: list[int]) -> tuple[int, int]:
    """Background part of a sweep: fetch + parse documents never seen before, re-matching as each lands."""
    names = await asyncio.to_thread(bid_numbers, tender_ids)

    async def updated(tid: int) -> None:
        m = await rematch(profile_id, [tid], only=True)
        verdict = next(iter(m["counts"]), None)
        publish(StepEvent(sweep_id=sweep_id, agent="all", type="update", tender_id=tid,
                          message=f"Read eligibility for {names.get(tid, tid)}" + (f": {verdict}" if verdict else "")))

    read = await _fetch_docs(sweep_id, tender_ids)
    parsed = await _parse_docs(sweep_id, tender_ids, on_parsed=updated)
    return read, parsed


async def _auto_alert(sweep_id: str, profile_id: int) -> int:
    try:
        sent = await auto_alert(profile_id)
    except Exception:
        log.exception("auto-alert failed")
        return 0
    if sent:
        publish(StepEvent(sweep_id=sweep_id, agent="all", type="step",
                          message=f"Sent {sent} WhatsApp/email alert{'s' if sent != 1 else ''} for new eligible tenders"))
    return sent


async def run_sweep(sweep_id: str, profile_id: int) -> None:
    """Background task for POST /sweeps. Never raises; always ends with exactly one all/done event,
    followed by all/settled when documents were left to read in the background (pending > 0)."""
    summary, pending = "Sweep failed", []
    try:
        keywords = await asyncio.to_thread(_load_keywords, profile_id)
        if not keywords:
            publish(StepEvent(sweep_id=sweep_id, agent="all", type="error",
                              message="Profile has no keywords or products to search for"))
            summary = "Nothing to search for"
            return
        corr_card = card_emitter(sweep_id, publish)
        corr_card("started", "Waiting for bids from the portals", None)
        per_portal = await asyncio.gather(
            *(_sweep_portal_all_keywords(sweep_id, p, _portal_keywords(p, keywords)) for p in PORTALS))
        bids = [b for bs in per_portal for b in bs]
        all_ids, new_ids = await asyncio.to_thread(upsert_tenders, bids)

        async def corrigenda() -> dict:
            try:
                return await check_corrigenda(all_ids, corr_card)
            except Exception as e:
                log.exception("corrigenda check failed")
                corr_card("error", f"Corrigenda check failed: {e}", None)
                return {"new": 0}

        reused, corr = await asyncio.gather(_reuse_known_documents(all_ids), corrigenda())
        publish(StepEvent(sweep_id=sweep_id, agent="all", type="step",
                          message="Matching tenders against your profile"))
        m = await rematch(profile_id)
        c = m["counts"]
        alerts = await _auto_alert(sweep_id, profile_id)
        pending = [tid for tid, _, _ in await asyncio.to_thread(tenders_needing_documents, all_ids)]
        low = m["total"] - m["relevant"]
        summary = (f"{len(all_ids)} tenders found ({len(new_ids)} new), {reused} with known eligibility. "
                   f"{c.get('ELIGIBLE', 0)} eligible, {c.get('CHECK_DOCS', 0)} check docs, "
                   f"{c.get('NOT_ELIGIBLE', 0)} not eligible"
                   + (f", {low} low-relevance hidden" if low else "")
                   + (f". {corr['new']} new corrigenda" if corr.get("new") else "")
                   + (f". {alerts} alert{'s' if alerts != 1 else ''} sent" if alerts else "")
                   + (f". Reading {len(pending)} new document{'s' if len(pending) != 1 else ''} in the background"
                      if pending else ""))
    except Exception as e:
        log.exception("sweep %s failed", sweep_id)
        publish(StepEvent(sweep_id=sweep_id, agent="all", type="error", message=f"Sweep failed: {e}"))
        pending = []
    finally:
        publish(StepEvent(sweep_id=sweep_id, agent="all", type="done", message=summary, pending=len(pending)))
    if pending:
        await _settle(sweep_id, profile_id, pending)


async def _settle(sweep_id: str, profile_id: int, pending: list[int]) -> None:
    """After all/done: read the new documents, then one all/settled. Never raises."""
    message = "Background reading failed"
    try:
        read, parsed = await _read_new_documents(sweep_id, profile_id, pending)
        alerts = await _auto_alert(sweep_id, profile_id)
        message = (f"{read} new document{'s' if read != 1 else ''} read, {parsed} parsed"
                   + (f". {alerts} alert{'s' if alerts != 1 else ''} sent" if alerts else ""))
    except Exception:
        log.exception("background reading for sweep %s failed", sweep_id)
    finally:
        publish(StepEvent(sweep_id=sweep_id, agent="all", type="settled", message=message))
