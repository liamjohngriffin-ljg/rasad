"""IMF PortWatch chokepoint transits, read from the public ArcGIS feature service.

PortWatch publishes daily transit calls per chokepoint from UN Global Platform AIS, with an
observed lag of about a week and revisions. Attribution is required and commercial reuse
needs emailed permission (IMF terms), so every row records the source and the operator keeps
the permission on file. The counts are the authority for the series, so rows are not
synthetic and need no analyst verification. The CSV path is kept for exports the operator
downloads by hand.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import SeriesPoint
from .base import fetch_text

SERVICE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query"
ATTRIBUTION = "IMF PortWatch (UN Global Platform AIS)"

# PortWatch portid -> series prefix
CHOKEPOINTS = {
    "chokepoint6": "hormuz",
    "chokepoint4": "bab_el_mandeb",
    "chokepoint1": "suez",
    "chokepoint7": "cape_of_good_hope",
}
NAME_TO_ID = {
    "strait of hormuz": "chokepoint6",
    "bab el-mandeb strait": "chokepoint4",
    "bab el mandeb": "chokepoint4",
    "suez canal": "chokepoint1",
    "cape of good hope": "chokepoint7",
}


def _rows_from_features(features: list[dict]) -> list[tuple[str, date, float]]:
    out = []
    for f in features:
        a = f.get("attributes", {})
        pid = a.get("portid") or NAME_TO_ID.get((a.get("portname") or "").lower())
        prefix = CHOKEPOINTS.get(pid)
        raw = a.get("date")
        if prefix is None or raw is None:
            continue
        d = datetime.utcfromtimestamp(raw / 1000).date() if isinstance(raw, (int, float)) else date.fromisoformat(str(raw)[:10])
        if a.get("n_total") is not None:
            out.append((f"{prefix}_transits", d, float(a["n_total"])))
        if a.get("n_tanker") is not None:
            out.append((f"{prefix}_tanker_transits", d, float(a["n_tanker"])))
    return out


def fetch_rows(since: date, until: date | None = None, *, portids: list[str] | None = None) -> list[tuple[str, date, float]]:
    """Page through the feature service for the chosen chokepoints from `since`."""
    ids = portids or list(CHOKEPOINTS)
    until = until or date.today()
    rows: list[tuple[str, date, float]] = []
    for pid in ids:
        offset = 0
        while True:
            where = f"portid='{pid}' AND date >= DATE '{since.isoformat()}' AND date <= DATE '{until.isoformat()}'"
            params = {
                "where": where, "outFields": "date,portid,portname,n_total,n_tanker", "orderByFields": "date ASC",
                "returnGeometry": "false", "resultOffset": str(offset), "resultRecordCount": "1000", "f": "json",
            }
            url = SERVICE + "?" + "&".join(f"{k}={v}" for k, v in params.items()).replace(" ", "%20").replace("'", "%27")
            data = json.loads(fetch_text(url, timeout=60))
            if "error" in data:
                raise RuntimeError(f"PortWatch query failed: {data['error']}")
            feats = data.get("features", [])
            rows.extend(_rows_from_features(feats))
            if len(feats) < 1000 or not data.get("exceededTransferLimit", False):
                break
            offset += len(feats)
    return rows


def parse_csv(text: str) -> list[tuple[str, date, float]]:
    """Hand-downloaded export (columns vary; accept the common spellings)."""
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        name = (row.get("portname") or row.get("chokepoint") or row.get("name") or "").strip().lower()
        pid = row.get("portid") or NAME_TO_ID.get(name)
        prefix = CHOKEPOINTS.get(pid or "")
        if prefix is None:
            continue
        raw_date = row.get("date") or row.get("Date")
        raw_val = row.get("n_total") or row.get("total") or row.get("transits")
        if not raw_date or raw_val in (None, ""):
            continue
        try:
            d = date.fromisoformat(raw_date[:10])
            out.append((f"{prefix}_transits", d, float(raw_val)))
            if row.get("n_tanker") not in (None, ""):
                out.append((f"{prefix}_tanker_transits", d, float(row["n_tanker"])))
        except ValueError:
            continue
    return out


def ingest_rows(db: Session, rows: list[tuple[str, date, float]], source: str = ATTRIBUTION) -> int:
    """Insert or overwrite; real rows always replace synthetic ones."""
    n = 0
    existing = {
        (p.series, p.date): p
        for p in db.scalars(select(SeriesPoint).where(SeriesPoint.series.in_(sorted({s for s, _, _ in rows})))).all()
    } if rows else {}
    for series, d, v in rows:
        p = existing.get((series, d))
        if p is None:
            p = SeriesPoint(series=series, date=d, value=v, unit="transits_per_day", source=source, is_synthetic=False)
            db.add(p)
            existing[(series, d)] = p
            n += 1
        elif p.is_synthetic or p.value != v:
            p.value, p.source, p.is_synthetic = v, source, False
            n += 1
    db.commit()
    return n


def fetch_and_ingest(db: Session, since: date | None = None) -> int:
    since = since or (date.today() - timedelta(days=120))
    return ingest_rows(db, fetch_rows(since))


def fetch_and_ingest_csv(db: Session, url: str) -> int:
    """A hand-downloaded export placed on a web share, for hosts that cannot reach ArcGIS."""
    from .base import fetch_text

    return ingest_rows(db, parse_csv(fetch_text(url, timeout=120)))


def backfill(db: Session, since: date = date(2024, 1, 1)) -> int:
    return ingest_rows(db, fetch_rows(since))
