# Rasad

Working name (Arabic for observation). A sovereign indicators-and-warnings engine for Gulf national security: a standing board of calibrated, evidence-traceable probabilities on the questions a principal has to decide on, in Arabic and English, refreshed daily, with a hash-chained commitment log and a public calibration record.

Version 0.3 runs on live data and carries the analyst workflows: the Hormuz and Red Sea module end to end on IMF PortWatch, UKMTO, JMIC, the UK Sanctions List, QNA and GDELT; a position book (stated versus revealed policy) for the United States, Iran, Saudi Arabia, Qatar, the UAE, the GCC and the Houthis; question and indicator editing, panel entry, evidence entry, resolution and tasking; alerts and a daily "what changed" page; search; Word export; accounts, roles, API keys, licence files and an audit log.

## What is in the box

| Layer | Where | What it does |
| --- | --- | --- |
| Threat ledger | `backend/rasad/models` | Coded events with provenance, verification state and a synthetic flag; maritime, war-risk and listed-area series |
| Policy ledger | `backend/rasad/policy` | Graded observations (cost class, speaker, 6x6 grade, confidence) → stated and revealed tracks, divergence, change-points, silence |
| Indicator engine | `backend/rasad/engine` | Rule-evaluated indicators → Bayesian update with capped likelihood ratios → extremised panel aggregate → blended, committed forecast |
| Commitment log | `backend/rasad/engine/commitment.py` | SHA-256 hash chain over every committed forecast; verified on the Record page |
| Scoring | `backend/rasad/engine/scoring.py` | Brier, Brier skill against the status-quo base rate, calibration bins, by horizon |
| Connectors | `backend/rasad/pipelines/connectors` | IMF PortWatch (ArcGIS, since 2024), the MSCIO library (UKMTO warnings and advisories, JMIC dashboards and advisory notes, weekly threat assessments), UK Sanctions List, GDELT standing queries, QNA feeds, Lloyd's JWC circulars, OFAC and State Department parsers; each parser tested on a real fixture |
| Alerts | `backend/rasad/engine/alerts.py` | Indicator flips, forecast moves, severe events, transit breaks, chain failures, resolutions due; acknowledgement; optional email digest |
| Workflows | `backend/rasad/api/workflow_routes.py` | Question and indicator editing with rule preview, panel forecasts per analyst, evidence entry, resolution, tasking from open to framed to answered |
| Product | `backend/rasad/licence.py`, `api/admin_routes.py` | Ed25519 licence files with seats and features, API keys (bearer), branding and marking settings, CSV and JSON exports |
| Extraction | `backend/rasad/extraction` | Lexicon extraction (Arabic, Farsi, English) that always works; optional Claude API or local open-weight model behind the same interface; everything lands in the verification queue |
| Briefs | `backend/rasad/briefs` | Two-to-three page brief per question in Arabic or English, PHIA yardstick bands, confidence stated separately; optional model polish that may not add a fact |
| Accounts | `backend/rasad/auth` | Users, roles, signed-cookie sessions with a client header on writes, API keys, audit log, operator CLI |
| API | `backend/rasad/api` | FastAPI; serves the built front end; every route behind sign-in |
| Front end | `frontend/` | React, TypeScript, Tailwind; board, today, question page with evidence, panel and related documents, position book, brief with Word export, record, verification queue, questions editor, evidence entry, tasking, search, sources, administration; full right-to-left Arabic |

## Run it locally

```bash
# backend (SQLite, no Docker)
cd backend
pip install -e ".[dev]"
python -m rasad.seed.load 2026-10-18        # reference data, the shipped snapshot of real series and events, a 30-day forecast history
python -m rasad.pipelines.run backfill       # live: PortWatch since 2024, the MSCIO library, UK sanctions, QNA, GDELT (needs internet)
uvicorn rasad.api.app:app --reload           # http://localhost:8000/api/status

# front end (dev server proxies /api to :8000)
cd ../frontend
npm install
npm run dev                                   # http://localhost:5173
```

Tests: `cd backend && pytest -q` (47 tests: engine, policy maths, every connector against a real fixture, accounts, roles, licence, the API end to end).

## Daily operation

`python -m rasad.pipelines.run daily` (the scheduler container runs it at `RASAD_PIPELINE_TIME`) polls every feed, extracts pending evidence, commits the day's forecasts to the chain, raises alerts and sends the digest. Other commands: `poll`, `extract`, `commit`, `backfill` (first run), `ingest-dir <folder>` (a folder of PDFs on an air-gapped host), `snapshot` (export real rows into the seed), `digest`. Feeds are configured in `<data dir>/urls.yaml`; the egress allow-list is `RASAD_EGRESS_ALLOWLIST`.

`python -m rasad.doctor` prints a readiness report (database, licence, chain, source freshness, reachability of every feed host) and exits non-zero when a deployment dependency is broken; support asks for its output first.

Analysts work from the Today page (alerts, moves, new events), the verification queue, the Questions editor (indicators with a rule preview), Evidence entry and Tasking. Every write is attributed and audited. Briefs export to Word with the marking in the header and footer.

## Licensing

The platform runs in evaluation mode (full functionality, three seats) until a licence file is installed under Administration. Licence files are JSON documents signed with the vendor's Ed25519 key (`python -m rasad.licence issue vendor.key --licensee "Org" --seats 25 --expires 2027-12-31 --features core,arabic,api,model,export`); the public key is embedded in `backend/rasad/licence.py` and the private key never enters the repository. Expired licences get a 30-day grace period. API keys (`Authorization: Bearer rsk_...`) are created under Administration and act with the role they were given.

