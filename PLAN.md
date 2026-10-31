# TenderHawk — Build Plan (HackIIITD 2026)

> One page everyone works from. Context, scope and rules live in [`CLAUDE.md`](CLAUDE.md); this file says **who builds what, in what order, against which interfaces.**
> If you need to change an interface below, tell the owner and the people consuming it, then update this file.

---

## 0. Goal: the 3-minute demo

Everything we build serves this script. If a task doesn't help this demo, it waits.

1. Create **Ramesh's** profile: steel fabrication, 25 people, Faridabad, Udyam + GeM registered.
2. Click **Sweep now**. The live panel shows the GeM / CPPP / Haryana / corrigenda agents with step counts ticking.
3. Open a match to see the verdict, its reasons and the **highlighted source clause**.
4. A WhatsApp alert lands on a phone on stage.

**Must work offline:** `FALLBACK_MODE=true` replays recorded runs with the same UI and SSE events, on a frozen demo clock (`DEMO_NOW`, else the newest fixture's `recorded_at`; `api/clock.py`) so recorded deadlines never expire.

---

## 1. What we already know (sanity check, H0)

| Fact | Impact |
|---|---|
| TinyFish SDK `tinyfish==0.11.0`: `client.agent.run(url=, goal=, output_schema=)`, also `.stream()` and `.queue()` | Use `stream` for the live panel, `output_schema` to force our field names |
| One GeM run (first 3 bids) took **20 steps, ~150 s** | A live 3-portal sweep is too slow for the stage, so **fixtures are mandatory**, and live runs go in the background |
| The agent chose its own key names (`bid_number` instead of `bid_no`) | Always pass `output_schema`; validate with Pydantic |
| GeM date format: `24-10-2026 2:00 PM IST` | Shared date parser in `agents/schemas.py` |
| `.env` is gitignored, and the key loads via `python-dotenv` | Copy `.env.example` → `.env` and fill it in locally |
| GeM drops connections from non-Indian IPs (agent saw `ERR_EMPTY_RESPONSE`, "site down") | Agent runs use `ProxyConfig(country_code="IN")` |
| `output_schema` rejects `description` keys (HTTP 400) | Field hints live in the goal text (`agents/goals.py`) |
| GeM's search for "steel rack" returns no rack bids; buyers write "storage rack" / "Metal Shelving Racks" | Keyword choice decides whether a live sweep finds anything (see §7); goals match on items/title, never on buyer names |
| Fetch API → GeM bid docs gives `proxy_error` (Fetch has no proxy option). A TinyFish agent can't read them either (run `b4065139`, 2026-10-24: 20 steps, 110 s, no text; the browser downloads the PDF) | `agents.fetch_doc_text` falls back to a direct PDF download over the Indian connection (`source=direct`) |
| Custom `max_steps` is rejected: HTTP 403 "Your account is not enabled for custom max steps yet". `max_duration_seconds` is accepted but soft (runs took 352 s, 471 s, 512 s) | `AGENT_LIMITS` caps time only (300 s); `agents/` enforces it at `AGENT_TIMEOUT` (300 s): stops waiting and cancels the run (`POST /v1/runs/{id}/cancel`; the SDK has no cancel) → error card with the portal link |
| One agent run with tooltip/detail clicks ran 10+ min | Runs capped at 300 s (`AGENT_LIMITS` + `AGENT_TIMEOUT`, cancelled on TinyFish); keep goals cheap |
| The plan runs 2 agents at once: a 3rd waited 197 s in TinyFish's queue and that wait counted against our 330 s timeout, so a GeM run that found 6 bids (385 s) was thrown away | `agents/` queues runs locally (`TINYFISH_CONCURRENCY`, default 2; GeM first), so the timeout only counts running time |

---

## 2. Owners

| Area | Owner | Folder | Branch |
|---|---|---|---|
| TinyFish agents, schemas, SSE step events | **Siddhant** (lead) | `agents/` | `feat/agents` |
| FastAPI, DB models/migrations, eligibility parser, matcher | **Harsh** | `api/` | `feat/backend` |
| Next.js dashboard | **Aditya** | `web/` | `feat/web` |
| Alerts, seed data, fixtures, fallback, Docker | **Vandan** | `delivery/` | `feat/delivery` |

---

## 3. Interfaces (agree these first; build against them in parallel)

### 3.1 Agent output: `agents/schemas.py`
```python
class BidListing(BaseModel):
    portal: Literal["gem", "cppp", "haryana"]
    bid_no: str                     # unique together with portal
    title: str
    item: str | None = None
    buyer: str | None = None        # ministry / department
    quantity: str | None = None
    est_value: float | None = None  # INR
    end_date: datetime              # parsed, IST-aware
    doc_url: str | None = None
    source_url: str                 # link the user can open

class Corrigendum(BaseModel):
    bid_no: str
    summary: str                    # "Deadline extended to 02 Nov"
    new_end_date: datetime | None = None
    source_url: str
```

### 3.2 Agent functions: `agents/` (the only code that touches the web)
> TinyFish is the only component that navigates portals; bid PDFs it finds are downloaded via an Indian connection.
```python
async def sweep_portal(portal: str, category: str, emit: Callable[[StepEvent], None], sweep_id: str = "local") -> list[BidListing]
async def fetch_doc_text(url: str) -> tuple[str, str]         # (text, source): TinyFish Fetch, else direct PDF download
async def search_corrigenda(bid: BidListing) -> list[Corrigendum]  # TinyFish Search API
```
- `sweep_id` is stamped on every emitted `StepEvent`; the API passes the id it publishes to Redis.
- Fixture file names come from the keyword: `category.lower()`, non-alphanumerics → `_` (e.g. `"steel rack"` → `gem_steel_rack.json`).
- Every agent run goes through an Indian proxy and is capped at 300 s and cancelled past it (at most 2 at once) (a custom step cap is rejected by TinyFish: beta only); a capped run ends as an `error` event with `direct_url`.
- Bid documents: TinyFish Fetch first; if it returns nothing, a direct HTTPS download of the PDF (only hosts of the 3 swept portals, PDF only, ≤15 MB). `source` (`fetch` / `direct` / `fixture`) is stored as `tenders.doc_source` and shown in `/matches/{id}` → `provenance`.
- In `FALLBACK_MODE`, `sweep_portal` replays `delivery/fixtures/{portal}_{category}.json`. It emits the recorded steps with 0.3–0.8 s delays.
- Unusable run result: retry the run once. Invalid bid: log and skip that bid. One bad bid never fails a sweep.
- Captcha or blocked portal: emit an `error` event with `direct_url`, return `[]`. **Never bypass the captcha.**

### 3.3 SSE step event (Redis channel `sweep:{sweep_id}` → `GET /sweeps/{id}/events`)
```json
{"sweep_id": "uuid", "agent": "gem|cppp|haryana|corrigenda",
 "type": "started|step|result|error|done",
 "step": 7, "message": "Filtering by keyword 'steel rack'",
 "count": 12, "direct_url": null, "ts": "2026-10-24T14:02:11+05:30"}
```
`count` is set on `result` (bids found). `direct_url` is set on `error`. After all agents finish, one final event with `agent: "all"` and `type: "done"`.
- Each portal card gets exactly one `started`, then `step`s, then one `result` or `error`, even though a portal is searched once per profile keyword (per-keyword messages are prefixed `[keyword]`). A portal ends in `error` (with `direct_url`) only when it found no bids and something failed (captcha, crash, no fixture).
- Pipeline progress after the portals finish is sent as `agent: "all"`, `type: "step"` (e.g. "Reading 10 bid documents", "Matching tenders against your profile"). The `done` message carries the summary.
- `all/done` fires once listings, already-known documents (same `doc_url` in the DB or a fixture: text and parse reused) and corrigenda are matched; it carries `pending` = new documents still to read. Those are fetched and parsed in the background (Groq: one at a time; 429/5xx/timeouts → eligibility null → CHECK_DOCS); each parse re-matches its tender and publishes `all/update` (`tender_id`); `all/settled` ends the stream. With `pending: 0`, `all/done` ends it.
- A client that connects late (or reconnects) gets the full event log replayed first. If a sweep goes silent for 15 min (server restarted mid-sweep), the stream ends with a `done` saying so.

### 3.4 Eligibility JSON (stored in `tenders.eligibility`)
```json
{
  "min_turnover":          {"value": 5000000, "source_clause": "Minimum average annual turnover ... Rs 50 Lakh"},
  "past_experience_years": {"value": 3,       "source_clause": "..."},
  "emd_amount":            {"value": 37000,   "source_clause": "..."},
  "emd_exemption_for_mse": {"value": true,    "source_clause": "..."},
  "mse_relaxation_experience_turnover":     {"value": false, "source_clause": "MSE Relaxation for Years of Experience and Turnover No"},
  "startup_relaxation_experience_turnover": {"value": false, "source_clause": "..."},
  "required_certifications": {"value": ["ISO 9001"], "source_clause": "..."},
  "documents_required":    {"value": ["Experience Criteria", "Bidder Turnover"], "source_clause": "..."},
  "states":                {"value": [],      "source_clause": null}
}
```
A criterion the document doesn't mention is stored as `{"value": null, "source_clause": null}` (list criteria: `{"value": [], "source_clause": null}`).
The two `*_relaxation_*` flags come straight from GeM bid documents: when MSE relaxation is `true`, an MSE is exempt from the turnover and experience criteria. `documents_required` feeds the document checklist.
`tenders.eligibility` stays `null` when the document couldn't be read or parsed; the matcher treats that as CHECK_DOCS.

### 3.5 REST API: FastAPI (`api/`)
| Method | Path | Body / returns |
|---|---|---|
| `POST` | `/profiles` | Profile JSON → `{id}` |
| `GET` | `/profiles/{id}` | Profile |
| `POST` | `/sweeps` | `{profile_id}` → `{sweep_id}` (runs in background) |
| `GET` | `/sweeps/{id}/events` | SSE stream of §3.3 events |
| `GET` | `/profiles/{id}/matches` | list: tender summary + verdict + fit_score, sorted |
| `GET` | `/matches/{id}` | tender, eligibility (§3.4), verdict, reasons, missing_docs, corrigenda |
| `POST` | `/matches/{id}/alert` | sends WhatsApp/email now (demo button) → `{sent, channels: {whatsapp, email}, preview}`; a channel without credentials reports `not_configured` |
| `GET` | `/health` | `{db, redis, fallback_mode, next_corrigenda_check, now, clock}` (`now`: the demo clock the UI counts down from) |
| `POST` | `/profiles/{id}/match` | re-run the matcher on stored tenders without sweeping → verdict counts |
| `POST` | `/corrigenda/check` | run the daily corrigenda job now (Search API, no credits) → `{checked, new, extended}` |

### 3.6 Matcher verdict rules (`api/matcher.py`)
Hard rules first, then rank by product fit: keyword overlap between the profile's keywords/products and the tender title/item (no embedding key).
- **NOT_ELIGIBLE** if any of these hold:
  - turnover is below `min_turnover`
  - the tender is limited to states the profile doesn't serve
  - the deadline has passed
- **CHECK_DOCS** if a criterion needs proof we can't verify: past experience, a certification not on the profile, or an unparseable value.
- **ELIGIBLE** otherwise.
- Every reason carries its `source_clause`. Example: `"Turnover met (₹1.2 Cr ≥ ₹50 L)"`, `"MSE EMD exemption applies"`.
- Also CHECK_DOCS: no parse at all, or a parse that found no criteria (the fetched page may not be the bid document). Never show green without a clause.
- Past experience is never a hard fail: years in business ≠ years of past supply, so it is always "needs proof".
- MSE (Udyam) profiles skip turnover/experience when the bid's MSE relaxation is Yes, and skip EMD when the MSE EMD exemption applies.
- State names match loosely ("State of Haryana" = "Haryana", "UP" = "Uttar Pradesh").
- Tenders whose product fit is below a threshold are flagged `relevant: false` and listed last.

### 3.7 Fixture format (`delivery/fixtures/{portal}_{category}.json`)
```json
{"portal": "gem", "category": "steel racks", "url": "...", "goal": "...",
 "recorded_at": "...", "run_id": "...",
 "steps": [{"step": 1, "message": "..."}],
 "result": [/* BidListing[] */],
 "docs": {"<doc_url>": "<fetched text>"},
 "eligibility": {"<doc_url>": {/* §3.4 JSON */}}}
```
`eligibility` holds recorded parses, so a `FALLBACK_MODE` demo needs neither the LLM nor the network.

---

## 4. Environment (`.env.example`)
```
TINYFISH_API_KEY=
FALLBACK_MODE=false
DEMO_NOW=                    # fallback only: frozen "now" (ISO, IST if no offset); empty = newest fixture's recorded_at
DATABASE_URL=postgresql+psycopg://tenderhawk:tenderhawk@localhost:5432/tenderhawk
REDIS_URL=redis://localhost:6379/0
GROQ_API_KEY=                # Groq free tier: the eligibility parser
LLM_MODEL=openai/gpt-oss-120b
LLM_MODEL_FAST=openai/gpt-oss-20b
LLM_EFFORT=medium            # reasoning effort for the eligibility parser (low | medium | high)
LLM_MAX_DOC_CHARS=14000      # free tier is 8k tokens/min; GeM eligibility sits in the first pages
LLM_CONCURRENCY=1            # documents parsed in parallel per sweep (free tier fits ~1/min)
LIVE_MAX_KEYWORDS=1          # profile keywords per live portal (billed Agent runs); replayed portals use all
LIVE_PORTALS=                # FALLBACK_MODE=false only: portals swept live, e.g. "gem"; the rest replay (labelled). Empty = all
AGENT_TIMEOUT=480            # live GeM runs take 300-512 s through the Indian proxy
SCHEDULER_ENABLED=true       # daily corrigenda job inside the API process (APScheduler)
CORRIGENDA_HOUR=7            # IST hour for the daily corrigenda job
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
ALERT_WHATSAPP_TO=
SMTP_URL=                    # smtp://user:pass@host:587 (STARTTLS) or smtps://user:pass@host:465
ALERT_EMAIL_FROM=            # defaults to the SMTP user
ALERT_EMAIL_TO=              # overrides the profile's email (demo inbox)
AUTO_ALERT=true              # after each sweep, alert relevant open ELIGIBLE matches not alerted yet (max 3 per sweep, 20 s budget)
NEXT_PUBLIC_API_URL=http://localhost:8000   # baked into the web build
WEB_ORIGINS=http://localhost:3000,http://127.0.0.1:3000   # CORS: origins the API allows
WEB_URL=http://localhost:3000                # where preflight expects the dashboard
```
**Never commit `.env`.** Share secrets over DM, not in the repo or in chat logs.

### 4.1 Models (decided)
| Use | Model (env var) | Notes |
|---|---|---|
| Eligibility parser | Groq free tier `openai/gpt-oss-120b` (`LLM_MODEL`) | Strict JSON-schema output generated from the Pydantic `Eligibility` model (§3.4); every criterion carries `source_clause`. A sweep parses one document at a time (8k tokens/min) and sends the first `LLM_MAX_DOC_CHARS` characters |
| Light tasks (title normalising, alert copy) | `openai/gpt-oss-20b` (`LLM_MODEL_FAST`) | |
| Product fit | keyword overlap (`api/matcher.keyword_fit`) | Profile keywords + products vs tender title + item; no model, no key. `api/embeddings.py` stays off without `OPENAI_API_KEY` |

- Model names live **only in env**. All LLM calls go through `api/llm.py`, so swapping a provider touches one file.

---

## 5. Timeline & tasks

Each block ends with a **checkpoint**: merge to `main`, and `main` must still run.

### H0–4 · Skeleton
| Who | Task | Done when |
|---|---|---|
| Siddhant | `agents/client.py` wrapper, `schemas.py` (§3.1), goals for GeM/CPPP/Haryana with `output_schema` | `python -m agents.cli gem "steel rack"` prints validated `BidListing`s |
| Siddhant | Record the first live GeM run → fixture (§3.7) | `delivery/fixtures/gem_steel_rack.json` exists with relevant, still-open bids |
| Harsh | FastAPI app, SQLAlchemy models (Tender/Profile/Match), Alembic init, `/health`, `/profiles` | `alembic upgrade head` + `curl /health` OK |
| Aditya | Next.js + Tailwind scaffold, layout, profile form (static) | Form renders, posts to a mock |
| Vandan | `docker-compose.yml`: Postgres 16 + pgvector, Redis; `.env.example`; Ramesh seed profile | `docker compose up` → both healthy |

### H4–10 · Data flowing
| Who | Task | Done when |
|---|---|---|
| Siddhant | `sweep_portal` with `agent.stream` → StepEvents; `fetch_doc_text`; CPPP + Haryana goals | All 3 portals return bids or a clean `error` event |
| Harsh | Upsert + dedupe on `(portal, bid_no)`; `POST /sweeps` background task; Redis pub → SSE endpoint | `curl -N /sweeps/{id}/events` streams steps |
| Aditya | Profile form wired to API; **Live agents panel** consuming SSE (4 cards: status, step count, last message, bids found) | Clicking Sweep animates the cards |
| Vandan | Fallback replay inside `sweep_portal` (with Siddhant); fixture recorder script | `FALLBACK_MODE=true` sweep looks identical in the UI |

### H10–16 · Intelligence  (**all fixtures recorded by H12**)
| Who | Task | Done when |
|---|---|---|
| Harsh | LLM eligibility parser → §3.4 JSON (structured output, Pydantic-validated); PyMuPDF for PDFs | 5 real GeM docs parse with clauses |
| Harsh | Matcher (§3.6) + ranking + `/profiles/{id}/matches`, `/matches/{id}` | Ramesh gets ≥1 of each verdict colour |
| Siddhant | `search_corrigenda` + daily job (APScheduler); corrigenda agent card in SSE | A corrigendum shows on a match |
| Aditya | Matches list (verdict chips green/amber/red, value, deadline countdown) | Renders real API data |
| Vandan | Record fixtures: GeM, CPPP, Haryana × "storage rack" + doc texts + parses | Full demo runs with wifi off |

### H16–21 · Demo polish → tag `v0.1-demo`
| Who | Task | Done when |
|---|---|---|
| Vandan | Twilio sandbox WhatsApp alert + email; `/matches/{id}/alert`; auto-alert new ELIGIBLE matches | Message lands on the stage phone |
| Aditya | Match detail page: verdict, reasons, **highlighted source clause**, doc checklist, source link | Matches the demo script, step 3 |
| Harsh + Siddhant | Error states: portal blocked → "Open on portal" link; LLM failure → CHECK_DOCS | No blank screens or stack traces in UI |
| All | Full demo dry run, live and fallback | Tag `v0.1-demo` |

### H21–24 · Freeze
- **Fixes only.** No new features, no refactors.
- README with run steps, architecture diagram and the "TinyFish navigates every portal" story.
- Rehearse the demo twice in each mode. Agree who presents and who drives the laptop.

---

## 6. How we work
- **Branches:** `feat/agents`, `feat/backend`, `feat/web`, `feat/delivery`. `main` must always be demo-able.
- **Commits:** small, every 30–60 min, using conventional prefixes (`feat(agents): ...`, `fix(api): ...`, `chore: ...`, `docs: ...`).
- **Budget:** Agent API runs cost credits, so use them only for listing sweeps and never per user. Use fixtures while developing the UI and matcher.
- **Rules that don't bend:**
  - Never bypass captchas.
  - Never submit bids (read-only).
  - Never commit secrets.
  - Only `agents/` touches the live web: TinyFish is the only component that navigates portals; bid PDFs it finds are downloaded via an Indian connection.

---

## 7. Open decisions (resolve in the first hour)
- [x] **LLM provider/model** → Groq free tier: `openai/gpt-oss-120b` (eligibility parser), `openai/gpt-oss-20b` (light tasks). We have no Anthropic or OpenAI key (and no budget), so Claude was removed and ranking uses keyword overlap. See §4.1.
- [x] **Ranking** → keyword overlap (no OpenAI key, no budget). See §4.1.
- [x] **Demo category keyword(s)** for Ramesh → "steel almirah", "storage rack", "steel rack" (in `delivery/seed/ramesh.json`). "steel almirah" comes first because it is a real GeM category ("Steel Almirah / Cabinets") that returned 8 open bids live, while live "storage rack" searches mostly return 0 relevant bids (C5). Live portals search only the first keyword (`LIVE_MAX_KEYWORDS=1`); replayed portals use all three, so CPPP and Haryana still replay their "storage rack" recordings.
- [ ] **Stage phone** joined to the Twilio sandbox, and whose number
- [x] **Run ports:** API `:8000`, web `:3000`, Postgres `:5432`, Redis `:6379`. Docker host ports can be moved with `API_PORT`, `WEB_PORT`, `POSTGRES_PORT`, `REDIS_PORT`.

## 8. Risks & fallbacks
| Risk | Fallback |
|---|---|
| Portal slow, down or captcha'd | Fixture replay (`FALLBACK_MODE`) and a direct link to the portal |
| Venue wifi dies | Everything local in Docker (`docker compose --profile app up -d`), plus fixtures with recorded parses (`FALLBACK_MODE=true`); the WhatsApp alert needs a phone hotspot |
| LLM misparses a document | The verdict falls back to CHECK_DOCS ("Couldn't read eligibility from the bid document"); a parse with no clauses is CHECK_DOCS too |
| Agent returns malformed JSON | `output_schema` plus one retry, then skip |
| Running out of time | Cut order: email → corrigenda job → Haryana portal. **Never cut:** fallback mode, the clause highlight, WhatsApp |

## 9. Progress (updated 2026-10-25)

Legend: ✅ done and verified · 🟡 partly done / blocked · ⬜ not started

**In short:** every feature in scope is built and merged to `main` (all `feat/*` branches merged). The one real code gap (live GeM document text) is closed (C1). The dashboard now uses the Stitch design (`feat/web-stitch`) and has run on the real stack. Everything else is Twilio setup and rehearsal. No paid keys are needed: Groq (free) parses, keyword overlap ranks, Twilio's free trial sends WhatsApp.

All §3.5 endpoints exist. Docker: `docker compose --profile app up -d --build` runs the API (:8000) and dashboard (:3000) too.

**Done today (2026-10-24):**
- Branches checked (all merged, `main` = `origin/main`); Groq free tier replaced Claude as the only LLM (Anthropic removed); parser verified on 2 real GeM bid PDFs: every criterion found, every clause verbatim in the document, ~7 s each, MSE EMD exemption caught.
- Phase 0 (`fix/demo-hardening`): web `npm install` + `npm test` (14 ✅) + `npm run build` ✅; one alembic head. Docker not running (Docker Desktop's `docker-desktop` WSL distro stopped), so DB steps and the 2 Postgres alert tests wait for it.
- Phase 1 (C1): GeM doc text via Fetch → direct PDF download in `agents/` (verified live, `source=direct`); agent route tried once and can't read PDFs; `AGENT_LIMITS` no longer sends the rejected `max_steps`; `tenders.doc_source` / `eligibility_source` + `/matches/{id}` provenance.
- Phase 2: one clock (`api/clock.py` `now_ist()`) for matcher, corrigenda, auto-alert, fixture check; web and `/demo` countdowns sync from `/health.now`. Fallback freezes at `DEMO_NOW`, else the newest fixture's `recorded_at` (no date rewriting). Tests: closes-in-3-days stays open, deadline-passed is NOT_ELIGIBLE.
- Phase 3: timezone audit. Storage was already tz-aware (`timestamptz`); added `as_ist()` so a naive datetime means IST, never the server's zone (matcher no longer crashes on one; alert "closes" text and corrigenda time-of-day no longer depend on `TZ`); `/demo` dates pinned to Asia/Kolkata. Tests: GeM "24-10-2026 2:00 PM IST" → 14:00 IST; a 15:00 IST deadline is open at 14:59 and passed at 15:01 with the server in UTC / Los Angeles / Kolkata.
- Phase 4: parse cache (text + parse reused by `doc_url` from the DB, then fixtures, in live and fallback mode); `all/done` fires before new documents are read (`pending`), background reads publish `all/update` per re-matched tender and end with `all/settled`; dashboard and `/demo` keep listening and reload matches. Groq 429 retried by the SDK (`LLM_MAX_RETRIES`), persistent 429/5xx/timeouts → CHECK_DOCS, tested.
- Phase 5: real fixtures. `gem_storage_rack` (live run, 28 steps, 1 bid, PDF via direct download, parsed: ELIGIBLE, no EMD/turnover criteria); `cppp_storage_rack` (3 real storage-rack bids, ₹9.3–39.5 L; CPPP only gives expiring session links, so no documents: CHECK_DOCS + stable portal link); `haryana_storage_rack` (blocked by captcha after 26 steps: replays as the captcha card with the portal link); `gem_steel_almirah` (8 bids; the agent guessed `/showbiddata/` links (404), no documents: CHECK_DOCS). Old `gem_steel_rack` retired. Verdict mix from real data: ELIGIBLE 1, CHECK_DOCS 11, **NOT_ELIGIBLE 0** (not forced). Found: TinyFish's 300 s cap is soft (runs took 352 s and 471 s), so `agents/` now stops waiting at `AGENT_TIMEOUT` (330 s) → clean error card; blocked runs are recorded and replayed; GeM goal demands the exact `showbidDocument` href and guessed links are dropped.
- Phase 6: `python -m delivery.seed --reset` (tenders, matches + alert flags, `sweep:*` Redis keys; reseeds Ramesh) and `scripts/preflight.py` (11 checks, PASS/WARN/FAIL, exit 1 on FAIL; TinyFish wallet read via the SDK: $15.18 ≈ 948 agent steps). Today it reports NOT READY: Docker down, Twilio unset, NOT_ELIGIBLE missing from the verdict mix.
- Phase 7: verdict chips say "You can bid" / "Keep proof ready" / "Turnover short"·"Deadline passed"·"State not served" (icon + words, never colour alone); match page provenance line (found by TinyFish on <portal> · document fetch/direct/recorded · eligibility LLM/recorded · verdict by rules); Replay-mode badge with the demo clock; `:focus-visible` ring; eligibility table scrolls and row metrics wrap at 390 px; CORS from `WEB_ORIGINS`; DB down → plain 503 sentence, never a bare 500. No Playwright in the project, so no headless run: smoke-tested with the real build (`next start` + uvicorn, DB down): pages render loading shells, API answers 503 sentences, unknown route 404, no tracebacks. Full click-through of §0 waits for Docker (HUMAN TODO).
- Phase 5 follow-up (C3): searched all 12 recorded open bids for corrigenda: none real, so no corrigenda fixture (never invented). The old filter flagged 4 of them from menu text ("Active Tenders | Corrigendum | Bid Awards") and boilerplate ("ATC and Corrigendum if any"); `is_corrigendum_notice` now needs a notice phrase ("Corrigendum 1", "date extended", "extended till <date>", "Amendment No. 2") within 250 chars of the bid number: 0 false positives on the same 12.
**Done 2026-10-25:**
- Web redesign from the Google Stitch project "TenderHawk AI Tender Intelligence" (`feat/web-stitch`): landing `/`, onboarding `/start`, per-profile tabs Live Matches / Watched Portals / Business Profile / WhatsApp Alerts sharing one sweep (`ProfileShell`), match detail in the same frame. Mockup claims we don't do (GSTN/Udyam API verification, factory photos, 14 portals, OCR, WhatsApp reply commands, Meta Cloud API) left out; Udyam shows "as declared". New read-only endpoints `GET /matches/{id}/alert/preview` and `GET /alerts/status`. Fonts self-hosted via `next/font`, icons inline: works offline.
- First run on the real stack (Docker up): migrations, `seed --reset`, API in replay mode + production web build. Sweep → 123 SSE events: GeM 53 steps / 9 bids, CPPP 19 / 3, Haryana captcha card after 28 steps with portal link, corrigenda 13 / 0 new; 12 tenders, 1 ELIGIBLE, 11 CHECK_DOCS. Every page screenshotted with real data (1440 px and 390 px). Tests: **116 passed** (incl. the Postgres alert tests), web 22. Preflight: 16 PASS, 1 WARN (no NOT_ELIGIBLE), 1 FAIL (Twilio unset). Wallet $14.20.
- Phase 8: CLAUDE.md, PLAN.md, README and `.env.example` agree: Groq gpt-oss models, keyword-overlap ranking (OpenAI/1536-d embedding config removed), no Claude/OpenAI key needed, the Phase 1 invariant wording, `DEMO_NOW`, preflight, `seed --reset`, the Twilio trial-prefix note, real test counts and the soft-cap finding.
- Live sweeps (afternoon, `FALLBACK_MODE=false`): no live sweep returned bids yet. Findings from TinyFish's run history: (1) the plan runs **2 agents at once**; a 3rd waited 197 s in TinyFish's queue and that wait counted against our timeout, so a GeM run that found 6 bids was thrown away → runs now queue locally (`TINYFISH_CONCURRENCY`, GeM first). (2) The 300 s cap was soft twice over: TinyFish lets runs go 385–512 s, and our timeout only stopped *listening* while the run kept going and billing → `agents/` now cancels the run at 300 s (`POST /v1/runs/{id}/cancel`; the SDK has no cancel). (3) A sweep that found nothing crashed with `KeyError: 'total'` (`match_profile` early return) → fixed. (4) GeM is reachable (occasional `ERR_TUNNEL_CONNECTION_FAILED` through the proxy, ~3 in 12 runs) but returns 0 relevant bids: see C5. (5) CPPP's listing pages now ask for a captcha before showing results (this morning's run could still read them); only the homepage "Latest Tenders" ticker is public. Haryana's homepage "Latest Tenders" list is public; only its search forms have captchas.
- Twilio credentials set and verified (account active, Trial; read-only API check, nothing sent). The stage phone's sandbox join and the first real send are still open (S4).

### Left to implement (code)
| # | Task | Owner | Notes |
|---|---|---|---|
| C1 | ✅ **Live GeM document text** (2026-10-24): Fetch → else direct PDF download in `agents/`; verified live on `showbidDocument/9845350` (19,776 chars, `source=direct`). The agent route was tried and can't read PDFs (§1) | Siddhant | done |
| C2 | ✅ **CPPP + Haryana live runs** (2026-10-25): CPPP 3 bids (documents only behind expiring session links → CHECK_DOCS + stable list link); Haryana blocked by captcha after 26 steps → error card with portal link, replayed from its fixture. Cap: custom steps rejected, 300 s is soft → enforced by `agents/` at 300 s and the run cancelled on TinyFish | Siddhant | done |
| C3 | ✅ Corrigenda checked for all 12 recorded bids: none real, so no fixture (the 4th card replays "0 new"). Matcher false positives fixed | Siddhant | done |
| C5 | ✅ **GeM live goal returned 0 bids** (fixed 2026-10-25, Harsh). Causes: (1) GeM lists closing-soonest first and the short goal doesn't re-sort, so the 2-day window dropped every card → window is now tomorrow onward (`MIN_CLOSE_DAYS=1`); (2) the agent reports "nothing relevant" as `blocked` → `agents/` shows a block only when the reason names a captcha/login/unreachable site, else "No relevant open bids"; (3) our 300 s timeout cut off runs that finished at 319 s → `AGENT_TIMEOUT` 480 s; (4) live keyword is "steel almirah" (a real GeM category). Verified live 2026-10-25: 16 steps, **7 real open bids** (Steel Almirah / Cabinets from Railways, MoD, Haryana Higher Education…) with real `showbidDocument` links. `LIVE_PORTALS=gem` runs GeM live and replays CPPP/Haryana (C6) | Harsh | |
| C6 | 🟡 CPPP and Haryana live goals: read only the public homepage "Latest Tenders" lists, never a search form (they need a captcha). Then rerun each live on its own (6 min wall clock) | Siddhant | C5 |
| C4 | Optional, cut first: email via `SMTP_URL` (code done, needs an SMTP account, e.g. a Gmail app password) | Vandan | |

Not building (by choice): OCR for scanned PDFs (every GeM bid seen has a text layer), real embeddings (no OpenAI key; keyword overlap is enough), Browser API (phase 2).

### Left to do (setup, data, rehearsal)
| # | Task | Owner | Blocked on |
|---|---|---|---|
| S1 | ✅ Docker running (2026-10-25): `docker compose up -d`, `alembic upgrade head`, `seed --reset`, 116 + 22 tests, sweep in replay mode end to end | Siddhant | — |
| S2 | ✅ Real fixtures: `gem_storage_rack`, `cppp_storage_rack`, `haryana_storage_rack`, `gem_steel_almirah`, all "fixture OK". **No NOT_ELIGIBLE from real data** (1 ELIGIBLE, 11 CHECK_DOCS) | Vandan + Siddhant | — |
| S3 | 🟡 3 of 5 real GeM docs parsed with verbatim clauses (NIT Warangal rack, IIM Indore, GeM 9998812) | Harsh | — |
| S4 | 🟡 Twilio sandbox (free trial): `TWILIO_*` keys ✅ and verified, `ALERT_WHATSAPP_TO` ✅ set; stage phone joined to the sandbox and one real alert sent still open | Vandan | phone |
| S5 | Full dry run live + fallback (checklist below), clicking "Sweep now" and "Send now" by hand in a browser (only screenshotted so far), then tag `v0.1-demo` | All | S2, S4 |
| S7 | Merge `feat/web-stitch` into `main` after the hand click-through | Siddhant | S5 |
| S6 | H21–24 freeze: fixes only, rehearse twice per mode, decide presenter / driver | All | S5 |

| Block | Task | Owner | Status | Notes |
|---|---|---|---|---|
| H0–4 | TinyFish wrapper, schemas, goals, CLI | Siddhant | ✅ | merged to `main` |
| H0–4 | First live GeM fixture | Siddhant | ✅ | `gem_steel_rack` retired; replaced by `gem_storage_rack` + `gem_steel_almirah` (Phase 5) |
| H0–4 | FastAPI, models, Alembic, `/health`, `/profiles` | Harsh | ✅ | |
| H0–4 | `docker-compose.yml`, Ramesh seed | Vandan | ✅ | `python -m delivery.seed` |
| H0–4 | Next.js scaffold + profile form | Aditya (built by Harsh) | ✅ | `web/`, Next.js 16 + Tailwind 4; Ramesh demo fill button |
| H4–10 | Upsert + dedupe, `POST /sweeps`, Redis → SSE | Harsh | ✅ | late clients replay the full log |
| H4–10 | `sweep_portal` streaming, `fetch_doc_text`, CPPP + Haryana goals | Siddhant | 🟡 | GeM live run ✅ via Indian proxy (10 bids, 8 steps). GeM doc text ✅ via direct PDF download when Fetch fails (C1). CPPP + Haryana run live and recorded (C2). Runs capped at 300 s (custom step cap rejected by TinyFish). |
| H4–10 | Fallback replay | Vandan + Siddhant | ✅ | replays steps with delays; missing fixtures → error card with portal link |
| H4–10 | Live agents panel (SSE) | Aditya (built by Harsh) | ✅ | 4 cards from §3.3 events; survives reconnect replays; `?sweep=` follows a running sweep |
| H10–16 | LLM eligibility parser + PyMuPDF | Harsh | 🟡 | Groq free tier (Claude removed). 3 of 5 real GeM docs parsed on Groq with verbatim clauses (see S3) |
| H10–16 | Matcher + embeddings + `/profiles/{id}/matches`, `/matches/{id}` | Harsh | ✅ | keyword-overlap ranking; clause excerpts for highlighting |
| H10–16 | `search_corrigenda` daily job + corrigenda card | Siddhant (backend wiring: Harsh) | ✅ | 4th SSE card in every sweep; daily 07:00 IST job + `POST /corrigenda/check`; extensions move `end_date`; shown as info reasons with links. Fallback reads `delivery/fixtures/{portal}_corrigenda.json` (`{bid_no: [Corrigendum]}`); none recorded yet |
| H10–16 | Matches list UI | Aditya (built by Harsh) | ✅ | verdict chips with text labels, value, deadline countdown, fit; low-relevance folded. Restyled to the Stitch design with 4 tabs (2026-10-25) |
| H10–16 | Fixtures GeM/CPPP/Haryana × "storage rack" + doc texts + parses | Vandan | ✅ | Recorded (S2): GeM, CPPP, Haryana (blocked) + GeM steel almirah, all "fixture OK"; only 1 GeM doc parsed into a fixture |
| H16–21 | Twilio WhatsApp + email, `/matches/{id}/alert` | Vandan (built by Harsh) | 🟡 | `delivery/alerts.py`: Twilio REST + SMTP, endpoint, auto-alert after sweeps; tested with stubs. Needs `TWILIO_*` + stage phone joined to the sandbox to send for real |
| H16–21 | Match detail page with highlighted clause | Aditya (built by Harsh) | ✅ | clause highlighted in the bid text, checklist, corrigenda, alert button with message preview |
| H16–21 | Error states (blocked portal link, LLM failure → CHECK_DOCS) | Harsh + Siddhant | ✅ | "Open on portal" cards, API-down / DB-down banners, reconnect notice, 404 pages |
| H21–24 | README, dry runs, tag `v0.1-demo` | All | 🟡 | README current. No tag yet. Dry runs and the tag wait for real fixtures and the Twilio sandbox (needs keys) |

Not built, by choice: OCR for scanned bid PDFs (CLAUDE.md stack). Every GeM bid PDF tested so far has a text layer; `build_fixture attach` reports a document with no text instead of guessing.

**Backend run steps (current):**
```
cp .env.example .env              # fill keys
docker compose up -d              # Postgres + Redis (skip redis if one already runs on :6379)
pip install -r requirements.txt
alembic upgrade head
python -m delivery.seed           # prints Ramesh's profile id
uvicorn api.main:app --reload     # :8000
python -m pytest -q tests         # 116 tests, no keys needed (2 alert tests + seed reset need Postgres/Redis running)
cd web && npm test                # 22 tests
python scripts/preflight.py       # before a demo: must print READY
```

**Before every demo run (checklist):**
1. `docker compose up -d` (or the app profile), `alembic upgrade head`, then **`python -m delivery.seed --reset`**: wipes tenders, matches (and their alert flags) and sweep logs, reseeds Ramesh, prints his id. The on-stage sweep then starts from nothing and alerts again.
2. **`python scripts/preflight.py`** prints PASS / WARN / FAIL for: docker services, alembic at head, `/health`, web reachable + CORS for the web origin, `FALLBACK_MODE` / `DEMO_NOW`, every fixture "fixture OK", verdict mix, Twilio creds + `ALERT_WHATSAPP_TO`, TinyFish key + wallet, Groq key + models, ports. It must end in `READY`.
3. The stage phone has sent the sandbox join message to the Twilio number **within the last 24 h** (otherwise Twilio accepts the message but never delivers it). `ALERT_WHATSAPP_TO` is that phone. (Preflight can't see this.) Trial accounts prefix SMS with "Sent from your Twilio trial account -"; check on the first real send whether WhatsApp shows it too.
4. **Live demo (GeM through TinyFish on stage):** after step 1, run one sweep with `FALLBACK_MODE=true` so the dashboard holds the recorded tenders (incl. the ELIGIBLE one), then restart the API with `FALLBACK_MODE=false LIVE_PORTALS=gem`. "Sweep now" then streams a real GeM agent run (5–7 min at ~15 s a step: start it as you begin talking) while CPPP and Haryana replay their recordings (labelled "Replaying the recorded run"). New GeM bids land in Matches as their documents are parsed. If GeM is down or finds nothing, the card says so and the recorded matches are still there.
5. Fallback rehearsal with wifi off: `FALLBACK_MODE=true`, dashboard at :3000, sweep, open a match, send the alert over a phone hotspot.

