"""MSCIO (Maritime Security Centre, Indian Ocean) document library at mscio.eu.

The library publishes the JMIC and UKMTO products as PDFs in named folders. This connector
lists each folder, skips files already in the document store, downloads the rest into the
raw cache and dispatches them by name:

    UKMTO Warnings / UKMTO Advisories      -> ukmto      (one event per warning)
    JMIC Advisories Dashboard              -> jmic       (weekly threat levels, incident counts)
    JMIC Advisories                        -> jmic_notes (war-period situation notes)
    JMIC Information Note, MSCIO Advisories,
    UKMTO Weeklies, Weekly Threat Assessment -> stored as documents for search and later parsers

The listing is plain HTML with `href="/media/documents/<file>.pdf"` links and a `title`
attribute carrying the display name.
"""

from __future__ import annotations

import os
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Document, Source
from . import jmic, jmic_notes, mscio_weekly, ukmto
from .base import RawDoc, cache_path, fetch_bytes, fetch_text, upsert_document

BASE = "https://mscio.eu"
FOLDERS = {
    "ukmto_warnings": "/folder/documents/UKMTO%20Warnings/",
    "ukmto_advisories": "/folder/documents/UKMTO%20Advisories/",
    "jmic_dashboards": "/folder/documents/JMIC%20Advisories%20Dashboard/",
    "jmic_advisories": "/folder/documents/JMIC%20Advisories/",
    "jmic_information": "/folder/documents/JMIC%20Information%20Note/",
    "mscio_advisories": "/folder/documents/MSCIO%20Advisories/",
    "ukmto_weeklies": "/folder/documents/UKMTO%20Weeklies/",
    "weekly_threat_assessment": None,  # year-suffixed; discovered from the advisories page
}
LINK_RE = re.compile(r'<a[^>]*?(?:title="([^"]*)")?[^>]*?href="(/media/documents/[^"]+\.pdf)"', re.I)
FOLDER_RE = re.compile(r'href="(https://mscio\.eu/folder/documents/WEEKLY%20THREAT%20ASSESSMENT%20(20\d{2})/)"', re.I)
DATE_PREFIX_RE = re.compile(r"^(20\d{2})(\d{2})(\d{2})[-_]")


def list_folder(path_or_url: str) -> list[tuple[str, str]]:
    """Return (url, title) for every PDF linked from a folder page."""
    url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
    html = fetch_text(url, timeout=60)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in LINK_RE.finditer(html):
        href = m.group(2)
        if href in seen:
            continue
        seen.add(href)
        out.append((BASE + href, (m.group(1) or href.rsplit("/", 1)[-1]).strip()))
    return out


def discover_weekly_assessment_folders() -> list[str]:
    try:
        html = fetch_text(BASE + "/advisories/", timeout=60)
    except Exception:  # noqa: BLE001
        return []
    return sorted({m.group(1) for m in FOLDER_RE.finditer(html)})


def classify(filename: str, folder: str) -> str:
    f = filename.upper()
    if "UKMTO" in f and ("WARNING" in f or "ADVISORY" in f or "INCIDENT" in f) or folder in ("ukmto_warnings", "ukmto_advisories") and "SUMMARY" not in f:
        return "ukmto"
    if "DASHBOARD" in f or folder == "jmic_dashboards":
        return "jmic_dashboard"
    if "ADVISORY_NOTE" in f or "ADVISORY NOTE" in f or folder == "jmic_advisories":
        return "jmic_note"
    if "WEEKLY" in f and ("ATALANTA" in f or "ATA_" in f or "MSCIO" in f) or folder == "weekly_threat_assessment":
        return "mscio_weekly"
    return "document"


def _known_external_ids(db: Session, source_codes: tuple[str, ...]) -> set[str]:
    ids: set[str] = set()
    for code in source_codes:
        src = db.scalar(select(Source).where(Source.code == code))
        if src is None:
            continue
        ids.update(db.scalars(select(Document.external_id).where(Document.source_id == src.id)))
    return ids


