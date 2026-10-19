# Third-party data and components

Rasad reads public sources through connectors and ships a snapshot of rows derived from
them. Each source keeps its own terms; this file records them so an operator can confirm
their deployment is within them. Nothing here is legal advice.

| Source | Used for | Terms |
| --- | --- | --- |
| IMF PortWatch (UN Global Platform AIS) | Daily chokepoint transits since 2024 | Attribution required; commercial reuse by permission (portwatch.imf.org) |
| UKMTO warnings and advisories | Maritime incidents | Free PDFs published for mariners; no reuse statement |
| JMIC (Combined Maritime Forces / MSCIO) dashboards and advisory notes | Threat levels, incident counts, S&P AIS transit tables reproduced in the notes | Released to the shipping industry; no reuse statement; S&P figures are as published by JMIC |
| EUNAVFOR Atalanta / MSCIO weekly reports | Incident counts and incidents in the Voluntary Reporting Area | Releasable to shipping industry |
| UK Sanctions List (FCDO) | Designations | Open Government Licence v3 |
| UK government news (gov.uk) | Policy observations | Open Government Licence v3 |
| Qatar News Agency | Policy observations | All rights reserved; RSS feeds consumed for analysis, text stored for verification only |
| GDELT 2.0 DOC API | Article discovery and routing | Free for use with attribution |
| OFAC SDN, US State Department FMS notifications | Designations, notifications (where reachable) | US government works |
| Lloyd's Joint War Committee circulars | Listed areas | Published by Lloyd's Market Association |
| Natural Earth | Land polygons on the map | Public domain |
| Wikipedia and press reporting cited in the seed | Curated events and observations in the concept record | Cited by URL in each row's provenance |

Software components: FastAPI, SQLAlchemy, pydantic, httpx, pdfplumber, feedparser, python-docx, cryptography, psycopg, numpy (Python), React, react-router, Tailwind CSS, Vite, TypeScript (front end), Caddy and PostgreSQL (deployment). Each is used under its published open-source licence; the licence texts are in the installed packages.
