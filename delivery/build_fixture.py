"""Build demo fixtures with real bid documents and parses (PLAN.md §3.7, H10–16 "Record fixtures").

TinyFish Fetch can't reach GeM bid PDFs (PLAN.md §1), so documents saved from a browser are attached
to a recorded run here. Three steps:

    python -m agents.cli gem "storage rack" --record              # 1. live agent run -> fixture (bids + steps)
    python -m delivery.build_fixture attach gem "storage rack" --docs ~/Downloads/gem_bids --parse
                                                                    # 2. PDFs -> text (+ LLM parse) into it
    python -m delivery.build_fixture check gem "storage rack"      # 3. validate before the demo

When --record already fetched the documents (agents/ downloads GeM PDFs directly), skip step 2 and run
    python -m delivery.build_fixture parse gem "storage rack"      # parse every recorded document

A document matches a bid when its file name (without extension) is the last part of the bid's doc_url
(GeM: showbidDocument/9988944 -> 9988944.pdf) or the bid number with "/" as "_" (GEM_2026_B_8120154.pdf).
"""
import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from agents.client import fixture_path
from agents.schemas import IST, BidListing
from api.clock import newest_recording, parse_demo_now
from api.documents import to_text
from api.eligibility import Eligibility, parse_eligibility
from api.llm import LLMError

DOC_EXTS = (".pdf", ".txt", ".md")


def _keys(bid: dict) -> list[str]:
    keys = []
    if bid.get("doc_url"):
        keys.append(bid["doc_url"].rstrip("/").rsplit("/", 1)[-1])
    keys.append(re.sub(r"[^A-Za-z0-9]+", "_", bid["bid_no"]).strip("_"))
    return [k.lower() for k in keys if k]


def find_documents(bids: list[dict], folder: Path) -> dict[str, Path]:
    """{doc_url: file} for every bid whose document is in `folder`."""
    files = {p.stem.lower(): p for p in folder.iterdir() if p.suffix.lower() in DOC_EXTS}
    out = {}
    for b in bids:
        url = b.get("doc_url") or b.get("source_url")
        for k in _keys(b):
            if k in files and url:
                out[url] = files[k]
                break
    return out


async def attach(fx: dict, folder: Path, parse: bool, log=print) -> dict:
    found = find_documents(fx.get("result", []), folder)
    fx.setdefault("docs", {})
    fx.setdefault("eligibility", {})
    for url, path in found.items():
        text = to_text(path.read_bytes())
        if not text.strip():
            log(f"  skip {path.name}: no text (scanned PDF? OCR is not built)")
            continue
        fx["docs"][url] = text
        log(f"  {path.name}: {len(text):,} chars")
        if parse:
            try:
                fx["eligibility"][url] = await parse_eligibility(text)
                log("    parsed eligibility")
            except LLMError as e:
                log(f"    parse failed: {e}")
    missing = [b["bid_no"] for b in fx.get("result", []) if (b.get("doc_url") or b.get("source_url")) not in fx["docs"]]
    if missing:
        log(f"  no document for {len(missing)} bid(s): {', '.join(missing)}")
    return fx


def demo_clock(fx: dict) -> datetime:
    """The "now" a fallback demo runs at, same rule as api/clock.py: DEMO_NOW, else the newest recorded_at
    of all fixtures (falling back to this fixture's own)."""
    raw = os.getenv("DEMO_NOW", "").strip()
    if raw:
        return parse_demo_now(raw)
    newest = newest_recording()
    if newest:
        return newest
    return parse_demo_now(fx["recorded_at"]) if fx.get("recorded_at") else datetime.now(IST)


async def parse_recorded(fx: dict, log=print) -> dict:
    """Parse every recorded document that has no recorded parse yet."""
    fx.setdefault("eligibility", {})
    for url, text in (fx.get("docs") or {}).items():
        if url in fx["eligibility"] or not text.strip():
            continue
        try:
            fx["eligibility"][url] = await parse_eligibility(text)
            log(f"  parsed {url}")
        except LLMError as e:
            log(f"  parse failed for {url}: {e}")
    return fx


def check(fx: dict, now: datetime | None = None) -> list[str]:
    """Problems that would hurt a fallback demo. Empty list = good to go."""
    now = now or demo_clock(fx)
    if fx.get("blocked"):  # a recorded captcha/blocked run replays as an error card with the portal link
        return [] if fx.get("steps") else ["blocked run with no agent steps: the card will look empty"]
    problems = []
    bids = []
    for raw in fx.get("result", []):
        try:
            bids.append(BidListing.model_validate(raw))
        except ValidationError as e:
            problems.append(f"invalid bid {raw.get('bid_no')}: {e.errors()[0]['msg']}")
    if not bids:
        problems.append("no bids recorded")
    open_bids = [b for b in bids if b.end_date > now]
    if bids and not open_bids:
        problems.append("every bid has closed: all verdicts will be NOT_ELIGIBLE (re-record)")
    if not fx.get("steps"):
        problems.append("no agent steps recorded: the live panel will look empty")
    docs, els = fx.get("docs") or {}, fx.get("eligibility") or {}
    for b in open_bids:
        url = b.doc_url
        if not url:  # the portal gives no readable document link (CPPP/Haryana session links): CHECK_DOCS
            continue
        if url not in docs:
            problems.append(f"{b.bid_no}: no document text")
        if url not in els:
            problems.append(f"{b.bid_no}: no recorded parse (fallback mode would need the LLM)")
    for url, el in els.items():
        try:
            Eligibility.model_validate(el)
        except ValidationError as e:
            problems.append(f"recorded parse for {url} is invalid: {e.errors()[0]['msg']}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m delivery.build_fixture")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("attach", help="attach saved bid documents (and parses) to a recorded fixture")
    a.add_argument("portal")
    a.add_argument("category")
    a.add_argument("--docs", required=True, type=Path, help="folder of saved bid PDFs / .txt files")
    a.add_argument("--parse", action="store_true", help="also run the eligibility parser (needs GROQ_API_KEY)")
    pr = sub.add_parser("parse", help="parse the documents a --record run already fetched")
    pr.add_argument("portal")
    pr.add_argument("category")
    c = sub.add_parser("check", help="validate a fixture for the fallback demo")
    c.add_argument("portal")
    c.add_argument("category")
    args = ap.parse_args(argv)

    path = fixture_path(args.portal, args.category)
    if not path.exists():
        print(f"no fixture at {path}. Record one first: python -m agents.cli {args.portal} \"{args.category}\" --record")
        return 2
    fx = json.loads(path.read_text())
    if args.cmd == "attach":
        if not args.docs.is_dir():
            print(f"not a folder: {args.docs}")
            return 2
        asyncio.run(attach(fx, args.docs, args.parse))
        path.write_text(json.dumps(fx, indent=2, ensure_ascii=False))
        print(f"saved {path}")
    if args.cmd == "parse":
        asyncio.run(parse_recorded(fx))
        path.write_text(json.dumps(fx, indent=2, ensure_ascii=False))
        print(f"saved {path}")
    print(f"  demo clock: {demo_clock(fx).isoformat()} ({'DEMO_NOW' if os.getenv('DEMO_NOW') else 'newest fixture recorded_at'})")
    problems = check(fx)
    for p in problems:
        print(f"  ⚠ {p}")
    print("fixture OK for the demo" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
