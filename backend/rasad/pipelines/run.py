"""Operator CLI.

  python -m rasad.pipelines.run poll      fetch every configured feed (runs on the host that may reach the sources)
  python -m rasad.pipelines.run extract   turn ingested documents into pending events and observations
  python -m rasad.pipelines.run commit    commit today's forecasts to the chain
  python -m rasad.pipelines.run daily     all three, in order

Source URLs for PDFs (UKMTO advisories, JWC circulars, JMIC dashboards) are listed in
RASAD_DATA_DIR/urls.yaml so the operator can add new ones without a deploy.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import yaml

from ..config import get_settings
from ..db import init_db, session_factory
from ..engine import run as engine_run
from ..extraction import service as extraction
from .connectors import jmic, jwc, portwatch, rss_wires, sanctions, state_fms, ukmto

DEFAULT_URLS = {
    "portwatch_csv": None,  # set to the PortWatch daily export URL once permission is on file
    "ofac_sdn_csv": "https://sanctionslist.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV",
    "ofac_add_csv": "https://sanctionslist.ofac.treas.gov/api/PublicationPreview/exports/ADD.CSV",
    "state_fms_listing": "https://www.state.gov/arms-sales-congressional-notifications/",
    "ukmto_advisories": [],
    "jwc_circulars": [],
    "jmic_dashboards": [],
    "rss": ["qna", "adm"],
    "allow_sanctioned_feeds": False,
}


def load_urls() -> dict:
    path = os.path.join(get_settings().data_dir, "urls.yaml")
    cfg = dict(DEFAULT_URLS)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(yaml.safe_load(f) or {})
    return cfg


def poll() -> dict:
    cfg = load_urls()
    db = session_factory()()
    report: dict = {}
    try:
        if cfg.get("portwatch_csv"):
            report["portwatch"] = portwatch.fetch_and_ingest(db, cfg["portwatch_csv"])
        if cfg.get("ofac_sdn_csv"):
            try:
                report["ofac"] = sanctions.fetch_and_ingest_ofac(db, cfg["ofac_sdn_csv"], cfg.get("ofac_add_csv"), date.today())
            except Exception as exc:  # noqa: BLE001
                report["ofac_error"] = str(exc)
        if cfg.get("state_fms_listing"):
            try:
                report["state_fms"] = state_fms.fetch_and_ingest(db, cfg["state_fms_listing"])
            except Exception as exc:  # noqa: BLE001
                report["state_fms_error"] = str(exc)
        if cfg.get("ukmto_advisories"):
            report["ukmto"] = ukmto.fetch_and_ingest(db, cfg["ukmto_advisories"])
        for url in cfg.get("jwc_circulars") or []:
            report.setdefault("jwc", []).append(jwc.fetch_and_ingest(db, url)["circular"])
        for url in cfg.get("jmic_dashboards") or []:
            report.setdefault("jmic", []).append(jmic.fetch_and_ingest(db, url)["week"])
        for code in cfg.get("rss") or []:
            try:
                report[f"rss_{code}"] = rss_wires.fetch_and_ingest(db, code, allow_sanctioned=bool(cfg.get("allow_sanctioned_feeds")))
            except Exception as exc:  # noqa: BLE001
                report[f"rss_{code}_error"] = str(exc)
    finally:
        db.close()
    return report


def extract() -> dict:
    db = session_factory()()
    try:
        return extraction.process_pending(db)
    finally:
        db.close()


def commit(as_of: date | None = None) -> dict:
    db = session_factory()()
    try:
        out = engine_run.commit_all_open(db, as_of or date.today())
        return {f.question.code: f.final_prob for f in out}
    finally:
        db.close()


def main(argv: list[str]) -> None:
    init_db()
    cmd = argv[0] if argv else "daily"
    if cmd == "poll":
        print(poll())
    elif cmd == "extract":
        print(extract())
    elif cmd == "commit":
        print(commit(date.fromisoformat(argv[1]) if len(argv) > 1 else None))
    elif cmd == "daily":
        print(poll())
        print(extract())
        print(commit())
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
