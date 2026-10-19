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


MAX_REDIRECTS = 5
MAX_BYTES = int(os.getenv("RASAD_FETCH_MAX_MB", "80")) * 1024 * 1024
UA = {"User-Agent": "rasad/0.4 (+research use; contact operator)"}


def check_egress(url: str) -> None:
    """Every URL the platform fetches, including each redirect hop, must be HTTPS (unless the
    operator allows plain HTTP) and on the allow-list."""
    p = urlparse(url)
    if p.scheme != "https" and not (p.scheme == "http" and os.getenv("RASAD_EGRESS_ALLOW_HTTP", "").lower() in ("1", "true", "yes")):
        raise EgressRefused(f"{p.scheme or 'no'} scheme refused for {p.hostname}; feeds are fetched over https")
    host = p.hostname or ""
    allowed = get_settings().egress_allowlist
    if not any(host == h or host.endswith("." + h) for h in allowed):
        raise EgressRefused(f"{host} is not on the egress allow-list")


def _get(url: str, timeout: float) -> httpx.Response:
    """GET with redirects followed by hand, so a redirect to a host off the allow-list (an internal
    address, a cloud metadata service) is refused, and with the body capped."""
    with httpx.Client(timeout=timeout, follow_redirects=False, headers=UA) as c:
        for _ in range(MAX_REDIRECTS + 1):
            check_egress(url)
            with c.stream("GET", url) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    url = str(httpx.URL(url).join(r.headers["location"]))
                    continue
                r.raise_for_status()
                size = int(r.headers.get("content-length") or 0)
                if size > MAX_BYTES:
                    raise EgressRefused(f"{url} is {size // 1048576} MB, over the {MAX_BYTES // 1048576} MB limit")
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > MAX_BYTES:
                        raise EgressRefused(f"{url} exceeded the {MAX_BYTES // 1048576} MB limit")
                return httpx.Response(r.status_code, headers=r.headers, content=bytes(buf), request=r.request)
    raise EgressRefused(f"too many redirects from {url}")


def fetch_text(url: str, *, timeout: float = 30.0) -> str:
    return _get(url, timeout).text


def fetch_bytes(url: str, *, timeout: float = 60.0) -> bytes:
    return _get(url, timeout).content


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
