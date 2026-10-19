# Analyst guide

Rasad keeps a standing board of questions a principal has to decide on, each with a calibrated probability that is traceable to evidence, committed daily to a tamper-evident record and scored when the question resolves. This guide covers the daily routine and every workflow an analyst or administrator needs.

## The daily routine

- Start on Today. It lists open alerts (indicator flips, forecast moves of ten points or more, severe events, transit breaks, resolutions due, any break in the record), the board's moves since yesterday and the newest events. Acknowledge an alert once you have read it; the count in the navigation bar falls to zero when everything is read.
- Clear the Verification queue next (analysts and administrators). Connector rows from official publishers arrive as grade A or B and already count in the indicators; extractions from wires and news arrive as grade C and count only once accepted.
- Enter your panel estimate on any question you own when the evidence has moved you, with a line of reasoning.
- Read the Board last. Each card shows the committed probability, its yardstick words, the change on the day and a 90-day line.

The scheduler polls the feeds every few hours and runs the full pipeline once a day (06:00 by default): poll, extract, link incidents, commit forecasts, raise alerts, send the email digest, back up.

## Reading a question

- The headline number is the blend of the machine estimate (indicators applied to the base rate) and the panel aggregate. The weights are shown on the page.
- Words follow the PHIA probability yardstick: remote chance (under about 7 percent), highly unlikely (about 10 to 20), unlikely (25 to 35), realistic possibility (40 to 50), likely (55 to 75), highly likely (80 to 90), almost certain (95 and above). The number is always shown beside the words. Analytical confidence (low, moderate, high) is stated separately and reflects how much independent evidence sits under the number.
- Every indicator shows its state (present, absent, unknown), its contribution in log-odds and the evidence that set it: the events, the series values or the policy observations. No single indicator can move an estimate by more than a factor of ten.
- Rows marked demo are illustrative and are flagged in every view and brief until live data replaces them.

## The verification queue

- Each item is one incident. When UKMTO, JMIC and the MSCIO weekly report all describe the same attack, the reports are linked and shown together under "Also reported by"; one decision covers all of them, and indicators count the incident once.
- Links are made automatically in two ways: by position (the same distance and reference point, such as 24NM north-west of Port Rashid, on the same or next day) or as a probable link (same day, same area, and each report is the other publisher's only candidate). Probable links say so.
- If two linked reports are different incidents, press Detach on the report that stands alone. Detached reports are never relinked automatically.
- Accept confirms a row; Reject removes it from every count and alert. Both are recorded against your name in the audit log.
- Filters: connectors (grade A and B), extractions (grade C) or all, and by publisher. Accept all shown and Reject all shown apply to the filtered list.
- For policy observations, check the stance score (minus one to plus one) and correct it with the slider before accepting.

## Grades

Source grades follow an adapted 6x6 scheme: a letter for the reliability of the source (A official publisher, B established outlet, C wire or automated extraction) and a number for the credibility of the item. Grades are set by the connector and can be read in each row's provenance.

## Questions and indicators (analysts)

- Questions sets the title in English and Arabic, the horizon, the base rate with its note, the resolution criteria and the decision hooks (both languages), and the indicators.
- An indicator is a rule plus two likelihood ratios. Rule types: event count (events of given types, countries, actors or severity in a window, against a threshold), series threshold and series change (a transit or price series against a level or its own baseline), position level and divergence (stated and revealed policy for an actor on an issue), silence (an actor saying less than usual) and change point (a shift in an actor's position).
- Preview evaluates a rule against the ledgers before you save it, so you can see whether it would be present today and on what evidence.
- A question resolves on its date or earlier when the criteria are met; resolution freezes it and its forecasts are scored on the Record page.

## Panel estimates

- Each analyst enters a probability and a short rationale per question. The panel aggregate is taken in log-odds with a modest extremising factor and shown with its spread.
- Enter when your view changes, not every day. Each analyst's latest estimate counts, weighted by that analyst's skill record, for 21 days; an estimate older than that drops out of the aggregate, so refresh it at least every three weeks.

## Evidence entry (analysts)

Use Evidence to add what the feeds cannot see: an event you know from a trusted channel, a policy observation from a meeting readout, a series value from a bought dataset. Every row records who entered it and when.

## Briefs

- Each question has a two to three page brief in Arabic or English: bottom line, the indicators that moved, the evidence, the panel view, decision hooks and resolution criteria. Download it as Word with the marking in the header and footer.
- The Weekly brief (from the Board) summarises the whole board, the week's moves and the reported incidents in one document.

## Position book

For each actor and issue, the stated track (what is said, weighted by speaker level and channel) and the revealed track (what is done, weighted by cost), and the divergence between them. A widening divergence is often the earliest sign of a change of course.

## The record

Every committed forecast is chained by SHA-256 to the one before it. The Record page verifies the whole chain and shows Brier scores and skill against the base rate for resolved questions. A broken chain raises an alert.

## Tasking

Anyone can raise a request (an open question from a principal). Analysts frame it into a question with criteria, or answer it directly; the requester sees the status.

## Search, map, series and sources

- Search covers events, policy observations and stored documents in both languages.
- Map shows events with a reported position as filled markers and events known only by area as hollow markers near the area's centre; dashed outlines are not yet verified.
- Series plots any transit or price series with its seven-day mean and the reported events of chosen types on the same axis.
- Sources lists every feed with its document count and last fetch, and every series with its span and days since the last point. Stale series appear in red.

## Your account

- Change your password on the Account page; doing so signs out every other session.
- Turn on two-factor sign-in: scan the QR code with an authenticator app (Microsoft Authenticator, Google Authenticator, 1Password), enter the code, and store the eight recovery codes offline. Each recovery code works once if the phone is lost.
- Sign out everywhere else ends every other browser session at once.

## Administration (administrators)

- Users: add users with a temporary password (they must change it at first sign-in), set the role (viewer reads; analyst verifies, edits questions and enters evidence; admin also manages users, licence, keys and settings), reset a password, reset two-factor sign-in for a lost phone, deactivate. The audit log lists every sign-in and every change.
- Settings: organisation and product name, marking, accent colour, logo, footer note, digest recipients, and the switch that requires two-factor sign-in for every user. With it on, a user without a second factor can reach only the Account page until they enrol.
- Team channel: paste a Microsoft Teams Workflows webhook (template "Post to a channel when a webhook request is received") or a Slack incoming webhook, choose the minimum severity, save, then Send a test message. New alerts are posted after every poll and every daily commit, each once, with links back to the platform when the public address is set. The address is treated as a credential and hidden from everyone but administrators.
- Licence: shows the licensee, seats, features and expiry; install a new licence file here. Without a licence the platform runs in evaluation mode with three seats.
- API keys: bearer tokens for BI tools, a SIEM or scripts (Authorization: Bearer rsk_...). Viewer keys read; analyst keys may also write evidence. The key is shown once.
- Exports: events, observations, series and the forecast log as CSV (opens in Excel), and the forecast log as JSON for independent verification of the chain.

## Operations

- python -m rasad.doctor prints a readiness report (database, licence, chain, source freshness, reachability of every feed) and exits non-zero when something is broken. Support asks for its output first.
- python -m rasad.pipelines.run daily runs the full pipeline by hand; link relinks incidents over the whole record; backup copies a SQLite database into the data folder (PostgreSQL deployments use the backup container).
- Feeds are configured in urls.yaml in the data folder; the platform refuses any host not on the egress allow-list.
