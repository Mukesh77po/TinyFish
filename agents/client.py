"""TinyFish wrapper. The only module in the repo that touches the live web (PLAN.md §3.2).

TinyFish navigates every portal. Bid PDFs it finds that TinyFish Fetch can't read (GeM: Fetch has no Indian
proxy) are downloaded directly over the Indian connection, here and nowhere else.
"""
import asyncio
import json
import logging
import os
import random
import re
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError
from tinyfish import AgentConfig, AsyncTinyFish, CompleteEvent, ProgressEvent, ProxyConfig, StartedEvent

from agents.goals import PORTALS, goal_for
from agents.schemas import AGENT_OUTPUT_SCHEMA, BidListing, Corrigendum, StepEvent
from api.documents import to_text

load_dotenv()
log = logging.getLogger("agents")

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "delivery" / "fixtures"

Emit = Callable[[StepEvent], None]

# Indian govt portals drop connections from non-Indian IPs (GeM: ERR_EMPTY_RESPONSE without this).
INDIA_PROXY = ProxyConfig(enabled=True, country_code="IN")

# Hard cap so a looping agent becomes a clean error card instead of a sweep that never ends (and keeps billing).
# Time only: a custom max_steps is rejected (HTTP 403 "not enabled for custom max steps", beta-only).
# The agent paces itself to this budget: at 300 s it gave up at step 20 of a GeM search ("276s/300s").
AGENT_LIMITS = AgentConfig(max_duration_seconds=420)
# TinyFish treats that as a soft limit (runs went 385 s and 512 s), so we enforce it ourselves: stop waiting
# and cancel the run, which otherwise keeps running (and billing) after we stop listening.
# Live GeM runs take 300-512 s through the Indian proxy (~17 s a step). At 300 s we threw away runs that
# finished at 319 s, after paying for them; 480 s keeps those and still cancels a runaway.
AGENT_TIMEOUT = int(os.getenv("AGENT_TIMEOUT", "480"))
# The plan runs 2 agents at once; a 3rd sits in TinyFish's queue (seen: 197 s) and that wait ate our timeout.
# Queue here instead, so the timeout only counts running time. Callers start GeM first (PORTALS order).
TINYFISH_CONCURRENCY = int(os.getenv("TINYFISH_CONCURRENCY", "2"))
_slots = asyncio.Semaphore(TINYFISH_CONCURRENCY)

# Direct downloads: only bid documents on the portals we sweep, only over HTTPS, only PDFs of sane size.
DOC_HOSTS = {urlparse(p["url"]).hostname for p in PORTALS.values()}
DOC_MAX_BYTES = 15_000_000

_client: AsyncTinyFish | None = None


def live_portals() -> set[str]:
    """Portals swept live when FALLBACK_MODE is off. LIVE_PORTALS=gem runs GeM through TinyFish and replays
    the recorded runs of the others (e.g. while their live goals still meet captchas). Default: all."""
    raw = os.getenv("LIVE_PORTALS", "").strip()
    return {p.strip() for p in raw.split(",") if p.strip()} if raw else set(PORTALS)


# The agent often reports "nothing relevant found" as blocked=true despite the goal. Only these are real blocks.
_REAL_BLOCK = re.compile(
    r"captcha|otp\b|log ?in|sign ?in|password|unreachable|err_|tunnel|timed? ?out|access denied|forbidden"
    r"|\b40[13]\b|\b50[234]\b|site (?:is )?down|not (?:load|reachabl|respond)|connection (?:refused|reset|failed)",
    re.I)


def is_real_block(reason: str | None) -> bool:
    return bool(reason and _REAL_BLOCK.search(reason))


def fallback_mode() -> bool:
    return os.getenv("FALLBACK_MODE", "false").lower() in ("1", "true", "yes")


def _tf() -> AsyncTinyFish:
    global _client
    if _client is None:
        _client = AsyncTinyFish()  # reads TINYFISH_API_KEY
    return _client


