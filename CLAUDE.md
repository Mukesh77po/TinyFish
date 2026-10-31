# TenderHawk — project context

AI web agents that find the Indian government tenders a small business can actually win, and tell it why.
Built at **HackIIITD 2026** (24h in-person final at IIITD) by team **L.C Hard, JIIT Noida**.
**TinyFish API integration is mandatory** and must be the core of the product, not a bolt-on.

## Problem
- GeM procured ~₹5 lakh Cr in FY 2025–26; 25% of central procurement is reserved for MSEs by policy; 11 lakh+ MSEs are on GeM.
- Tenders are scattered: GeM, CPPP, IREPS, defence, ~30 state e-procurement portals, each with its own UI, filters, captchas.
- Eligibility (turnover, past experience, EMD, certifications) is buried in long bid PDFs.
- Hard deadlines; corrigenda (extensions, changed terms) get posted quietly.
- Owners check portals at night or pay consultants ₹5–20k/month.

## Solution (4 steps)
1. **Profile once** — products, HSN codes, annual turnover, certifications (MSE/Udyam, Startup India, ISO), states served.
2. **Agents sweep portals** — TinyFish Agent API opens each portal, filters, paginates, returns bids as JSON.
3. **Read & match** — Fetch API pulls bid documents as text; LLM extracts eligibility into structured JSON with the source clause; rules check hard criteria; keyword overlap ranks product fit.
4. **Alert & act** — WhatsApp/email: tender, value, deadline, verdict, reasons, document checklist, link to source clause.

Verdicts: `ELIGIBLE` (green) / `CHECK_DOCS` (amber) / `NOT_ELIGIBLE` with reason e.g. "Turnover short" (red).

Differentiators: reads eligibility not keywords; one profile across every portal; every verdict shows the exact clause.

## Users & pricing (pitch only, don't build billing)
- Primary: MSMEs & startups. Channel: CA firms & tender consultants (multi-client). Ecosystem: incubators, MSME associations.
- Free (1 category, weekly) / Pro ₹999/mo (all categories, daily) / Consultant ₹4,999/mo (25 clients).

## Architecture
```
Sources (GeM, CPPP, Haryana e-proc)
  -> TinyFish layer (Agent: navigate+extract | Fetch: bid docs->text | Search: corrigenda)
  -> Processing (Pydantic validate + dedupe on bid_no | Groq eligibility parser, cached by doc_url | keyword-overlap fit)
  -> Store (Postgres: tenders, profiles, matches)
  -> Serve (Matcher: rules + rank | FastAPI: REST + SSE)
  -> Users (Next.js dashboard with live agent panel | Twilio WhatsApp + email alerts)
```
**Invariant: TinyFish is the only component that navigates portals; bid PDFs it finds are downloaded via an Indian connection. Both happen only in `agents/`; no other module downloads anything. Everything downstream works on validated JSON.**

## TinyFish usage
- **Agent API** — core crawler, goal-based run per portal × category, `/run-async` + `/run-sse` (stream steps to UI). Billed: use only on listing sweeps, never per user.
- **Fetch API** (`api.fetch.tinyfish.ai`) — once per new bid, renders page/docs to clean text for the LLM. No credits.
- **Search API** (`api.search.tinyfish.ai`) — daily per active bid: corrigenda, deadline extensions, buyer context. No credits.
- **Browser API** — phase 2 only (bid-status tracking). Do not build now.

```python
from tinyfish import TinyFish
client = TinyFish()  # reads TINYFISH_API_KEY
run = client.agent.run(
    url="https://bidplus.gem.gov.in/all-bids",
    goal="Search bids for 'steel rack'. Keep only bids closing after today. "
         "Return bid_no, item, ministry, quantity, end_date, doc_url as JSON.")
```
Check the installed SDK for exact method names/signatures before assuming; adapt the wrapper, not callers.

