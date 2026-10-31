"""One command before the demo: every check prints PASS / WARN / FAIL; exit 1 if anything FAILs.

    python scripts/preflight.py            # from the repo root, with the venv active

WEB_URL (default http://localhost:3000) is where the dashboard should be reachable; the API is
NEXT_PUBLIC_API_URL (default http://localhost:8000). Calls cost nothing: TinyFish wallet + one free
Search query, one Groq models listing (no tokens).
"""
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import httpx  # noqa: E402

import api.config  # noqa: E402,F401  (loads .env)
from agents.schemas import BidListing  # noqa: E402
from api.clock import parse_demo_now  # noqa: E402
from api.matcher import ProfileFacts, evaluate  # noqa: E402

API_URL = os.getenv("NEXT_PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
WEB_URL = os.getenv("WEB_URL", "http://localhost:3000").rstrip("/")
FIXTURES = ROOT / "delivery" / "fixtures"
REQUIRED_FIXTURES = ["gem_storage_rack"]           # the demo's green match lives here
OPTIONAL_FIXTURES = ["cppp_storage_rack", "haryana_storage_rack"]  # a blocked portal is a clean error card
MIN_WALLET_USD = 2.0                               # ~125 agent steps: a couple of live sweeps

results: list[tuple[str, str, str]] = []


def report(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"{status:4}  {name}" + (f": {detail}" if detail else ""), flush=True)


def check(name: str):
    """Decorator: a crashing check is a FAIL with its error, never a traceback."""
    def wrap(fn):
        def run():
            try:
                fn()
            except Exception as e:
                first = (str(e).strip().splitlines() or [""])[0]
                report("FAIL", name, f"{type(e).__name__}: {first}")
        return run
    return wrap


def env_flag(name: str) -> bool:
    return os.getenv(name, "false").lower() in ("1", "true", "yes")


@check("docker services")
def docker_services():
    out = subprocess.run(["docker", "compose", "ps", "--all", "--format", "json"], capture_output=True, text=True,
                         timeout=30)
    if out.returncode != 0:
        report("FAIL", "docker services", (out.stderr.strip().splitlines() or ["docker compose failed"])[-1]
               + " (start Docker Desktop; enable WSL integration for Ubuntu)")
        return
    rows = [json.loads(line) for line in out.stdout.splitlines() if line.strip().startswith("{")]
    if not rows and out.stdout.strip().startswith("["):
        rows = json.loads(out.stdout)
    by = {r.get("Service"): r for r in rows}
    for svc in ("db", "redis"):
        r = by.get(svc)
        if not r:
            report("FAIL", f"docker {svc}", "not running: docker compose up -d")
        elif r.get("State") != "running" or r.get("Health") not in ("healthy", ""):
            report("FAIL", f"docker {svc}", f"{r.get('State')} / {r.get('Health') or 'no healthcheck'}")
        else:
            report("PASS", f"docker {svc}", "running, healthy")


@check("alembic")
def alembic_head():
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine
    heads = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_heads()
    if len(heads) != 1:
        report("FAIL", "alembic", f"{len(heads)} heads {heads}: merge them")
        return
    eng = create_engine(os.environ.get("DATABASE_URL", api.config.DATABASE_URL), connect_args={"connect_timeout": 3})
    with eng.connect() as c:
        current = MigrationContext.configure(c).get_current_heads()
    if tuple(current) == tuple(heads):
        report("PASS", "alembic", f"at head {heads[0]}")
    else:
        report("FAIL", "alembic", f"db at {current or 'nothing'}, head is {heads[0]}: alembic upgrade head")


health: dict = {}


@check("API /health")
def api_health():
    r = httpx.get(API_URL + "/health", timeout=5)
    r.raise_for_status()
    health.update(r.json())
    bad = [k for k in ("db", "redis") if not health.get(k)]
    if bad:
        report("FAIL", "API /health", f"{API_URL} up but {', '.join(bad)} down")
    else:
        report("PASS", "API /health", f"{API_URL}: db ✓ redis ✓, fallback_mode={health.get('fallback_mode')}, "
                                      f"clock {health.get('now')} ({health.get('clock')})")


@check("web + CORS")
def web_and_cors():
    origin = f"{urlparse(WEB_URL).scheme}://{urlparse(WEB_URL).netloc}"
    try:
        w = httpx.get(WEB_URL, timeout=10)
        report("PASS" if w.status_code == 200 else "FAIL", "web", f"{WEB_URL} → HTTP {w.status_code}")
    except httpx.HTTPError as e:
        report("FAIL", "web", f"{WEB_URL} unreachable ({type(e).__name__}): cd web && npm run build && npm start")
    pre = httpx.options(API_URL + "/profiles", timeout=5, headers={
        "Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    allowed = pre.headers.get("access-control-allow-origin")
    if allowed in ("*", origin):
        report("PASS", "CORS", f"API allows {origin}")
    else:
        report("FAIL", "CORS", f"API answered {allowed!r} for origin {origin}: set WEB_ORIGINS")


@check("fallback + demo clock")
def fallback_clock():
    fb, demo = env_flag("FALLBACK_MODE"), os.getenv("DEMO_NOW", "").strip()
    if demo:
        try:
            parse_demo_now(demo)
        except ValueError:
            report("FAIL", "DEMO_NOW", f"{demo!r} is not an ISO datetime (e.g. 2026-10-25T11:00:00)")
            return
    note = ("live sweeps (billed)" if not fb else
            f"replay, clock frozen at {demo}" if demo else "replay, clock frozen at the newest fixture's recorded_at")
    report("PASS", "FALLBACK_MODE / DEMO_NOW", f"FALLBACK_MODE={fb}, DEMO_NOW={demo or '(unset)'}: {note}")
    if health and health.get("fallback_mode") != fb:
        report("FAIL", "FALLBACK_MODE", f".env says {fb} but the running API says {health.get('fallback_mode')}: restart it")


def _fixture_files() -> list[Path]:
    return sorted(p for p in FIXTURES.glob("*.json") if not p.stem.endswith("_corrigenda"))


@check("fixtures")
def fixtures():
    from delivery.build_fixture import check as fixture_check
    present = {p.stem for p in _fixture_files()}
    for name in REQUIRED_FIXTURES + OPTIONAL_FIXTURES:
        path = FIXTURES / f"{name}.json"
        if name not in present:
            report("FAIL" if name in REQUIRED_FIXTURES else "WARN", f"fixture {name}",
                   "missing" + ("" if name in REQUIRED_FIXTURES else ": its card shows an error with the portal link"))
            continue
        problems = fixture_check(json.loads(path.read_text()))
        report("PASS" if not problems else "FAIL", f"fixture {name}", "fixture OK" if not problems else "; ".join(problems))


@check("verdict mix")
def verdict_mix():
    """Ramesh against every recorded bid, on the demo clock, without the DB: is every colour on screen?"""
    from delivery.build_fixture import demo_clock
    p = json.loads((ROOT / "delivery" / "seed" / "ramesh.json").read_text())
    facts = ProfileFacts(p["annual_turnover"], p["years_in_business"], p["certifications"], p["states_served"])
    seen: dict[str, list[str]] = {}
    for path in _fixture_files():
        fx = json.loads(path.read_text())
        now = demo_clock(fx)  # the fallback demo's frozen clock (api/clock.py)
        for raw in fx.get("result", []):
            b = BidListing.model_validate(raw)
            el = (fx.get("eligibility") or {}).get(b.doc_url or b.source_url)
            seen.setdefault(evaluate(facts, b.end_date, el, now=now).verdict, []).append(b.bid_no)
    missing = [v for v in ("ELIGIBLE", "CHECK_DOCS", "NOT_ELIGIBLE") if v not in seen]
    detail = ", ".join(f"{v} {len(ids)}" for v, ids in sorted(seen.items())) or "no recorded bids"
    report("PASS" if not missing else "WARN", "verdict mix", detail + (f"; missing {', '.join(missing)}" if missing else ""))


@check("Twilio")
def twilio():
    missing = [k for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM", "ALERT_WHATSAPP_TO")
               if not os.getenv(k)]
    if missing:
        hint = " (sandbox sender: TWILIO_WHATSAPP_FROM=whatsapp:+14155238886)" if "TWILIO_WHATSAPP_FROM" in missing else ""
        report("FAIL", "Twilio WhatsApp", f"{', '.join(missing)} not set{hint}")
        return
    report("PASS", "Twilio WhatsApp", f"creds set, alerts go to {os.getenv('ALERT_WHATSAPP_TO')} "
                                      "(the phone must have sent the sandbox join message within 24 h)")


@check("TinyFish")
def tinyfish():
    from tinyfish import TinyFish
    if not os.getenv("TINYFISH_API_KEY"):
        report("FAIL", "TinyFish", "TINYFISH_API_KEY not set")
        return
    tf = TinyFish()
    tf.search.query("GeM storage rack tender", location="IN")  # free; proves the key works
    try:
        w = tf.wallet.get()
        bal = float(w.available_balance)
        step = next((float(m.unit_amount) for m in w.rates.meters if m.label == "TinyFish Agent"), 0.016)
        report("PASS" if bal >= MIN_WALLET_USD else "WARN", "TinyFish",
               f"key valid, wallet {w.currency} {bal:.2f} ≈ {int(bal / step)} agent steps (a GeM sweep is ~30)")
    except Exception as e:
        report("WARN", "TinyFish", f"key valid; couldn't read the wallet ({type(e).__name__}): check credits manually")


@check("Groq")
def groq():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        report("FAIL", "Groq", "GROQ_API_KEY not set")
        return
    from api import llm
    r = httpx.get(llm.GROQ_BASE_URL + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=10)
    if r.status_code == 401:
        report("FAIL", "Groq", "GROQ_API_KEY rejected")
        return
    r.raise_for_status()
    ids = {m["id"] for m in r.json().get("data", [])}
    missing = [m for m in (llm.LLM_MODEL, llm.LLM_MODEL_FAST) if m not in ids]
    report("PASS" if not missing else "FAIL", "Groq", "key valid, models available" if not missing
           else f"key valid but {', '.join(missing)} not offered")


@check("ports")
def ports():
    """Each port is either serving our stack or free; anything else is a conflict."""
    expect = {int(os.getenv("API_PORT", "8000")): "api", int(os.getenv("WEB_PORT", "3000")): "web",
              int(os.getenv("POSTGRES_PORT", "5432")): "db", int(os.getenv("REDIS_PORT", "6379")): "redis"}
    ours = {"api": bool(health), "web": any(n == "web" and s == "PASS" for s, n, _ in results),
            "db": any(n == "docker db" and s == "PASS" for s, n, _ in results),
            "redis": any(n == "docker redis" and s == "PASS" for s, n, _ in results)}
    for port, svc in expect.items():
        with socket.socket() as s:
            s.settimeout(1)
            busy = s.connect_ex(("127.0.0.1", port)) == 0
        if not busy:
            report("WARN", f"port {port}", f"free, but {svc} should be listening here")
        elif ours[svc]:
            report("PASS", f"port {port}", f"{svc}")
        else:
            report("FAIL", f"port {port}", f"in use, but not by a healthy TenderHawk {svc}")


def main() -> int:
    for fn in (docker_services, alembic_head, api_health, web_and_cors, fallback_clock, fixtures, verdict_mix,
               twilio, tinyfish, groq, ports):
        fn()
    fails = sum(s == "FAIL" for s, _, _ in results)
    warns = sum(s == "WARN" for s, _, _ in results)
    print(f"\n{'READY' if not fails else 'NOT READY'}: {fails} fail, {warns} warn, "
          f"{sum(s == 'PASS' for s, _, _ in results)} pass")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
