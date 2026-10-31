"""Tender persistence: upsert + dedupe on (portal, bid_no)."""
from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert

from agents.schemas import BidListing
from api.db import SessionLocal
from api.models import Tender

_KEEP_IF_NULL = ("item", "buyer", "quantity", "est_value", "doc_url")


def upsert_tenders(bids: list[BidListing]) -> tuple[list[int], list[int]]:
    """Insert or refresh tenders. Returns (all_ids, new_ids)."""
    if not bids:
        return [], []
    rows = {(b.portal, b.bid_no): b.model_dump() for b in bids}  # dedupe within the batch too
    stmt = insert(Tender).values(list(rows.values()))
    ex = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        constraint="uq_tender_portal_bid",
        set_={
            "title": ex.title,
            "end_date": ex.end_date,
            "source_url": ex.source_url,
            **{c: func.coalesce(getattr(ex, c), getattr(Tender, c)) for c in _KEEP_IF_NULL},
            "updated_at": func.now(),
        },
    ).returning(Tender.id, literal_column("(xmax = 0)").label("inserted"))
    with SessionLocal() as db:
        res = db.execute(stmt).all()
        db.commit()
    return [r.id for r in res], [r.id for r in res if r.inserted]


def tenders_missing_text(ids: list[int]) -> list[tuple[int, str]]:
    with SessionLocal() as db:
        q = select(Tender.id, Tender.doc_url).where(
            Tender.id.in_(ids), Tender.doc_text.is_(None), Tender.doc_url.is_not(None))
        return [(r.id, r.doc_url) for r in db.execute(q)]


def save_doc_text(tender_id: int, text: str, source: str | None = None) -> None:
    with SessionLocal() as db:
        t = db.get(Tender, tender_id)
        t.doc_text = text
        t.doc_source = source
        db.commit()


def tenders_missing_eligibility(ids: list[int]) -> list[tuple[int, str | None, str]]:
    with SessionLocal() as db:
        q = select(Tender.id, Tender.doc_url, Tender.doc_text).where(
            Tender.id.in_(ids), Tender.doc_text.is_not(None), Tender.eligibility.is_(None))
        return [(r.id, r.doc_url, r.doc_text) for r in db.execute(q)]


def save_eligibility(tender_id: int, eligibility: dict, source: str | None = None) -> None:
    with SessionLocal() as db:
        t = db.get(Tender, tender_id)
        t.eligibility = eligibility
        t.eligibility_source = source
        db.commit()


def known_documents(urls: list[str]) -> dict[str, dict]:
    """Text and parse already stored for these doc_urls (any tender), so a document is read and parsed once."""
    if not urls:
        return {}
    with SessionLocal() as db:
        q = select(Tender.doc_url, Tender.doc_text, Tender.doc_source, Tender.eligibility, Tender.eligibility_source
                   ).where(Tender.doc_url.in_(urls), Tender.doc_text.is_not(None))
        out: dict[str, dict] = {}
        for r in db.execute(q):
            prev = out.get(r.doc_url)
            if prev is None or (prev["eligibility"] is None and r.eligibility is not None):
                out[r.doc_url] = {"text": r.doc_text, "doc_source": r.doc_source,
                                  "eligibility": r.eligibility, "eligibility_source": r.eligibility_source}
        return out


def tenders_needing_documents(ids: list[int]) -> list[tuple[int, str, bool]]:
    """(id, doc_url, has_text) for tenders still missing their document text or its parse."""
    with SessionLocal() as db:
        q = select(Tender.id, Tender.doc_url, Tender.doc_text.is_not(None).label("has_text")).where(
            Tender.id.in_(ids), Tender.doc_url.is_not(None),
            (Tender.doc_text.is_(None)) | (Tender.eligibility.is_(None)))
        return [(r.id, r.doc_url, r.has_text) for r in db.execute(q)]


def bid_numbers(ids: list[int]) -> dict[int, str]:
    with SessionLocal() as db:
        return dict(db.execute(select(Tender.id, Tender.bid_no).where(Tender.id.in_(ids))).all())
