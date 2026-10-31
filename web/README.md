# TenderHawk dashboard (Next.js)

Profile form, live agents panel, matches list and match detail with highlighted source clauses.
It talks only to the TenderHawk API (`api/`); it never touches the live web itself.

```bash
cp .env.example .env.local        # NEXT_PUBLIC_API_URL, default http://localhost:8000
npm install
npm run dev                       # http://localhost:3000
npm test                          # helper + sweep-state tests (vitest)
npm run lint && npm run typecheck && npm run build     # what CI would run
```

Pages:

| Path | What it shows |
|---|---|
| `/` | Create a business profile (or fill the Ramesh demo persona), or open one by id |
| `/profiles/{id}` | "Sweep now", four live agent cards (GeM, CPPP, Haryana, Corrigenda), matches with verdict chips |
| `/profiles/{id}?sweep={sweep_id}` | Follow a sweep that is already running (a second screen during the demo) |
| `/matches/{id}` | Verdict, reasons with the clause highlighted in the bid text, document checklist, corrigenda, alert button |

Fonts are system fonts, so the dashboard renders with no network in fallback mode.
In Docker it is built by `docker compose --profile app up -d --build` from the repo root (`web/Dockerfile`).
