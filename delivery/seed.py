"""Seed Ramesh's demo profile.

    python -m delivery.seed           # create/refresh Ramesh -> prints the profile id
    python -m delivery.seed --reset   # clean demo state first: tenders, matches (and their alert flags),
                                      # sweep event logs; other profiles are kept
"""
import argparse
import json
from pathlib import Path

import redis
from sqlalchemy import delete

from api.config import REDIS_URL
from api.db import SessionLocal
from api.models import Match, Profile, Tender

SEED = Path(__file__).parent / "seed" / "ramesh.json"


def reset() -> dict:
    """Wipe everything a sweep or a rehearsal leaves behind. Returns what was removed."""
    with SessionLocal() as db:
        matches = db.execute(delete(Match)).rowcount
        tenders = db.execute(delete(Tender)).rowcount
        db.commit()
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    keys = list(r.scan_iter("sweep:*"))
    if keys:
        r.delete(*keys)
    return {"tenders": tenders, "matches": matches, "sweep_keys": len(keys)}


def seed() -> int:
    data = json.loads(SEED.read_text())
    with SessionLocal() as db:
        # The dashboard's onboarding can save another "Ramesh"; refresh the oldest, never crash the reset.
        p = db.query(Profile).filter_by(name=data["name"]).order_by(Profile.id).first()
        if p is None:
            p = Profile(**data)
            db.add(p)
        else:
            for k, v in data.items():
                setattr(p, k, v)
            p.embedding = None  # re-embedded on the next match
        db.commit()
        return p.id


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m delivery.seed")
    ap.add_argument("--reset", action="store_true", help="wipe tenders, matches, alert flags and sweep logs first")
    args = ap.parse_args(argv)
    if args.reset:
        gone = reset()
        print(f"reset: {gone['tenders']} tenders, {gone['matches']} matches, {gone['sweep_keys']} sweep log keys removed")
    print(seed())


if __name__ == "__main__":
    main()
