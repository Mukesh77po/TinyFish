"""Corrigenda: deadline extensions and changed terms posted after a bid opens.

TinyFish Search (via agents.search_corrigenda) runs per open bid. New corrigenda are merged into
tenders.corrigenda, and a readable extension date moves tenders.end_date. Runs as the 4th agent card
in every sweep and once a day for all open bids (api/scheduler.py).
"""
import asyncio
import logging
import re
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select

from agents.client import search_corrigenda
from agents.schemas import IST, BidListing, Corrigendum, StepEvent, parse_portal_date
from api.clock import as_ist, now_ist
from api.db import SessionLocal
from api.models import Tender

log = logging.getLogger("api.corrigenda")
SEARCH_CONCURRENCY = 4
SEARCH_TIMEOUT = 45  # seconds per bid

_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
_DATE = re.compile(rf"\b(\d{{1,2}})[-/. ](\d{{1,2}}|(?:{_MONTHS})[a-z]*)[-/., ]+(\d{{4}})\b", re.I)
_EXTENDED = re.compile(r"extend|extension|revised|postpone|new (?:closing|end|due|submission)", re.I)


def extension_date(c: Corrigendum, current_end: datetime) -> datetime | None:
    """The new closing date if this corrigendum extends the deadline, else None."""
    if c.new_end_date:
        return c.new_end_date if c.new_end_date > current_end else None
    if not _EXTENDED.search(c.summary):
        return None
    local_end = as_ist(current_end)  # the DB hands back UTC; keep the IST time of day
    found = []
    for d, m, y in _DATE.findall(c.summary):
        m = m[:3].title() if m.isalpha() else m
        try:
            # keep the original time of day: extensions usually move the date, not the hour
            day = parse_portal_date(f"{d}-{m}-{y}")
            found.append(day.replace(hour=local_end.hour, minute=local_end.minute))
        except ValueError:
            continue
    later = [x for x in found if x > current_end]
    return max(later) if later else None


def _open_tenders(tender_ids: list[int] | None) -> list[tuple[int, BidListing, list]]:
    with SessionLocal() as db:
        q = select(Tender).where(Tender.end_date >= now_ist())
        if tender_ids is not None:
            q = q.where(Tender.id.in_(tender_ids))
        out = []
        for t in db.scalars(q):
            bid = BidListing(portal=t.portal, bid_no=t.bid_no, title=t.title, item=t.item, buyer=t.buyer,
                             quantity=t.quantity, est_value=t.est_value, end_date=t.end_date,
                             doc_url=t.doc_url, source_url=t.source_url)
            out.append((t.id, bid, list(t.corrigenda or [])))
        return out


def _save(tender_id: int, corrigenda: list, new_end: datetime | None) -> None:
    with SessionLocal() as db:
        t = db.get(Tender, tender_id)
        t.corrigenda = corrigenda
        if new_end:
            t.end_date = new_end
        db.commit()


async def check_corrigenda(tender_ids: list[int] | None = None,
                           emit: Callable[[str, str, int | None], None] | None = None) -> dict:
    """Search corrigenda for open tenders (all open ones if tender_ids is None).

    emit(type, message, count) drives the 'corrigenda' agent card; omit it for the daily job.
    Returns {"checked", "new", "extended", "changed_tender_ids"}. Never raises per bid.
    """
    emit = emit or (lambda *a: None)
    todo = await asyncio.to_thread(_open_tenders, tender_ids)
    emit("started", f"Checking {len(todo)} open bids for corrigenda and deadline extensions", None)
    sem = asyncio.Semaphore(SEARCH_CONCURRENCY)
    changed: list[int] = []
    totals = {"new": 0, "extended": 0}

    async def one(tid: int, bid: BidListing, existing: list) -> None:
        try:
            async with sem:
                found = await asyncio.wait_for(search_corrigenda(bid), SEARCH_TIMEOUT)
            seen = {(c.get("source_url"), c.get("summary")) for c in existing}
            fresh = [c for c in found if (c.source_url, c.summary) not in seen]
            new_end = None
            for c in fresh:
                ext = extension_date(c, new_end or bid.end_date)
                new_end = ext or new_end
                existing.append({**c.model_dump(mode="json"), "found_at": datetime.now(IST).isoformat(),
                                 "extends_to": ext.isoformat() if ext else None})
            if fresh:
                await asyncio.to_thread(_save, tid, existing, new_end)
                changed.append(tid)
                totals["new"] += len(fresh)
                totals["extended"] += bool(new_end)
            msg = f"{bid.bid_no}: {len(fresh)} new" + (f", deadline now {new_end:%d %b}" if new_end else "")
        except Exception as e:
            log.warning("corrigenda search failed for %s: %r", bid.bid_no, e)
            msg = f"{bid.bid_no}: couldn't search ({type(e).__name__})"
        emit("step", msg, None)

    await asyncio.gather(*(one(*row) for row in todo))
    emit("result", f"Found {totals['new']} new corrigenda" +
         (f", {totals['extended']} deadline extensions" if totals["extended"] else ""), totals["new"])
    return {"checked": len(todo), **totals, "changed_tender_ids": changed}


def card_emitter(sweep_id: str, publish: Callable[[StepEvent], None]) -> Callable[[str, str, int | None], None]:
    """Adapts check_corrigenda's emit to §3.3 StepEvents on the 'corrigenda' card."""
    step = 0
    started = False

    def emit(type_: str, message: str, count: int | None) -> None:
        nonlocal step, started
        if type_ == "started":
            if started:
                type_ = "step"
            started = True
        step += type_ == "step"
        publish(StepEvent(sweep_id=sweep_id, agent="corrigenda", type=type_, step=step, message=message,
                          count=count))
    return emit
