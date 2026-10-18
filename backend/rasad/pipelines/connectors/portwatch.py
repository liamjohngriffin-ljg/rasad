"""IMF PortWatch chokepoint transits (daily CSV export).

PortWatch publishes daily transit calls per chokepoint from UN Global Platform AIS, with an
observed lag of about eight days and revisions. Attribution is required and commercial reuse
needs emailed permission (IMF terms), so the loader records the source on every row and the
operator keeps the permission on file. Counts are the authority for the series, so rows are
not synthetic and need no analyst verification.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import SeriesPoint
from .base import fetch_text

CHOKEPOINT_SERIES = {
    "strait of hormuz": "hormuz_transits",
    "bab el-mandeb strait": "bab_el_mandeb_transits",
    "bab el mandeb": "bab_el_mandeb_transits",
    "suez canal": "suez_transits",
}

# PortWatch's export columns have varied; accept the common spellings.
DATE_COLS = ("date", "Date", "date_str")
NAME_COLS = ("portname", "chokepoint", "name", "portName")
VALUE_COLS = ("n_total", "total", "transits", "n_transits", "value")


def _pick(row: dict, cols: tuple[str, ...]) -> str | None:
    for c in cols:
        if c in row and row[c] not in (None, ""):
            return row[c]
    return None


def parse_csv(text: str) -> list[tuple[str, date, float]]:
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        name = (_pick(row, NAME_COLS) or "").strip().lower()
        series = CHOKEPOINT_SERIES.get(name)
        if series is None:
            continue
        raw_date = _pick(row, DATE_COLS)
        raw_val = _pick(row, VALUE_COLS)
        if not raw_date or raw_val is None:
            continue
        try:
            d = datetime.fromisoformat(raw_date[:19]).date() if "T" in raw_date or " " in raw_date else date.fromisoformat(raw_date[:10])
            v = float(raw_val)
        except ValueError:
            continue
        out.append((series, d, v))
    return out


def ingest_rows(db: Session, rows: list[tuple[str, date, float]], source: str = "IMF PortWatch") -> int:
    n = 0
    for series, d, v in rows:
        existing = db.scalar(select(SeriesPoint).where(SeriesPoint.series == series, SeriesPoint.date == d))
        if existing:
            if existing.is_synthetic or existing.value != v:
                existing.value, existing.source, existing.is_synthetic = v, source, False
                n += 1
            continue
        db.add(SeriesPoint(series=series, date=d, value=v, unit="transits_per_day", source=source, is_synthetic=False))
        n += 1
    db.commit()
    return n


def fetch_and_ingest(db: Session, url: str) -> int:
    return ingest_rows(db, parse_csv(fetch_text(url)))