## Run it for real (a server you keep)

One command on a fresh Ubuntu server. Point a hostname at the server first if you want TLS (an A record for, say, `rasad.yourdomain.com`); without one it serves plain HTTP for a first look.

```bash
# copy the repo to the server (scp, rsync or git clone), then:
sudo bash deploy/install.sh rasad.yourdomain.com
```

That installs Docker, opens ports 22, 80 and 443, writes `.env` with generated secrets, builds and starts five containers (Postgres, the API with the front end, Caddy for TLS, the daily scheduler, nightly backups), seeds the demo data and prints the first admin password. Sign in, change the password, add colleagues under Users.

What runs afterwards without you:

| Service | What it does | Where to look |
| --- | --- | --- |
| scheduler | Polls the configured sources, extracts, commits forecasts every day at `RASAD_PIPELINE_TIME` (06:00 Dubai by default) | `docker compose logs -f scheduler` |
| backup | `pg_dump` every 24 hours, kept for 30 days | the `backups` volume: `docker compose exec backup ls /backups` |
| web (Caddy) | TLS certificate issue and renewal, security headers | `docker compose logs web` |

Day-to-day operations:

```bash
docker compose ps                                   # health
docker compose logs -f api                          # requests and errors
docker compose --profile pipeline run --rm pipeline # run the pipeline now
docker compose exec api python -m rasad.auth.cli list        # accounts
docker compose exec api python -m rasad.auth.cli password liam
sudo bash deploy/update.sh                          # deploy a new version (data and .env untouched)
```

Restore from a backup: `zcat backups/rasad-YYYYMMDD-HHMM.sql.gz | docker compose exec -T db psql -U rasad rasad` into a fresh database.

Connector URLs for PDFs (UKMTO advisories, JWC circulars, JMIC dashboards) and the PortWatch export go in `urls.yaml` in the data volume (`docker compose exec api sh -c 'cat > /data/urls.yaml'`); see `backend/rasad/pipelines/run.py` for the keys. Connectors refuse any host not on `RASAD_EGRESS_ALLOWLIST`.

## Accounts and roles

Everything behind the sign-in. Three roles:

| Role | Can |
| --- | --- |
| viewer | Read the board, question pages, position book, record, briefs and sources; pose a question |
| analyst | Viewer, plus the verification queue, question and indicator editing, panel estimates, evidence entry, resolution, tasking answers, alert acknowledgement, exports and committing forecasts |
| admin | Analyst, plus users, licence, API keys, branding and the audit log |

New accounts get a temporary password and must set their own on first sign-in. Every sign-in, verification decision, commit, brief and user change is written to the audit log with the user and IP. Passwords are PBKDF2-SHA256; sessions are signed cookies that expire after 12 hours; ten failed sign-ins in a quarter hour lock that username for the rest of it.

Bringing a team on, in order: give colleagues viewer access first so they read the board and briefs; promote the two who will own evidence to analyst and route all verification through them; keep admin to one person plus a deputy. Set `RASAD_PUBLIC_RECORD=true` only when the calibration record has real resolutions behind it.

## Data

The seed ships a snapshot (`backend/rasad/seed/data/snapshot.json`) of real rows exported from a live run: PortWatch daily transits for Hormuz, Bab el-Mandeb, Suez and the Cape since January 2024, every UKMTO warning and advisory from October 2025, the JMIC threat-level and transit series from the 2026 advisory notes and weekly dashboards, UK sanctions designations, and the curated events and observations behind the concept document, each with a source and URL in `provenance`. Connector rows an analyst has not yet accepted stay `pending`. The `is_synthetic` flag marks the few remaining illustrative rows (war-risk premium interpolations between quoted points, illustrative statements); the banner stays up while any is present, and `python -m rasad.pipelines.run backfill` on a connected host replaces the snapshot with the live record.

The four resolved demo questions on the Record page were produced by replaying the engine on the seeded ledgers as of earlier dates with no tuning; the misses are shown as they fall.

## Model providers

`RASAD_MODEL_PROVIDER=rules` is the default and needs nothing. `anthropic` uses the Claude API for extraction and brief polish during development. `local` points at any OpenAI-compatible endpoint (vLLM or SGLang serving Jais 2, Fanar 2 or similar) for in-country deployment. The extraction prompt in `backend/rasad/extraction/prompts.py` never asks a model for a probability; it asks for rows with a quote, and an analyst accepts or rejects them.

## Where this goes next

1. Bought feeds from the concept document's acquisition plan (AIS, insurance quotes, ADS-B) behind the same connector interface.
2. Fine-tune the Arabic and Farsi extractors on the verified corpus the queue builds; raise the review quota for the weaker languages.
3. Resolve the first live questions on their dates and let the Record page carry real skill numbers before any client sees it.
4. Arabic for decision hooks and resolution criteria in the seed (the briefs currently carry those in English).
5. Sovereign deployment: the same containers on an in-country cloud or private cloud; the stack has no outbound dependency except the allow-listed feeds.

## Layout

```
backend/rasad/   api  auth  briefs  engine  extraction  licence.py  models  pipelines  policy  seed
backend/tests/
frontend/src/    pages  components.tsx  api.ts  auth.tsx  i18n.tsx
deploy/          install.sh  update.sh  Caddyfile  backup.sh
Dockerfile  docker-compose.yml  .env.example
```
