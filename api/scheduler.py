"""Daily corrigenda check for every open bid, then re-match every profile (APScheduler, no Celery)."""
import asyncio
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from agents.schemas import IST
from api.corrigenda import check_corrigenda
from api.db import SessionLocal
from api.matching import rematch
from api.models import Profile

log = logging.getLogger("api.scheduler")
SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "true").lower() in ("1", "true", "yes")
CORRIGENDA_HOUR = int(os.getenv("CORRIGENDA_HOUR", "7"))  # IST

_sched: AsyncIOScheduler | None = None


def _profile_ids() -> list[int]:
    with SessionLocal() as db:
        return list(db.scalars(select(Profile.id)))


async def daily_corrigenda() -> dict:
    res = await check_corrigenda()
    profile_ids = await asyncio.to_thread(_profile_ids)
    for pid in profile_ids:
        await rematch(pid)
    log.info("daily corrigenda: %s; re-matched %d profiles", res, len(profile_ids))
    return res


def start() -> None:
    global _sched
    if not SCHEDULER_ENABLED or _sched:
        return
    _sched = AsyncIOScheduler(timezone=IST)
    _sched.add_job(daily_corrigenda, CronTrigger(hour=CORRIGENDA_HOUR, minute=0, timezone=IST),
                   id="daily_corrigenda", max_instances=1, coalesce=True, misfire_grace_time=3600)
    _sched.start()
    log.info("scheduler started: corrigenda daily at %02d:00 IST", CORRIGENDA_HOUR)


def stop() -> None:
    global _sched
    if _sched:
        _sched.shutdown(wait=False)
        _sched = None


def next_run() -> str | None:
    job = _sched.get_job("daily_corrigenda") if _sched else None
    return job.next_run_time.isoformat() if job and job.next_run_time else None
