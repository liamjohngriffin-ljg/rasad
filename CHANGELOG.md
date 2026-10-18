# Changelog

## 0.3.0 (18 October 2026)

Live data
- IMF PortWatch chokepoint transits (Hormuz, Bab el-Mandeb, Suez, Cape; cargo and tanker) from the public ArcGIS service, backfilled since January 2024.
- MSCIO library connector: UKMTO warnings and advisories, JMIC weekly dashboards and advisory notes, EUNAVFOR Atalanta weekly reports; each layout parsed from the real PDFs, with incident numbers, positions and threat levels.
- UK Sanctions List, GDELT standing queries (rate limited), QNA English and Arabic feeds, UK government feeds (FCDO, MOD, No.10).
- Seed snapshot of real rows shipped with the code; synthetic shaping generated only where no sourced series exists.

Analyst workflows
- Question and indicator editing with rule validation and a live preview against the ledgers; new reference indicators appended on upgrade without touching analyst edits.
- Panel forecasts per analyst, evidence entry (events, observations, series values), resolution, tasking from open to framed to answered.
- Verification queue filters by grade and source with bulk accept or reject.

Daily use
- Alerts (indicator flips, forecast moves, severe events, transit breaks, chain failures, resolutions due) with acknowledgement and an optional email digest; Today page.
- Search across events, observations and documents; document reader; related documents per question; map of events with land from Natural Earth.
- Brief export to Word with a configurable marking; Sources page with document counts, last fetch and series freshness.

Product
- Ed25519 licence files (seats, features, expiry, grace); evaluation mode; API keys as bearer tokens; branding and marking settings; CSV and JSON exports; Administration page.
- Client header required on cookie-session writes; forward-only column catch-up on upgrade; scheduler polls every few hours and commits daily.

## 0.2.0
- Accounts and roles, audit log, production deployment (Docker Compose, Caddy, backups), Windows launcher.

## 0.1.0
- Vertical slice: ledgers, indicator engine, panel aggregation, commitment chain, scoring, position book, briefs, front end in Arabic and English.
