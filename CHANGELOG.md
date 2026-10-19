# Changelog

## 0.4.0 (19 October 2026)

Analytical integrity
- Cross-source incident linking: when UKMTO, JMIC and the MSCIO weekly report describe the same attack, the reports are linked (by position anchor, or as a labelled probable link on the same day and area). Indicators count incidents rather than reports, alerts fire once per incident, and one verification decision covers every report. Analysts can detach a report or link one by hand; their decisions are never overridden.
- UKMTO updates no longer repeat the original narrative; stored rows and the shipped snapshot repaired on upgrade.

Security
- Two-factor sign-in with any authenticator app (RFC 6238), QR enrolment, eight single-use recovery codes, replay protection.
- Organisation policy to require two-factor sign-in, enforced by the server: without a second factor a user reaches only the Account page.
- Sessions end on password change, admin reset or deactivation; "sign out everywhere else" on the Account page; administrators can reset a lost second factor.

Analysts
- Analyst guide in English and Arabic inside the app (the ? beside your name).
- Weekly situation brief (Board, Word export), series explorer with events on the same axis, Arabic resolution criteria and decision hooks, as-of date on the Board.
- Verification queue grouped by incident with publisher badges.

Operations
- Whole suite runs against PostgreSQL 16 (RASAD_TEST_DATABASE_URL); live pipeline verified on PostgreSQL.
- `python -m rasad.doctor` readiness report; `run link` upgrade step (the Windows launcher runs it on every start); SQLite online backups in the daily pipeline.

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
