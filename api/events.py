"""Sweep event bus on Redis (PLAN.md §3.3).

Each event is appended to a log list (so a late SSE client can replay) and published on
`sweep:{id}`. The publish payload is "<seq>|<json>", where seq is the log length after the push,
so a subscriber can skip events it already replayed from the log.
"""
import json
from collections.abc import AsyncIterator

import redis
import redis.asyncio as aioredis

from agents.schemas import StepEvent
from api.config import REDIS_URL

TTL = 3600
IDLE_LIMIT = 360  # seconds without an event before the stream gives up; agent runs are capped at 300 s
_r = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _channel(sweep_id: str) -> str:
    return f"sweep:{sweep_id}"


def _log(sweep_id: str) -> str:
    return f"sweep:{sweep_id}:log"


def _meta(sweep_id: str) -> str:
    return f"sweep:{sweep_id}:meta"


def register_sweep(sweep_id: str, profile_id: int) -> None:
    _r.set(_meta(sweep_id), json.dumps({"profile_id": profile_id}), ex=TTL)


def sweep_exists(sweep_id: str) -> bool:
    return bool(_r.exists(_meta(sweep_id)))


def publish(ev: StepEvent) -> None:
    """Sync on purpose: called from agents' emit callback, keeps events strictly ordered."""
    js = ev.model_dump_json()
    n = _r.rpush(_log(ev.sweep_id), js)
    _r.expire(_log(ev.sweep_id), TTL)
    _r.publish(_channel(ev.sweep_id), f"{n}|{js}")


def _is_final(js: str) -> bool:
    """all/done ends the stream unless documents are still being read; then all/settled does."""
    d = json.loads(js)
    if d.get("agent") != "all":
        return False
    return d.get("type") == "settled" or (d.get("type") == "done" and not d.get("pending"))


async def stream(sweep_id: str) -> AsyncIterator[str]:
    """SSE frames: replay the log, then follow live events until the final `all/done`."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    ps = r.pubsub()
    await ps.subscribe(_channel(sweep_id))  # subscribe before reading the log: no gap
    try:
        backlog = await r.lrange(_log(sweep_id), 0, -1)
        for js in backlog:
            yield f"data: {js}\n\n"
            if _is_final(js):
                return
        seen = len(backlog)
        idle = 0.0
        while True:
            msg = await ps.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if msg is None:
                idle += 15.0
                if idle >= IDLE_LIMIT:
                    lost = StepEvent(sweep_id=sweep_id, agent="all", type="done",
                                     message="Lost contact with this sweep. Start a new one.")
                    yield f"data: {lost.model_dump_json()}\n\n"
                    return
                yield ": keepalive\n\n"
                continue
            idle = 0.0
            n, js = msg["data"].split("|", 1)
            if int(n) <= seen:
                continue
            seen = int(n)
            yield f"data: {js}\n\n"
            if _is_final(js):
                return
    finally:
        await ps.unsubscribe()
        await ps.aclose()
        await r.aclose()
