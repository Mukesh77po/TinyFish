"""seed --reset leaves a clean demo: no tenders, matches or sweep logs; Ramesh reseeded. Needs Postgres + Redis."""
from datetime import datetime, timedelta

import pytest
import redis
from sqlalchemy import select, text

from agents.schemas import IST
from api.config import REDIS_URL
from api.db import SessionLocal, engine


def _stack_up() -> bool:
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return bool(redis.Redis.from_url(REDIS_URL, socket_connect_timeout=1).ping())
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _stack_up(), reason="needs Postgres and Redis (docker compose up -d)")


def test_reset_wipes_demo_state_and_reseeds_ramesh(capsys):
    from api.models import Match, Profile, Tender
    from delivery import seed
    pid = seed.seed()
    with SessionLocal() as db:
        t = Tender(portal="gem", bid_no="GEM/TEST/RESET/1", title="Steel rack", end_date=datetime.now(IST) + timedelta(days=3),
                   source_url="https://bidplus.gem.gov.in/all-bids")
        db.add(t)
        db.flush()
        db.add(Match(profile_id=pid, tender_id=t.id, verdict="ELIGIBLE", reasons=[], missing_docs=[],
                     alerted_at=datetime.now(IST)))
        db.commit()
    r = redis.Redis.from_url(REDIS_URL)
    r.rpush("sweep:test-reset:log", "{}")

    seed.main(["--reset"])
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0].startswith("reset:") and out[-1].isdigit()
    with SessionLocal() as db:
        assert db.scalars(select(Tender)).first() is None and db.scalars(select(Match)).first() is None
        assert db.get(Profile, int(out[-1])).name == "Ramesh Steel Fabricators"
    assert not r.exists("sweep:test-reset:log")
