# Rasad

Working name (Arabic for observation). A sovereign indicators-and-warnings engine for Gulf national security: a standing board of calibrated, evidence-traceable probabilities on the questions a principal has to decide on, in Arabic and English, refreshed daily, with a hash-chained commitment log and a public calibration record.

Version 0.1 is the vertical slice from the concept document: the Hormuz and Red Sea module end to end, a first position book (stated versus revealed policy) for the United States, Iran, Saudi Arabia, Qatar, the UAE, the GCC and the Houthis, and the connectors for the free sources.

## What is in the box

| Layer | Where | What it does |
| --- | --- | --- |
| Threat ledger | `backend/rasad/models` | Coded events with provenance, verification state and a synthetic flag; maritime, war-risk and listed-area series |
| Policy ledger | `backend/rasad/policy` | Graded observations (cost class, speaker, 6x6 grade, confidence) → stated and revealed tracks, divergence, change-points, silence |
| Indicator engine | `backend/rasad/engine` | Rule-evaluated indicators → Bayesian update with capped likelihood ratios → extremised panel aggregate → blended, committed forecast |
| Commitment log | `backend/rasad/engine/commitment.py` | SHA-256 hash chain over every committed forecast; verified on the Record page |
| Scoring | `backend/rasad/engine/scoring.py` | Brier, Brier skill against the status-quo base rate, calibration bins, by horizon |
| Connectors | `backend/rasad/pipelines/connectors` | UKMTO advisories, JMIC dashboards, IMF PortWatch, Lloyd's JWC circulars, OFAC and UK sanctions, State Department FMS notifications, state wires via RSS; each parser tested on a fixture |
| Extraction | `backend/rasad/extraction` | Lexicon extraction (Arabic, Farsi, English) that always works; optional Claude API or local open-weight model behind the same interface; everything lands in the verification queue |
| Briefs | `backend/rasad/briefs` | Two-to-three page brief per question in Arabic or English, PHIA yardstick bands, confidence stated separately; optional model polish that may not add a fact |
| Accounts | `backend/rasad/auth` | Users, roles, signed-cookie sessions, audit log, operator CLI |
| API | `backend/rasad/api` | FastAPI; serves the built front end; every route behind sign-in |
| Front end | `frontend/` | React, TypeScript, Tailwind; board, question page with evidence, position book, brief, record, verification queue, sources; full right-to-left Arabic |

## Run it locally

```bash
# backend (SQLite, no Docker)
cd backend
pip install -e ".[dev]"
python -m rasad.seed.load 2026-10-18        # seeds reference data, ledgers and a 30-day forecast history
uvicorn rasad.api.app:app --reload           # http://localhost:8000/api/status

# front end (dev server proxies /api to :8000)
cd ../frontend
npm install
npm run dev                                   # http://localhost:5173
```

Tests: `cd backend && pytest -q` (32 tests: engine, policy maths, every connector against its fixture, accounts and roles, the API end to end).

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
| analyst | Viewer, plus the verification queue (accept or reject extracted evidence, correct a stance score) and committing forecasts |
| admin | Analyst, plus user management and the audit log |

New accounts get a temporary password and must set their own on first sign-in. Every sign-in, verification decision, commit, brief and user change is written to the audit log with the user and IP. Passwords are PBKDF2-SHA256; sessions are signed cookies that expire after 12 hours; ten failed sign-ins in a quarter hour lock that username for the rest of it.

Bringing a team on, in order: give colleagues viewer access first so they read the board and briefs; promote the two who will own evidence to analyst and route all verification through them; keep admin to one person plus a deputy. Set `RASAD_PUBLIC_RECORD=true` only when the calibration record has real resolutions behind it.

## Demo data

The seed carries two kinds of rows and the `is_synthetic` flag separates them without exception. Sourced rows carry the facts behind the concept document (the 28 February 2026 strikes on all six GCC states, the Hormuz closure of 2 March, JWLA-033, the July collapse of the truce, the October Riyadh airport strike, the GCC summit decisions, the UK and US deployments and notifications) with a source and URL in `provenance`. Synthetic rows (the daily transit series shaped by PortWatch anchors, illustrative Iranian and American statements, a few October tanker attacks whose specifics are unconfirmed) exist to exercise the engine and are flagged in the UI, in every brief and in every indicator's evidence block. The banner stays up while any synthetic row is present.

The four resolved demo questions on the Record page were produced by replaying the engine on the seeded ledgers as of earlier dates with no tuning; the misses are shown as they fall.

## Model providers

`RASAD_MODEL_PROVIDER=rules` is the default and needs nothing. `anthropic` uses the Claude API for extraction and brief polish during development. `local` points at any OpenAI-compatible endpoint (vLLM or SGLang serving Jais 2, Fanar 2 or similar) for in-country deployment. The extraction prompt in `backend/rasad/extraction/prompts.py` never asks a model for a probability; it asks for rows with a quote, and an analyst accepts or rejects them.

## Where this goes next

1. Replace synthetic series with PortWatch (permission email on file) and the first bought feeds in the concept document's acquisition plan.
2. Fine-tune the Arabic and Farsi extractors on the verified corpus the queue builds; raise the review quota for the weaker languages.
3. Resolve the first live questions on their dates and let the Record page carry real skill numbers before any client sees it.
4. Arabic for decision hooks and resolution criteria in the seed (the briefs currently carry those in English).
5. Sovereign deployment: the same containers on Google Cloud Doha or the Meeza and Microsoft Azure Local private cloud; the stack has no outbound dependency except the allow-listed feeds.

## Layout

```
backend/rasad/   api  auth  briefs  engine  extraction  models  pipelines  policy  seed
backend/tests/
frontend/src/    pages  components.tsx  api.ts  auth.tsx  i18n.tsx
deploy/          install.sh  update.sh  Caddyfile  backup.sh
Dockerfile  docker-compose.yml  .env.example
```
