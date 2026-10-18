from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...models import Document, Source


class EgressRefused(RuntimeError):
    pass


def check_egress(url: str) -> None:
    host = urlparse(url).hostname or ""
    allowed = get_settings().egress_allowlist
    if not any(host == h or host.endswith("." + h) for h in allowed):
        raise EgressRefused(f"{host} is not on the egress allow-list")


def fetch_text(url: str, *, timeout: float = 30.0) -> str:
    check_egress(url)
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": "rasad/0.1 (+research use; contact operator)"}) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


def fetch_bytes(url: str, *, timeout: float = 60.0) -> bytes:
    check_egress(url)
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": "rasad/0.1 (+research use; contact operator)"}) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.content


def cache_path(source_code: str, external_id: str, ext: str) -> str:
    d = os.path.join(get_settings().data_dir, "raw", source_code)
    os.makedirs(d, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in external_id)[:120]
    return os.path.join(d, f"{safe}{ext}")


@dataclass
class RawDoc:
    source_code: str
    external_id: str
    text: str
    url: str | None = None
    title: str | None = None
    language: str = "en"
    published_at: datetime | None = None
    meta: dict = field(default_factory=dict)


def upsert_document(db: Session, raw: RawDoc) -> tuple[Document, bool]:
    src = db.scalar(select(Source).where(Source.code == raw.source_code))
    if src is None:
        src = Source(code=raw.source_code, name=raw.source_code, tier=2, kind="unknown", language=raw.language)
        db.add(src)
        db.flush()
    existing = db.scalar(select(Document).where(Document.source_id == src.id, Document.external_id == raw.external_id))
    sha = hashlib.sha256(raw.text.encode("utf-8")).hexdigest()
    if existing:
        return existing, False
    doc = Document(source_id=src.id, external_id=raw.external_id, url=raw.url, title=raw.title, language=raw.language, published_at=raw.published_at, sha256=sha, raw_text=raw.text, meta=raw.meta or {})
    db.add(doc)
    db.flush()
    return doc, True