def fixture_path(portal: str, category: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_")
    return FIXTURES_DIR / f"{portal}_{slug}.json"


# GeM bid documents live at /showbidDocument/<digits>. Anything else the agent returns is a guess (seen:
# /showbiddata/GEM/2026/B/... -> 404) and would be a dead "Bid document" link on stage.
_GEM_DOC = re.compile(r"^https://bidplus\.gem\.gov\.in/showbidDocument/\d+$")


def session_bound(url: str) -> bool:
    """NIC GePNIC portals (CPPP, Haryana) link tenders through per-session URLs that expire in minutes
    ("Stale Session"): useless as a document to read and as an "Open on portal" link."""
    q = urlparse(url).query
    return "session=T" in q or "%24DirectLink" in q or "$DirectLink" in q


def to_listings(portal: str, raw_bids: list[dict]) -> list[BidListing]:
    """Validate raw agent rows. A bad row is logged and skipped, never fails the sweep."""
    base = PORTALS[portal]["url"]
    out: dict[str, BidListing] = {}
    for raw in raw_bids:
        row = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
        row = {k: v for k, v in row.items() if v not in ("", None)}
        if row.get("doc_url"):
            row["doc_url"] = urljoin(base, row["doc_url"])
            if session_bound(row["doc_url"]) or (portal == "gem" and not _GEM_DOC.match(row["doc_url"])):
                log.info("dropping unusable %s doc_url for %s: %s", portal, row.get("bid_no"), row["doc_url"])
                row.pop("doc_url")  # the stable bid list (base) is where the bid number can be found
        row.setdefault("source_url", row.get("doc_url") or base)
        try:
            bid = BidListing(portal=portal, **row)
        except ValidationError as e:
            log.warning("skip %s bid %r: %s", portal, raw.get("bid_no"), e.errors()[0]["msg"])
            continue
        out.setdefault(bid.bid_no, bid)
    return list(out.values())


async def run_agent(portal: str, category: str, on_step: Callable[[int, str], None]) -> dict:
    """One live agent run, retried once if the result is unusable.

    Returns {"run_id", "url", "goal", "steps", "result"} where result is the raw agent JSON.
    """
    if _slots.locked():
        on_step(0, f"Waiting for a free TinyFish agent ({TINYFISH_CONCURRENCY} run at a time)")
    async with _slots:
        return await _run_agent(portal, category, on_step)


async def _run_agent(portal: str, category: str, on_step: Callable[[int, str], None]) -> dict:
    url, goal = goal_for(portal, category)
    last_error = "no result"
    for attempt in (1, 2):
        steps: list[dict] = []
        run_id, result = None, None
        try:
            async with asyncio.timeout(AGENT_TIMEOUT):
                async with _tf().agent.stream(
                    url=url, goal=goal, output_schema=AGENT_OUTPUT_SCHEMA, proxy_config=INDIA_PROXY,
                    agent_config=AGENT_LIMITS,
                ) as stream:
                    async for ev in stream:
                        if isinstance(ev, StartedEvent):
                            run_id = ev.run_id
                        elif isinstance(ev, ProgressEvent):
                            steps.append({"step": len(steps) + 1, "message": ev.purpose})
                            on_step(len(steps), ev.purpose)
                        elif isinstance(ev, CompleteEvent):
                            if ev.status == "COMPLETED" and isinstance(ev.result_json, dict):
                                result = ev.result_json
                            else:
                                last_error = ev.error.message if ev.error else f"run {ev.status}"
        except TimeoutError:
            # No retry: a second run would take as long. The card shows the portal link instead.
            if run_id:
                await _cancel_run(run_id)
            raise RuntimeError(f"Agent still running after {AGENT_TIMEOUT} s ({len(steps)} steps); cancelled")
        if result is not None and (result.get("blocked") or isinstance(result.get("bids"), list)):
            return {"run_id": run_id, "url": url, "goal": goal, "steps": steps, "result": result}
        log.warning("%s run %s unusable (attempt %d): %s", portal, run_id, attempt, last_error)
    raise RuntimeError(f"{portal} agent failed: {last_error}")


async def _cancel_run(run_id: str) -> None:
    """The SDK has no agent-run cancel; the REST endpoint does it. Best effort: never raises."""
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.post(f"https://agent.tinyfish.ai/v1/runs/{run_id}/cancel",
                                headers={"X-API-Key": os.environ["TINYFISH_API_KEY"]})
        log.info("cancelled run %s: %s %s", run_id, r.status_code, r.text[:120])
    except Exception:
        log.exception("cancel failed for run %s", run_id)


def _short_reason(reason: str | None) -> str:
    """Agents explain a block at length; the card needs the first sentence."""
    first = re.split(r"(?<=[.!?])\s", (reason or "captcha").strip(), maxsplit=1)[0].rstrip(".")
    return first if len(first) <= 140 else first[:137] + "…"


async def _replay(portal: str, category: str, emit: Emit, sweep_id: str, labelled: bool = False) -> list[BidListing]:
    path = fixture_path(portal, category)
    if not path.exists():
        emit(StepEvent(sweep_id=sweep_id, agent=portal, type="error",
                       message=f"No recorded run for '{category}'", direct_url=PORTALS[portal]["url"]))
        return []
    fx = json.loads(path.read_text())
    when = str(fx.get("recorded_at", ""))[:10]
    note = f"Replaying the recorded run from {when}: " if labelled else ""
    emit(StepEvent(sweep_id=sweep_id, agent=portal, type="started", message=f"{note}Opening {fx['url']}"))
    for s in fx["steps"]:
        await asyncio.sleep(random.uniform(0.3, 0.8))
        emit(StepEvent(sweep_id=sweep_id, agent=portal, type="step", step=s["step"], message=s["message"]))
    if fx.get("blocked"):  # the recorded run hit a captcha: replay exactly that, with the portal link
        emit(StepEvent(sweep_id=sweep_id, agent=portal, type="error", step=len(fx["steps"]),
                       message=f"Blocked: {_short_reason(fx.get('blocked_reason'))}. Open on portal.",
                       direct_url=PORTALS[portal]["url"]))
        return []
    bids = [BidListing.model_validate(b) for b in fx["result"]]
    emit(StepEvent(sweep_id=sweep_id, agent=portal, type="result", step=len(fx["steps"]),
                   message=f"Found {len(bids)} bids", count=len(bids)))
    return bids


async def sweep_portal(portal: str, category: str, emit: Emit, sweep_id: str = "local") -> list[BidListing]:
    """Sweep one portal for one category, streaming StepEvents. Never raises; errors become events."""
    if fallback_mode():
        return await _replay(portal, category, emit, sweep_id)
    if portal not in live_portals():
        return await _replay(portal, category, emit, sweep_id, labelled=True)

    url = PORTALS[portal]["url"]
    emit(StepEvent(sweep_id=sweep_id, agent=portal, type="started", message=f"Opening {url}"))

    def on_step(n: int, msg: str) -> None:
        emit(StepEvent(sweep_id=sweep_id, agent=portal, type="step", step=n, message=msg))

    try:
        run = await run_agent(portal, category, on_step)
    except Exception as e:  # network, auth, run failure: surface a direct link instead
        log.exception("%s sweep failed", portal)
        emit(StepEvent(sweep_id=sweep_id, agent=portal, type="error", message=str(e), direct_url=url))
        return []

    result = run["result"]
    bids = to_listings(portal, result.get("bids") or [])
    reason = result.get("blocked_reason")
    if result.get("blocked") and not bids and is_real_block(reason):
        emit(StepEvent(sweep_id=sweep_id, agent=portal, type="error", step=len(run["steps"]),
                       message=f"Blocked: {_short_reason(reason)}. Open on portal.", direct_url=url))
        return []
    if result.get("blocked") and not bids:
        log.info("%s: agent said blocked but gave no access problem (%r): treating as no relevant bids", portal, reason)
    msg = f"Found {len(bids)} bids" if bids else "No relevant open bids on the first result pages"
    emit(StepEvent(sweep_id=sweep_id, agent=portal, type="result", step=len(run["steps"]),
                   message=msg, count=len(bids)))
    return bids


def _fixture_docs() -> dict[str, str]:
    docs: dict[str, str] = {}
    for p in FIXTURES_DIR.glob("*.json"):
        docs.update(json.loads(p.read_text()).get("docs", {}))
    return docs


async def _fetch(url: str) -> str:
    try:
        resp = await _tf().fetch.get_contents([url], format="markdown")
    except Exception:
        log.exception("fetch failed: %s", url)
        return ""
    if resp.errors or not resp.results:
        log.warning("fetch returned no text for %s: %s", url, resp.errors)
        return ""
    return to_text(resp.results[0].text or "")


async def _direct(url: str) -> str:
    """Last resort for a bid PDF on a swept portal. A TinyFish agent can't read these (the browser downloads
    the PDF instead of showing it: 20 steps, no text), so fetch the file itself over the Indian connection."""
    u = urlparse(url)
    if u.scheme != "https" or u.hostname not in DOC_HOSTS:
        return ""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
            r = await http.get(url)
    except httpx.HTTPError as e:
        log.warning("direct download failed for %s: %r", url, e)
        return ""
    if r.status_code != 200 or len(r.content) > DOC_MAX_BYTES or r.content[:5] != b"%PDF-":
        log.warning("direct download of %s: HTTP %s, %d bytes, not a usable PDF", url, r.status_code, len(r.content))
        return ""
    return to_text(r.content)


async def fetch_doc_text(url: str) -> tuple[str, str]:
    """Bid page/document -> (clean text, source). source: fetch | direct | fixture, or "" with no text."""
    if fallback_mode():
        text = _fixture_docs().get(url, "")
        return (text, "fixture") if text else ("", "")
    for source, get in (("fetch", _fetch), ("direct", _direct)):
        text = await get(url)
        if text.strip():
            log.info("doc text for %s: %d chars, source=%s", url, len(text), source)
            return text, source
    return "", ""


# What an actual corrigendum or extension notice says. The bare word is everywhere and proves nothing: portal
# menus ("Active Tenders | Corrigendum | Bid Awards"), GeM boilerplate ("ATC and Corrigendum if any"), lists of
# other tenders ("corrigendum tender for gas chromatograph"). Seen as false positives on real bids, 2026-10-25.
_NOTICE = re.compile(
    r"corrigendum\s*(?:no\.?|number|#)?\s*[-:]?\s*\d"
    r"|corrigendum\s+(?:issued|published|dated|regarding)"
    r"|(?:bid|tender|due|closing|submission|end|opening)\s+date\s+(?:has\s+been\s+|is\s+|was\s+)?(?:extended|revised|changed)"
    r"|extended\s+(?:to|till|until|up\s*to)\s+\d"
    r"|extension\s+of\s+(?:the\s+)?(?:bid|tender|due|closing|last|submission|end)(?:\s+\w+)?\s+date"
    r"|(?:addendum|amendment)\s*(?:no\.?)?\s*[-:]?\s*\d",
    re.I)
_NEAR = 250  # characters: the notice must be about this bid, not another one on the same page


def is_corrigendum_notice(text: str, bid_no: str) -> bool:
    low, key = text.lower(), bid_no.lower()
    for i in (m.start() for m in re.finditer(re.escape(key), low)):
        window = text[max(0, i - _NEAR): i + len(key) + _NEAR]
        if _NOTICE.search(window):
            return True
    return False


async def search_corrigenda(bid: BidListing) -> list[Corrigendum]:
    """Look for corrigenda / deadline extensions for a bid via TinyFish Search."""
    if fallback_mode():
        fx = fixture_path(bid.portal, "corrigenda")
        rows = json.loads(fx.read_text()).get(bid.bid_no, []) if fx.exists() else []
        return [Corrigendum.model_validate(r) for r in rows]
    try:
        resp = await _tf().search.query(f'"{bid.bid_no}" corrigendum OR extension', location="IN")
    except Exception:
        log.exception("search failed: %s", bid.bid_no)
        return []
    out = []
    for r in resp.results:
        text = f"{r.title} {r.snippet}"
        if is_corrigendum_notice(text, bid.bid_no):
            out.append(Corrigendum(bid_no=bid.bid_no, summary=r.snippet or r.title, source_url=r.url))
    return out
