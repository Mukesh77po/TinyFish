"""TenderHawk API. Run: uvicorn api.main:app --reload"""
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import redis
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload

from api.clock import demo_now, now_ist
from api.config import REDIS_URL, WEB_ORIGINS, fallback_mode
from api import events, scheduler
from delivery.alerts import alert_match, channel_status, preview_match
from api.db import engine, get_db
from api.documents import excerpt
from api.matcher import VERDICT_RANK
from api.matching import rematch
from api import llm
from api.models import Match, Profile, Tender
from api.schemas import (Created, MatchDetail, MatchRunOut, MatchSummary, ProfileIn, ProfileOut, SweepIn,
                         SweepOut)
from api.sweeps import run_sweep

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.stop()


log = logging.getLogger("api.main")
app = FastAPI(title="TenderHawk", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=WEB_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(OperationalError)
async def database_down(request, exc):
    """Postgres unreachable: a plain sentence for the dashboard, never a stack trace or a bare 500."""
    log.warning("database unavailable on %s: %s", request.url.path, str(exc).splitlines()[0])
    return JSONResponse(status_code=503, content={
        "detail": "The database is not reachable. Start it with `docker compose up -d`, then retry."})


@app.get("/health")
def health():
    _, clock = demo_now()
    status = {"db": False, "redis": False, "fallback_mode": fallback_mode(),
              "next_corrigenda_check": scheduler.next_run(),
              "now": now_ist().isoformat(), "clock": clock}  # clock: real | DEMO_NOW | fixture recorded_at
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        status["db"] = True
    except Exception:
        pass
    try:
        status["redis"] = bool(redis.Redis.from_url(REDIS_URL, socket_timeout=1, socket_connect_timeout=1).ping())
    except Exception:
        pass
    return status


@app.post("/profiles", response_model=Created, status_code=201)
def create_profile(body: ProfileIn, db: Session = Depends(get_db)):
    p = Profile(**body.model_dump())
    db.add(p)
    db.commit()
    return Created(id=p.id)


@app.get("/profiles/{profile_id}", response_model=ProfileOut)
def get_profile(profile_id: int, db: Session = Depends(get_db)):
    p = db.get(Profile, profile_id)
    if not p:
        raise HTTPException(404, "profile not found")
    return p


@app.post("/sweeps", response_model=SweepOut, status_code=202)
def start_sweep(body: SweepIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not db.get(Profile, body.profile_id):
        raise HTTPException(404, "profile not found")
    sweep_id = str(uuid.uuid4())
    events.register_sweep(sweep_id, body.profile_id)
    background.add_task(run_sweep, sweep_id, body.profile_id)
    return SweepOut(sweep_id=sweep_id)


@app.get("/sweeps/{sweep_id}/events")
def sweep_events(sweep_id: str):
    if not events.sweep_exists(sweep_id):
        raise HTTPException(404, "sweep not found")
    return StreamingResponse(events.stream(sweep_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/profiles/{profile_id}/matches", response_model=list[MatchSummary])
def list_matches(profile_id: int, include_low_relevance: bool = True, db: Session = Depends(get_db)):
    """Relevant first, then ELIGIBLE > CHECK_DOCS > NOT_ELIGIBLE, then best fit, then soonest deadline."""
    if not db.get(Profile, profile_id):
        raise HTTPException(404, "profile not found")
    q = select(Match).where(Match.profile_id == profile_id).options(selectinload(Match.tender))
    if not include_low_relevance:
        q = q.where(Match.relevant.is_(True))
    matches = db.scalars(q).all()
    return sorted(matches, key=lambda m: (not m.relevant, VERDICT_RANK[m.verdict], -(m.fit_score or 0),
                                          m.tender.end_date))


PORTAL_NAMES = {"gem": "GeM", "cppp": "CPPP", "haryana": "Haryana e-proc"}


def provenance(t: Tender) -> dict:
    name = PORTAL_NAMES.get(t.portal, t.portal)
    return {
        "found_by": f"recorded TinyFish run on {name}" if fallback_mode() else f"TinyFish agent on {name}",
        "portal": t.portal,
        "doc_source": t.doc_source if t.doc_text else None,
        "eligibility_by": None if t.eligibility is None else
                          "recorded parse" if t.eligibility_source == "recorded" else f"LLM ({llm.LLM_MODEL})",
    }


@app.get("/matches/{match_id}", response_model=MatchDetail)
def get_match(match_id: int, db: Session = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(404, "match not found")
    t = m.tender
    reasons = [{**r, "excerpt": excerpt(t.doc_text or "", r.get("source_clause") or "")} for r in m.reasons]
    return MatchDetail(id=m.id, profile_id=m.profile_id, verdict=m.verdict, fit_score=m.fit_score, relevant=m.relevant, reasons=reasons,
                       missing_docs=m.missing_docs, alerted_at=m.alerted_at, tender=t,
                       eligibility=t.eligibility, corrigenda=t.corrigenda or [], provenance=provenance(t))


@app.post("/profiles/{profile_id}/match", response_model=MatchRunOut)
def run_match(profile_id: int, db: Session = Depends(get_db)):
    """Re-run the matcher on stored tenders without sweeping (e.g. after editing the profile)."""
    if not db.get(Profile, profile_id):
        raise HTTPException(404, "profile not found")
    db.close()
    return asyncio.run(rematch(profile_id))  # sync endpoint runs in a worker thread with no event loop


@app.post("/corrigenda/check")
async def corrigenda_check_now():
    """Run the daily corrigenda job now (demo button / ops). TinyFish Search costs no credits."""
    return await scheduler.daily_corrigenda()


@app.get("/matches/{match_id}/alert/preview")
def alert_preview(match_id: int):
    """The alert text for this match, without sending it."""
    text = preview_match(match_id)
    if text is None:
        raise HTTPException(404, "match not found")
    return {"preview": text}


@app.get("/alerts/status")
def alerts_status():
    """Which alert channels are configured (no secrets)."""
    return channel_status()


@app.post("/matches/{match_id}/alert")
async def send_alert(match_id: int):
    """Send this match by WhatsApp/email now (demo button). Unconfigured channels report "not_configured";
    the message preview is always returned."""
    res = await alert_match(match_id)
    if res is None:
        raise HTTPException(404, "match not found")
    return res


@app.get("/demo", include_in_schema=False)
def demo_page():
    """Single-page demo console (stopgap until the Next.js dashboard in web/)."""
    return FileResponse(Path(__file__).parent / "static" / "demo.html", media_type="text/html")
