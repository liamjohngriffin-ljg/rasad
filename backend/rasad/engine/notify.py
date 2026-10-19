"""Push new alerts into a team chat channel.

Microsoft Teams (a Workflows "post to a channel when a webhook request is received" URL, which takes
an Adaptive Card), Slack (an incoming webhook, which takes text) or any HTTPS endpoint that accepts
JSON. The administrator sets the URL on the Administration page; it is treated as a credential and
never shown to other users.

Each alert is pushed once (pushed_at), only alerts at or above the configured severity, only alerts
from the last three days (a backfill must not flood the channel), and at most a dozen individual
cards per run; the rest go as one summary line. A failed post never stops the pipeline.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Alert

MAX_CARDS = 12
SEV_WORD = {1: "info", 2: "notable", 3: "urgent"}


def _setting(db: Session, key: str) -> str:
    from ..api.admin_routes import get_setting

    return (get_setting(db, key) or "").strip()


def check_url(url: str) -> None:
    """HTTPS only, and not an address inside the deployment's own network (the webhook must not
    become a way to make the server call internal services)."""
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname:
        raise ValueError("the webhook must be an https:// URL")
    if os.getenv("RASAD_WEBHOOK_ALLOW_PRIVATE", "").lower() in ("1", "true", "yes"):
        return
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"cannot resolve {p.hostname}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError(f"{p.hostname} resolves to an internal address ({ip}); set RASAD_WEBHOOK_ALLOW_PRIVATE=true if that is intended")


def _link(db: Session, a: Alert) -> str | None:
    base = (_setting(db, "public_url") or os.getenv("RASAD_PUBLIC_URL", "")).rstrip("/")
    if not base:
        return None
    return f"{base}/q/{a.question_code}" if a.question_code else f"{base}/today"


def _payload(db: Session, kind: str, alerts: list[Alert], extra: int = 0, test: bool = False) -> dict:
    marking = _setting(db, "marking") or "OFFICIAL"
    product = _setting(db, "product_name") or "Rasad"
    if kind == "slack" or kind == "generic":
        lines = [f"[{marking}] {product}: " + ("test message, the channel is connected" if test else f"{len(alerts) + extra} new alert(s)")]
        for a in alerts:
            link = _link(db, a)
            lines.append(f"{'!' * a.severity} {a.kind}: {a.title_en}" + (f" <{link}>" if link and kind == "slack" else (f" {link}" if link else "")))
        if extra:
            lines.append(f"and {extra} more on the Today page")
        if kind == "slack":
            return {"text": "\n".join(lines)}
        return {"product": product, "marking": marking, "test": test, "text": "\n".join(lines),
                "alerts": [{"id": a.id, "kind": a.kind, "severity": a.severity, "title_en": a.title_en, "title_ar": a.title_ar, "question": a.question_code,
                            "created_at": a.created_at.isoformat(), "link": _link(db, a)} for a in alerts], "more": extra}
    # Teams: an Adaptive Card in a message envelope (the format Teams Workflows webhooks accept)
    body: list[dict] = [
        {"type": "TextBlock", "text": marking, "size": "Small", "weight": "Bolder", "color": "Attention"},
        {"type": "TextBlock", "text": f"{product}: " + ("test message, the channel is connected" if test else f"{len(alerts) + extra} new alert(s)"), "weight": "Bolder", "size": "Medium", "wrap": True},
    ]
    for a in alerts:
        link = _link(db, a)
        body.append({"type": "Container", "separator": True, "items": [
            {"type": "TextBlock", "text": f"{SEV_WORD.get(a.severity, '')} · {a.kind.replace('_', ' ')} · {a.created_at:%d %b %H:%M}", "size": "Small", "isSubtle": True, "wrap": True},
            {"type": "TextBlock", "text": a.title_en + (f" [open]({link})" if link else ""), "wrap": True},
            *([{"type": "TextBlock", "text": a.title_ar, "wrap": True, "horizontalAlignment": "Right"}] if a.title_ar else []),
        ]})
    if extra:
        body.append({"type": "TextBlock", "text": f"and {extra} more on the Today page", "isSubtle": True, "wrap": True})
    card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4", "body": body}
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}]}


def _post(url: str, payload: dict) -> None:
    check_url(url)
    r = httpx.post(url, json=payload, timeout=20, follow_redirects=False)
    if r.status_code >= 300:
        raise RuntimeError(f"webhook answered {r.status_code}: {r.text[:200]}")


def push_new(db: Session) -> dict:
    url = _setting(db, "webhook_url")
    if not url:
        return {"pushed": 0, "reason": "no webhook configured"}
    from .. import licence

    if not licence.current().has("api"):
        return {"pushed": 0, "reason": "the licence does not include the api module"}
    kind = _setting(db, "webhook_kind") or "teams"
    try:
        min_sev = int(_setting(db, "webhook_min_severity") or "2")
    except ValueError:
        min_sev = 2
    since = datetime.utcnow() - timedelta(days=3)
    pending = db.scalars(select(Alert).where(Alert.pushed_at.is_(None), Alert.created_at >= since, Alert.acknowledged_at.is_(None)).order_by(Alert.severity.desc(), Alert.created_at)).all()
    send = [a for a in pending if a.severity >= min_sev]
    if not send:
        return {"pushed": 0}
    shown, extra = send[:MAX_CARDS], len(send) - MAX_CARDS if len(send) > MAX_CARDS else 0
    try:
        _post(url, _payload(db, kind, shown, extra))
    except Exception as exc:  # noqa: BLE001
        return {"pushed": 0, "error": f"{type(exc).__name__}: {exc}"[:240]}
    now = datetime.utcnow()
    for a in send:
        a.pushed_at = now
    db.commit()
    return {"pushed": len(send), "kind": kind}


def post_anchor(db: Session, as_of, n_forecasts: int, head_hash: str | None) -> dict:
    """The day's chain head, posted outside the database. A copy held in the channel's history is
    what makes the record tamper-evident: rewriting the table would no longer match it."""
    url = _setting(db, "webhook_url")
    if not url or not head_hash:
        return {"anchored": False}
    from .. import licence

    if not licence.current().has("api"):
        return {"anchored": False}
    kind = _setting(db, "webhook_kind") or "teams"
    marking = _setting(db, "marking") or "OFFICIAL"
    product = _setting(db, "product_name") or "Rasad"
    text = f"{product} record for {as_of}: {n_forecasts} forecasts committed. Chain head {head_hash}"
    if kind == "teams":
        payload = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4", "body": [
                {"type": "TextBlock", "text": marking, "size": "Small", "weight": "Bolder", "color": "Attention"},
                {"type": "TextBlock", "text": f"{product} record for {as_of}: {n_forecasts} forecasts committed", "wrap": True},
                {"type": "TextBlock", "text": f"Chain head {head_hash}", "fontType": "Monospace", "size": "Small", "wrap": True},
            ]}}]}
    elif kind == "slack":
        payload = {"text": f"[{marking}] {text}"}
    else:
        payload = {"product": product, "marking": marking, "anchor": {"as_of": str(as_of), "forecasts": n_forecasts, "chain_head": head_hash}, "text": text}
    try:
        _post(url, payload)
    except Exception as exc:  # noqa: BLE001
        return {"anchored": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"anchored": True, "head": head_hash[:16]}


def send_test(db: Session) -> dict:
    url = _setting(db, "webhook_url")
    if not url:
        return {"ok": False, "error": "set the webhook URL first"}
    kind = _setting(db, "webhook_kind") or "teams"
    try:
        _post(url, _payload(db, kind, [], test=True))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:240]}
    return {"ok": True, "kind": kind}
