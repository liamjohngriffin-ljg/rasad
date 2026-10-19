"""Operator CLI.

  python -m rasad.pipelines.run poll        fetch every configured feed (runs on the host that may reach the sources)
  python -m rasad.pipelines.run extract     turn ingested documents into pending events and observations
  python -m rasad.pipelines.run commit      commit today's forecasts to the chain
  python -m rasad.pipelines.run daily       all three, in order, then the alert digest
  python -m rasad.pipelines.run digest      email unacknowledged alerts (RASAD_SMTP_HOST, RASAD_DIGEST_TO)
  python -m rasad.pipelines.run backup [keep]   SQLite online backup into <data dir>/backups (default keeps 30)
  python -m rasad.pipelines.run link        relink reports of one incident across publishers (whole record)
  python -m rasad.pipelines.run backfill    first run: PortWatch since 2024, every MSCIO folder, the sanctions lists
  python -m rasad.pipelines.run ingest-dir <path> [folder]   ingest a directory of PDFs (air-gapped hosts)
  python -m rasad.pipelines.run snapshot [path]              export real ledger rows to the seed snapshot

Feeds are configured in RASAD_DATA_DIR/urls.yaml so the operator can add, disable or point
sources elsewhere without a deploy. Keys and defaults are in DEFAULT_URLS below.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import yaml

from ..config import get_settings
from ..db import init_db, session_factory
from ..engine import alerts as alert_engine
from ..engine import incidents
from ..engine import run as engine_run
from ..extraction import service as extraction
from .connectors import gdelt, jmic, jwc, mscio, portwatch, rss_wires, sanctions, state_fms, uk_sanctions, ukmto

DEFAULT_URLS = {
    "portwatch": True,  # IMF PortWatch chokepoint transits via the public ArcGIS service
    "portwatch_csv": None,  # or a hand-downloaded export
    "portwatch_days": 120,
    "mscio": True,  # UKMTO warnings and advisories, JMIC dashboards and notes from mscio.eu
    "mscio_folders": None,  # None = all; or a list such as ["ukmto_warnings", "jmic_dashboards"]
    "uk_sanctions": True,
    "gdelt": True,
    "gdelt_timespan": "3d",
    "ofac_sdn_csv": "https://sanctionslist.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV",
    "ofac_add_csv": "https://sanctionslist.ofac.treas.gov/api/PublicationPreview/exports/ADD.CSV",
    "state_fms_listing": "https://www.state.gov/arms-sales-congressional-notifications/",
    "ukmto_advisories": [],  # extra PDF URLs beyond the MSCIO listing
    "jwc_circulars": [],
    "jmic_dashboards": [],
    "rss": ["qna", "qna_ar", "ukgov"],
    "allow_sanctioned_feeds": False,
}


def load_urls() -> dict:
    path = os.path.join(get_settings().data_dir, "urls.yaml")
    cfg = dict(DEFAULT_URLS)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(yaml.safe_load(f) or {})
    return cfg


def _try(report: dict, key: str, fn):
    try:
        report[key] = fn()
    except Exception as exc:  # noqa: BLE001
        report[f"{key}_error"] = f"{type(exc).__name__}: {exc}"[:300]


def poll(*, backfill: bool = False) -> dict:
    cfg = load_urls()
    db = session_factory()()
    report: dict = {}
    try:
        if cfg.get("portwatch_csv"):
            _try(report, "portwatch_csv", lambda: portwatch.fetch_and_ingest_csv(db, cfg["portwatch_csv"]))
        elif cfg.get("portwatch"):
            since = date(2024, 1, 1) if backfill else date.today() - timedelta(days=int(cfg.get("portwatch_days") or 120))
            _try(report, "portwatch", lambda: portwatch.ingest_rows(db, portwatch.fetch_rows(since)))
        if cfg.get("mscio"):
            folders = cfg.get("mscio_folders") or None
            _try(report, "mscio", lambda: mscio.poll(db, folders=folders, since=None if backfill else date.today() - timedelta(days=45)))
        if cfg.get("uk_sanctions"):
            _try(report, "uk_sanctions", lambda: uk_sanctions.fetch_and_ingest(db))
        if cfg.get("ofac_sdn_csv"):
            _try(report, "ofac", lambda: sanctions.fetch_and_ingest_ofac(db, cfg["ofac_sdn_csv"], cfg.get("ofac_add_csv"), date.today()))
        if cfg.get("state_fms_listing"):
            _try(report, "state_fms", lambda: state_fms.fetch_and_ingest(db, cfg["state_fms_listing"]))
        if cfg.get("gdelt"):
            _try(report, "gdelt", lambda: gdelt.fetch_and_ingest(db, timespan=str(cfg.get("gdelt_timespan") or "3d")))
        if cfg.get("ukmto_advisories"):
            _try(report, "ukmto_extra", lambda: ukmto.fetch_and_ingest(db, cfg["ukmto_advisories"]))
        for url in cfg.get("jwc_circulars") or []:
            _try(report, f"jwc:{url.rsplit('/', 1)[-1]}", lambda u=url: jwc.fetch_and_ingest(db, u)["circular"])
        for url in cfg.get("jmic_dashboards") or []:
            _try(report, f"jmic:{url.rsplit('/', 1)[-1]}", lambda u=url: jmic.fetch_and_ingest(db, u)["week"])
        for code in cfg.get("rss") or []:
            _try(report, f"rss_{code}", lambda c=code: rss_wires.fetch_and_ingest(db, c, allow_sanctioned=bool(cfg.get("allow_sanctioned_feeds"))))
        _try(report, "ukmto_tidy", lambda: ukmto.tidy_descriptions(db))
        _try(report, "incidents", lambda: incidents.link(db))
        _try(report, "alerts", lambda: alert_engine.after_poll(db))
    finally:
        db.close()
    return report


def extract(limit: int | None = None) -> dict:
    """Rules extraction is cheap, so the whole backlog goes in one run; a model provider works
    in batches of RASAD_EXTRACT_BATCH (default 200) so a stalled endpoint cannot hold the day."""
    db = session_factory()()
    try:
        if limit is None:
            limit = 100000 if get_settings().model_provider == "rules" else int(os.getenv("RASAD_EXTRACT_BATCH", "200"))
        return extraction.process_pending(db, limit=limit)
    finally:
        db.close()


def commit(as_of: date | None = None) -> dict:
    db = session_factory()()
    try:
        out = engine_run.commit_all_open(db, as_of or date.today())
        raised = alert_engine.after_commit(db, out)
        return {"alerts": raised, **{f.question.code: f.final_prob for f in out}}
    finally:
        db.close()


def backup(keep: int = 30) -> dict:
    """SQLite deployments (laptop, single host): copy the database with the online backup API
    into <data dir>/backups and keep the newest `keep` copies. PostgreSQL deployments use the
    backup container (pg_dump) instead."""
    import shutil
    import sqlite3

    url = get_settings().database_url
    if not url.startswith("sqlite"):
        return {"skipped": "not a SQLite database; the compose backup service runs pg_dump"}
    src = url.replace("sqlite:///", "", 1)
    if not os.path.exists(src):
        return {"skipped": f"{src} not found"}
    out_dir = os.path.join(get_settings().data_dir, "backups")
    os.makedirs(out_dir, exist_ok=True)
    stamp = date.today().isoformat()
    dest = os.path.join(out_dir, f"rasad-{stamp}.db")
    with sqlite3.connect(src) as con, sqlite3.connect(dest) as bak:
        con.backup(bak)
    olds = sorted(f for f in os.listdir(out_dir) if f.startswith("rasad-") and f.endswith(".db"))
    removed = []
    for f in olds[:-keep] if len(olds) > keep else []:
        os.remove(os.path.join(out_dir, f))
        removed.append(f)
    free = shutil.disk_usage(out_dir).free // (1024 * 1024)
    return {"backup": dest, "size_mb": round(os.path.getsize(dest) / (1024 * 1024), 1), "kept": min(len(olds), keep), "removed": removed, "free_mb": free}


def link_incidents() -> dict:
    """Relink reports of the same incident across publishers over the whole record."""
    db = session_factory()()
    try:
        return incidents.link(db, since=date(2024, 1, 1))
    finally:
        db.close()


def digest() -> dict:
    db = session_factory()()
    try:
        return alert_engine.send_digest(db)
    finally:
        db.close()


def ingest_dir(path: str, folder_hint: str = "local") -> dict:
    db = session_factory()()
    try:
        return mscio.ingest_directory(db, path, folder_hint=folder_hint)
    finally:
        db.close()


def snapshot(path: str | None = None) -> dict:
    from ..seed import snapshot as snap

    db = session_factory()()
    try:
        return snap.export(db, path)
    finally:
        db.close()


def main(argv: list[str]) -> None:
    init_db()
    cmd = argv[0] if argv else "daily"
    if cmd == "poll":
        print(poll())
    elif cmd == "backfill":
        print(poll(backfill=True))
        print(link_incidents())
    elif cmd == "link":
        print(link_incidents())
    elif cmd == "extract":
        print(extract())
    elif cmd == "commit":
        print(commit(date.fromisoformat(argv[1]) if len(argv) > 1 else None))
    elif cmd == "daily":
        print(poll())
        print(extract())
        print(commit())
        print(digest())
    elif cmd == "digest":
        print(digest())
    elif cmd == "backup":
        print(backup(int(argv[1]) if len(argv) > 1 else 30))
    elif cmd == "ingest-dir":
        print(ingest_dir(argv[1], argv[2] if len(argv) > 2 else "local"))
    elif cmd == "snapshot":
        print(snapshot(argv[1] if len(argv) > 1 else None))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
