"""The one "now" every deadline comparison uses (matcher, corrigenda, auto-alert, fixture check, web via /health).

Live: the real time in IST. FALLBACK_MODE=true: a frozen demo clock, so recorded fixtures never expire:
  - DEMO_NOW (ISO datetime; no offset means IST), else
  - the newest fixture's recorded_at, so every replayed deadline reads exactly as it did when recorded.
Event timestamps (alerted_at, SSE ts, recorded_at) stay on the real clock.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from agents.schemas import IST
from api.config import fallback_mode

log = logging.getLogger("api.clock")
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "delivery" / "fixtures"


def as_ist(dt: datetime) -> datetime:
    """Any datetime -> IST-aware. Naive means IST (portal times are IST), never the server's local zone."""
    return dt.replace(tzinfo=IST) if dt.tzinfo is None else dt.astimezone(IST)


def parse_demo_now(value: str) -> datetime:
    return as_ist(datetime.fromisoformat(value.strip()))


def newest_recording() -> datetime | None:
    newest = None
    for p in FIXTURES_DIR.glob("*.json"):
        try:
            rec = json.loads(p.read_text()).get("recorded_at")
            dt = parse_demo_now(rec) if rec else None
        except (OSError, ValueError, AttributeError):
            continue
        if dt and (newest is None or dt > newest):
            newest = dt
    return newest


def demo_now() -> tuple[datetime | None, str]:
    """(frozen time, where it came from) in fallback mode; (None, "real") otherwise."""
    if not fallback_mode():
        return None, "real"
    raw = os.getenv("DEMO_NOW", "").strip()
    if raw:
        try:
            return parse_demo_now(raw), "DEMO_NOW"
        except ValueError:
            log.warning("DEMO_NOW=%r is not an ISO datetime; ignoring it", raw)
    rec = newest_recording()
    return (rec, "fixture recorded_at") if rec else (None, "real")


def now_ist() -> datetime:
    frozen, _ = demo_now()
    return frozen or datetime.now(IST)