def _published(filename: str) -> date | None:
    m = DATE_PREFIX_RE.match(filename)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def read_pdf_text(data: bytes) -> str:
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def ingest_file(db: Session, data: bytes, *, filename: str, url: str, folder: str, title: str | None = None) -> dict:
    kind = classify(filename, folder)
    out = {"kind": kind, "file": filename}
    if kind == "ukmto":
        ev = ukmto.ingest_pdf(db, data, external_id=filename, url=url)
        db.commit()
        out["event"] = ev.id if ev is not None else None
    elif kind == "jmic_dashboard":
        parsed = jmic.ingest_text(db, read_pdf_text(data), external_id=filename, url=url)
        out["week"] = parsed.get("week")
    elif kind == "jmic_note":
        counts = jmic_notes.ingest_pdf(db, data, external_id=filename, url=url)
        out.update(counts)
    elif kind == "mscio_weekly":
        out.update(mscio_weekly.ingest_text(db, mscio_weekly.read_pdf_text(data), external_id=filename, url=url))
    else:
        text = read_pdf_text(data)
        source_code = "ukmto" if "UKMTO" in filename.upper() else "jmic" if "JMIC" in filename.upper() else "mscio"
        pub = _published(filename)
        from datetime import datetime

        upsert_document(db, RawDoc(source_code, filename, text, url=url, title=title, published_at=datetime(pub.year, pub.month, pub.day) if pub else None, meta={"folder": folder}))
        db.commit()
    return out


def poll(db: Session, *, folders: list[str] | None = None, limit_per_folder: int | None = None, since: date | None = None) -> dict:
    """List every configured folder, fetch what is new, dispatch. Returns a per-folder report."""
    report: dict = {}
    known = _known_external_ids(db, ("ukmto", "jmic", "mscio"))
    targets: list[tuple[str, str]] = []
    for name, path in FOLDERS.items():
        if folders and name not in folders:
            continue
        if path is None:
            for u in discover_weekly_assessment_folders():
                targets.append((name, u))
        else:
            targets.append((name, path))
    for name, path in targets:
        try:
            links = list_folder(path)
        except Exception as exc:  # noqa: BLE001
            report[f"{name}_error"] = str(exc)
            continue
        new = []
        for url, title in links:
            fn = url.rsplit("/", 1)[-1]
            if fn in known:
                continue
            if since is not None:
                pub = _published(fn)
                if pub is not None and pub < since:
                    continue
            new.append((url, title, fn))
        new.sort(key=lambda t: t[2])
        if limit_per_folder:
            new = new[-limit_per_folder:]
        done, errors = 0, []
        for url, title, fn in new:
            try:
                path_on_disk = cache_path("mscio", fn, "")
                if os.path.exists(path_on_disk):
                    with open(path_on_disk, "rb") as fh:
                        data = fh.read()
                else:
                    data = fetch_bytes(url, timeout=90)
                    with open(path_on_disk, "wb") as fh:
                        fh.write(data)
                ingest_file(db, data, filename=fn, url=url, folder=name, title=title)
                known.add(fn)
                done += 1
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                errors.append(f"{fn}: {exc}")
        report[name] = {"listed": len(links), "new": len(new), "ingested": done, "errors": errors[:5]}
    return report


def ingest_directory(db: Session, directory: str, *, folder_hint: str = "local") -> dict:
    """Ingest a directory of previously downloaded PDFs (air-gapped deployments, or a bulk backfill)."""
    report = {"files": 0, "errors": []}
    known = _known_external_ids(db, ("ukmto", "jmic", "mscio"))
    for fn in sorted(os.listdir(directory)):
        if not fn.lower().endswith(".pdf") or fn in known:
            continue
        with open(os.path.join(directory, fn), "rb") as fh:
            data = fh.read()
        try:
            ingest_file(db, data, filename=fn, url=f"{BASE}/media/documents/{fn}", folder=folder_hint)
            report["files"] += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            report["errors"].append(f"{fn}: {exc}")
    return report