## Hackathon scope (24h) — decided, don't expand
- Portals: **GeM, CPPP, Haryana e-proc** only.
- Scheduler: FastAPI background tasks / APScheduler + Redis pub/sub for SSE. **No Celery** (mention as scale path only).
- WhatsApp: **Twilio sandbox**, not Meta Cloud API. Twilio trial accounts prefix outgoing SMS with "Sent from your Twilio trial account -"; whether the WhatsApp sandbox does too isn't confirmed, so check the first real send (the message still leads with the verdict either way). The stage phone must have sent the sandbox join message within 24 h.
- Ranking: keyword overlap between the profile's products/keywords and the tender title/item (no embedding key; the pgvector path in `api/embeddings.py` stays off).
- **FALLBACK_MODE**: recorded real agent runs in `delivery/fixtures/*.json` (blocked runs too); deadlines then use a frozen clock (`DEMO_NOW`, else the newest fixture's `recorded_at`; `api/clock.py`); when `FALLBACK_MODE=true`, sweeps replay fixtures (still emitting SSE steps with small delays) so the demo survives bad wifi/portal downtime.
- Captcha/blocked portals: skip and surface a direct link. **Never bypass captchas.** Read-only: never submit bids.

## Stack
Python 3.11+, FastAPI, SQLAlchemy 2 + Alembic, psycopg, Pydantic v2, Redis, PostgreSQL 16 + pgvector, TinyFish SDK, Groq free tier (`openai/gpt-oss-120b` eligibility parser via strict JSON-schema output; `openai/gpt-oss-20b` light tasks; no Anthropic key, so Claude is not used), keyword-overlap ranking (no OpenAI key), PyMuPDF (+ OCR fallback), Next.js + Tailwind, Twilio, Docker Compose.

## Repo layout & ownership
```
agents/     TinyFish client wrapper, portal goals, schemas, SSE step events   (Siddhant — lead)
api/        FastAPI app, models, migrations, eligibility parser, matcher      (Harsh)
web/        Next.js dashboard: profile form, live agents panel, matches, detail (Aditya)
delivery/   Twilio/email alerts, seed profiles, fixtures, fallback mode, docker (Vandan)
tests/      pytest suite (no API keys needed); web/ has its own vitest suite
```
Current status and the pre-demo checklist live in `PLAN.md` §9. Before a demo: `python -m delivery.seed --reset`, then `python scripts/preflight.py` (must print READY).

## Core data model (starting point)
- `Tender`: id, portal, bid_no (unique with portal), title, item, ministry/buyer, quantity, est_value, end_date, doc_url, doc_text, doc_source, eligibility (JSONB), eligibility_source, corrigenda (JSONB), created_at, updated_at
- `Eligibility` JSON: `min_turnover`, `past_experience_years`, `emd_amount`, `emd_exemption_for_mse`, `required_certifications[]`, `states[]`, each criterion with `source_clause` text
- `Profile`: id, name, phone, products[], hsn_codes[], annual_turnover, years_in_business, certifications[], states_served[]
- `Match`: profile_id, tender_id, verdict, reasons[], missing_docs[], fit_score, alerted_at

## Demo (3 min) — everything serves this
1. Create a business profile (persona: **Ramesh**, 25-person steel fabrication unit, Faridabad, Udyam + GeM registered).
2. Hit **"Sweep now"** → live agents panel shows GeM / CPPP / Haryana / Search-corrigenda runs with step counts.
3. Open a match → verdict + highlighted source clause.
4. WhatsApp alert lands on stage.
Example match: "Supply of steel storage racks · MoD · ₹18.5 L · closes 28 Oct · Eligible: turnover met, MSE EMD exemption applies · Check: needs 3 years past-supply proof."

## Timeline & checkpoints (merge to main at each)
- H0–4: skeleton, TinyFish goals for 3 portals, schemas, first live GeM run saved to fixtures
- H4–10: Postgres upsert/dedupe, /sweep endpoint, Fetch for docs, SSE streaming, profile form
- H10–16: LLM eligibility extraction, matcher, ranking, Search corrigenda, **fixtures recorded by H12**
- H16–21: WhatsApp alert, match detail UI, error states → tag `v0.1-demo`
- H21–24: **fix-only freeze**, README, rehearse live + fallback

## Git rules
- `main` always demo-able. Branches: `feat/agents`, `feat/backend`, `feat/web`, `feat/delivery`.
- Small commits every 30–60 min, conventional commits: `feat(scope):`, `fix(scope):`, `chore:`, `docs:`. Scopes: agents, api, web, delivery.
- One logical change per commit. Never commit `.env` or secrets.
- Don't push unless asked.

## How to work in this repo
- Keep it simple and demo-first; no premature abstraction, no features outside scope.
- Validate every agent output with Pydantic; one retry on validation failure, then log and skip.
- Config from env vars only (see `.env.example`).
- When finishing a task: run it, show it works, then commit with the message given (or propose one).
