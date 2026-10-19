"""Readiness check for operators and support: `python -m rasad.doctor`.

Reports the database, licence, the egress allow-list with a reachability probe per host, the
last fetch per source, series freshness for the watched series, the commitment chain, pending
verification counts and the scheduler settings. Exit status is 1 when something a deployment
depends on is wrong (database unreachable, chain broken, licence rejected).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime

import httpx
from sqlalchemy import func, select

from . import __version__, licence
from .config import get_settings
from .db import init_db, session_factory
from .engine.commitment import verify_chain
from .models import Alert, Document, Forecast, PolicyObservation, SeriesPoint, Source, ThreatEvent

WATCHED = ("hormuz_transits", "bab_el_mandeb_transits", "jmic_regional_threat_level", "war_risk_premium_hormuz_pct")
PROBES = {
    "services9.arcgis.com": "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/Daily_Chokepoints_Data/FeatureServer/0?f=json",
    "mscio.eu": "https://mscio.eu/advisories/",
    "sanctionslist.fcdo.gov.uk": "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.csv",
    "api.gdeltproject.org": "https://api.gdeltproject.org/api/v2/doc/doc?query=hormuz&mode=artlist&format=json&maxrecords=1",
    "qna.org.qa": "https://qna.org.qa/en/Pages/RSS-Feeds/Qatar",
    "www.gov.uk": "https://www.gov.uk/search/news-and-communications.atom?organisations%5B%5D=ministry-of-defence",
    "sanctionslist.ofac.treas.gov": "https://sanctionslist.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV",
    "www.state.gov": "https://www.state.gov/arms-sales-congressional-notifications/",
}


def run(probe: bool = True) -> dict:
    s = get_settings()
    report: dict = {"version": __version__, "database_url": s.database_url.split("@")[-1] if "@" in s.database_url else s.database_url, "data_dir": s.data_dir, "model_provider": s.model_provider, "ok": True, "problems": []}
    try:
        init_db()
        db = session_factory()()
    except Exception as exc:  # noqa: BLE001
        report["ok"] = False
        report["problems"].append(f"database: {exc}")
        return report
    try:
        st = licence.current(refresh=True)
        report["licence"] = st.as_dict()
        if st.mode == "evaluation" and st.reason and "rejected" in st.reason:
            report["ok"] = False
            report["problems"].append(st.reason)
        report["counts"] = {
            "events": db.scalar(select(func.count(ThreatEvent.id))), "events_pending": db.scalar(select(func.count(ThreatEvent.id)).where(ThreatEvent.verification == "pending")),
            "observations": db.scalar(select(func.count(PolicyObservation.id))), "series_points": db.scalar(select(func.count(SeriesPoint.id))),
            "documents": db.scalar(select(func.count(Document.id))), "forecasts": db.scalar(select(func.count(Forecast.id))),
            "alerts_open": db.scalar(select(func.count(Alert.id)).where(Alert.acknowledged_at.is_(None))),
        }
        rows = [{"prev_hash": r.prev_hash, "question_code": r.question.code, "as_of": r.as_of, "final_prob": r.final_prob, "decomposition": r.decomposition, "commit_hash": r.commit_hash} for r in db.scalars(select(Forecast).order_by(Forecast.id))]
        ok, bad = verify_chain(rows)
        last = db.scalar(select(func.max(Forecast.as_of)))
        report["chain"] = {"length": len(rows), "verified": ok, "first_bad_index": bad, "last_commit": last.isoformat() if last else None}
        if not ok:
            report["ok"] = False
            report["problems"].append(f"commitment chain fails at index {bad}")
        if last and (date.today() - last).days > 2:
            report["problems"].append(f"last commit was {last.isoformat()}; the scheduler may not be running")
        srcs = []
        for src in db.scalars(select(Source).order_by(Source.code)):
            n, last_fetch = db.execute(select(func.count(Document.id), func.max(Document.fetched_at)).where(Document.source_id == src.id)).one()
            srcs.append({"source": src.code, "documents": n, "last_fetched": last_fetch.isoformat(timespec="minutes") if last_fetch else None})
        report["sources"] = srcs
        fresh = []
        for name in WATCHED:
            p = db.scalar(select(SeriesPoint).where(SeriesPoint.series == name).order_by(SeriesPoint.date.desc()).limit(1))
            fresh.append({"series": name, "last": p.date.isoformat() if p else None, "days_stale": (date.today() - p.date).days if p else None})
        report["series"] = fresh
    finally:
        db.close()
    report["scheduler"] = {"pipeline_time": os.getenv("RASAD_PIPELINE_TIME", "06:00"), "poll_interval_hours": os.getenv("RASAD_POLL_INTERVAL_HOURS", "4"), "tz": os.getenv("TZ", "container time")}
    report["egress_allowlist"] = s.egress_allowlist
    if probe:
        probes = []
        for host, url in PROBES.items():
            if not any(host == h or host.endswith("." + h) for h in s.egress_allowlist):
                probes.append({"host": host, "status": "not on allow-list"})
                continue
            try:
                with httpx.stream("GET", url, timeout=20, follow_redirects=True, headers={"User-Agent": "rasad/doctor"}) as r:
                    probes.append({"host": host, "status": str(r.status_code)})  # headers only; large files are not downloaded
            except Exception as exc:  # noqa: BLE001
                probes.append({"host": host, "status": f"{type(exc).__name__}"})
        report["reachability"] = probes
    report["checked_at"] = datetime.utcnow().isoformat(timespec="seconds")
    return report


def main(argv: list[str]) -> None:
    rep = run(probe="--no-probe" not in argv)
    print(json.dumps(rep, indent=1, default=str))
    sys.exit(0 if rep["ok"] else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
