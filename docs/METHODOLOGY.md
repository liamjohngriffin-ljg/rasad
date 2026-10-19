# Rasad: methodology and assurance note

For a customer's analytic lead, security officer and procurement team. It says how a number on the board is produced, how it is checked, what the platform does with data, and where its limits are. Version 0.4.0, October 2026.

## 1. What the platform produces

A standing board of questions a principal has to decide on (for example: will commercial transits of the Strait of Hormuz fall below a quarter of their 2025 daily average for seven consecutive days within 90 days?). Each question carries:

- a probability, committed once a day and never edited afterwards;
- the words for that probability on the PHIA yardstick (remote chance, highly unlikely, unlikely, realistic possibility, likely, highly likely, almost certain), always shown beside the number;
- an analytical confidence (low, moderate, high), stated separately from the probability;
- the indicators that moved it, each with its evidence;
- the decisions the question informs and its resolution criteria, in Arabic and English;
- a brief of two to three pages, exportable to Word with the customer's protective marking.

When a question resolves, every forecast committed for it is scored and the score is published on the Record page.

## 2. How a probability is produced

Each question starts from a base rate: the status-quo probability over its horizon, with a written note of where it comes from.

Indicators update the base rate. An indicator is a rule evaluated against the ledgers (counts of reported incidents in a window, a transit or price series against a threshold or its own baseline, an actor's stated or revealed policy position, a divergence between the two, an actor going quiet, a change point) and two likelihood ratios: how much more likely its present state is if the outcome is coming than if it is not, and the same for its absent state. The machine estimate is the base rate's log-odds plus the sum of the log likelihood ratios of the observed states. Indicators whose state is unknown contribute nothing. Each contribution is capped at a factor of ten, so a mis-specified ratio cannot dominate and the decomposition stays readable.

Analysts add a panel estimate per question with a rationale. Each analyst's latest estimate counts for 21 days. The panel aggregate is the skill-weighted mean in log-odds with a mild extremising factor of 1.3 (the IARPA tournament literature fitted larger factors in-sample; a smaller one is the conservative choice), bounded between 2 and 98 percent. The spread of the panel is shown beside it.

The committed probability blends the machine estimate and the panel aggregate in log-odds, by default with equal weight. The weights are shown on the question page.

## 3. Evidence and its grading

Sources fall into three classes, and each row carries its grade (an adapted 6x6 scheme: a letter for the source, a number for the item):

- A: official publishers read by dedicated parsers: UKMTO warnings and advisories, JMIC dashboards and advisory notes, EUNAVFOR Atalanta and MSCIO weekly reports, IMF PortWatch transit counts, UK and US sanctions lists, Lloyd's Joint War Committee listed areas, government statements.
- B: established outlets and official wires.
- C: automated extraction from wires and news (GDELT, national news agencies), in Arabic, English and Farsi.

Grade A and B rows count in indicators as soon as they arrive. Grade C rows wait in the verification queue and count only after an analyst accepts them. Every accept and reject is recorded against the analyst's name.

Before rows reach the queue the platform removes duplication that would otherwise inflate counts:

- the same incident reported by several publishers (UKMTO, JMIC and the weekly report often describe one attack) is linked into one incident, by matching position anchors ("24NM north-west of Port Rashid") or, more cautiously, by a same-day, same-area, one-candidate rule that is labelled as probable. Indicators count incidents, not reports; analysts can split a wrong link and the platform never relinks it;
- syndicated copies of one story from different outlets are folded into one row with the other outlets listed;
- a wire's English and Arabic versions of one story are paired, and the counts in each must agree before they are paired;
- text with no Gulf or regional geography does not become a ledger event.

Rows created only to exercise the engine (demonstration data) carry a flag that is shown in every view, brief and export until live data replaces them.

## 4. The record

Every committed forecast is hashed with SHA-256 together with the hash of the commit before it, the question, the date, the probability and the full decomposition. The Record page re-verifies the whole chain on every view and raises an alert if any link fails.

A chain kept only in the platform's own database could be rebuilt by someone with database access. The platform therefore sends the day's chain head outside itself: to the team channel (Teams or Slack) and in the email digest. Those copies, held in systems the platform does not control, are what make the record tamper-evident.

Resolved questions are scored with the Brier score and with skill against the question's own base rate (one minus the ratio of the two Brier scores), which is the honest comparator for a warning system: a record that does not beat "nothing changes" is not worth reading. Calibration is shown in bins. The record is published as it falls, misses included.

## 5. What analysts and principals see

The board, a Today page of alerts (indicator flips, moves of ten points or more, severe incidents, transit breaks, resolutions due, any break in the record), the verification queue, the question pages with evidence, a position book of stated against revealed policy by actor and issue, a map, series charts, search in both languages, the briefs and a weekly situation brief. The interface is fully bilingual, right to left in Arabic.

## 6. Security controls

- Accounts with three roles (viewer, analyst, administrator). Passwords are stored as PBKDF2-SHA256 with 310,000 iterations. Sign-in attempts are throttled.
- Two-factor sign-in with any authenticator app (RFC 6238), single-use recovery codes and replay protection; an administrator can require it for every user, and the server then refuses every other request until the user enrols.
- Sessions are signed tokens in an HttpOnly cookie, ended on password change, administrator reset or deactivation, and on demand from the Account page. State-changing requests require a client header a cross-site form cannot send.
- API keys for integrations are shown once and stored only as a SHA-256 hash; they carry a role.
- Every sign-in and every change is in the audit log with the user, time and address.
- Outbound connections are limited to an allow-list of source hosts; the team channel address must be HTTPS and must not resolve to an internal address.
- The reverse proxy serves TLS with HSTS, refuses framing and path traversal, and hides server identification.
- The platform's own code has an automated test suite (engine, connectors against real documents, accounts, roles, licensing, the API end to end) that runs against both SQLite and PostgreSQL.

## 7. Deployment and sovereignty

The platform is five containers (PostgreSQL, the application, the Caddy reverse proxy, the scheduler, nightly backups) and runs on the customer's own server or private cloud, including in-country regions. It needs no outbound connection except to the allow-listed sources, and it can run fully air-gapped with documents loaded from a folder. Model-assisted extraction is optional and can use an open-weight Arabic model served inside the customer's network; nothing is sent to a model provider unless the customer turns that on. Backups are nightly PostgreSQL dumps with a retention window and a tested restore script that takes a safety copy first.

## 8. Licensing

A signed licence file (Ed25519) sets the licensee, seats, expiry and modules: core, Arabic, bulk export, API and team channel, model-assisted extraction. The server enforces each module. An expired licence gives a 30-day grace period.

## 9. Limits

- Lexicon extraction from wires is crude by design and is a triage aid; grade C rows count only after an analyst accepts them. Model-assisted extraction improves recall but is still reviewed.
- Likelihood ratios are elicited judgements until enough questions have resolved to fit them; the decomposition is shown so they can be challenged.
- A probability is only as good as the question: resolution criteria must be checkable from named sources on a named date.
- Open sources see what is published. Customer reporting can be entered as evidence, with its own grade, and is then counted like any other row.
- The skill record means little until dozens of questions have resolved; until then the record shows its sample size.
