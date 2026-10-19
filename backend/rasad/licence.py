"""Licence files: an Ed25519-signed JSON document the vendor issues per customer.

    {"licence_id": "...", "licensee": "...", "seats": 25, "features": ["core", "arabic", "api", "model"],
     "issued_at": "2026-10-18", "expires": "2027-10-18", "notes": "..."}

The vendor keeps the private key (never in the repository); the matching public key is embedded
below. The platform loads RASAD_LICENCE_FILE (default <data_dir>/licence.json) at startup and
re-reads it when an admin uploads a new one. Without a valid licence the platform runs in
evaluation mode: everything works, the interface says so, and sign-ins are capped at
EVALUATION_SEATS. Expired licences get a 30-day grace period with a warning, then evaluation.

Vendor CLI (the key file is produced once and kept offline):
    python -m rasad.licence keygen vendor.key                      # writes vendor.key and prints the public key
    python -m rasad.licence issue vendor.key --licensee "Org" --seats 25 --expires 2027-12-31 --features core,arabic,api,model > licence.json
    python -m rasad.licence verify licence.json
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

# The vendor's public key, fixed in the code. There is deliberately no environment override: a
# customer controls the environment, and an override would let anyone sign their own licence.
VENDOR_PUBLIC_KEY_B64 = "aKD6nj3+rRDRhk8wpn1m+RMAKXUXnZwSaE2LvZmb8q4="
EVALUATION_SEATS = 3
GRACE_DAYS = 30
ALL_FEATURES = ("core", "arabic", "api", "model", "export")


@dataclass
class LicenceState:
    mode: str  # licensed | grace | evaluation
    licensee: str = "Evaluation"
    seats: int = EVALUATION_SEATS
    features: list[str] = field(default_factory=lambda: ["core", "arabic", "export"])
    expires: date | None = None
    licence_id: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict:
        return {"mode": self.mode, "licensee": self.licensee, "seats": self.seats, "features": self.features, "expires": self.expires.isoformat() if self.expires else None, "licence_id": self.licence_id, "reason": self.reason}

    def has(self, feature: str) -> bool:
        return feature in self.features


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def keygen(path: str) -> str:
    priv = Ed25519PrivateKey.generate()
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    with open(path, "wb") as f:
        f.write(pem)
    os.chmod(path, 0o600)
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(pub).decode()


def issue(key_path: str, *, licensee: str, seats: int, expires: str, features: list[str], notes: str = "") -> dict:
    with open(key_path, "rb") as f:
        priv = serialization.load_pem_private_key(f.read(), password=None)
    assert isinstance(priv, Ed25519PrivateKey)
    payload = {"licence_id": secrets.token_hex(8), "licensee": licensee, "seats": int(seats), "features": sorted(set(features)), "issued_at": date.today().isoformat(), "expires": expires, "notes": notes}
    sig = priv.sign(_canonical(payload))
    return {"payload": payload, "signature": base64.b64encode(sig).decode(), "format": "rasad-licence-1"}


def verify(doc: dict, public_key_b64: str | None = None) -> dict:
    pub_b64 = public_key_b64 or VENDOR_PUBLIC_KEY_B64
    if not pub_b64 or pub_b64.startswith("__"):
        raise ValueError("no vendor public key configured")
    pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))
    payload, sig = doc.get("payload"), doc.get("signature")
    if not isinstance(payload, dict) or not isinstance(sig, str):
        raise ValueError("malformed licence file")
    try:
        pub.verify(base64.b64decode(sig), _canonical(payload))
    except InvalidSignature:
        raise ValueError("signature does not verify") from None
    return payload


def load(path: str | None = None, today: date | None = None) -> LicenceState:
    today = today or date.today()
    from .config import get_settings

    path = path or os.getenv("RASAD_LICENCE_FILE") or os.path.join(get_settings().data_dir, "licence.json")
    if not os.path.exists(path):
        return LicenceState("evaluation", reason="no licence file")
    try:
        with open(path, encoding="utf-8") as f:
            payload = verify(json.load(f))
    except Exception as exc:  # noqa: BLE001
        return LicenceState("evaluation", reason=f"licence rejected: {exc}")
    expires = date.fromisoformat(payload["expires"])
    state = LicenceState("licensed", licensee=payload["licensee"], seats=int(payload["seats"]), features=list(payload["features"]), expires=expires, licence_id=payload.get("licence_id"))
    if today > expires + timedelta(days=GRACE_DAYS):
        return LicenceState("evaluation", licensee=payload["licensee"], expires=expires, licence_id=payload.get("licence_id"), reason="licence expired")
    if today > expires:
        state.mode, state.reason = "grace", f"licence expired on {expires.isoformat()}; grace until {(expires + timedelta(days=GRACE_DAYS)).isoformat()}"
    return state


_cached: LicenceState | None = None


def current(refresh: bool = False) -> LicenceState:
    global _cached
    if _cached is None or refresh:
        _cached = load()
    return _cached


def main(argv: list[str]) -> None:
    if not argv or argv[0] not in ("keygen", "issue", "verify"):
        print(__doc__)
        return
    if argv[0] == "keygen":
        pub = keygen(argv[1] if len(argv) > 1 else "vendor.key")
        print(f"public key (put it in VENDOR_PUBLIC_KEY_B64 in rasad/licence.py and build a release): {pub}")
        return
    if argv[0] == "verify":
        with open(argv[1], encoding="utf-8") as f:
            doc = json.load(f)
        payload = verify(doc, os.getenv("RASAD_VERIFY_WITH_KEY") or None)  # vendor-side check of a file against another key
        print(json.dumps(payload, indent=1))
        return
    import argparse

    ap = argparse.ArgumentParser(prog="rasad.licence issue")
    ap.add_argument("key")
    ap.add_argument("--licensee", required=True)
    ap.add_argument("--seats", type=int, default=10)
    ap.add_argument("--expires", required=True)
    ap.add_argument("--features", default="core,arabic,export")
    ap.add_argument("--notes", default="")
    ns = ap.parse_args(argv[1:])
    print(json.dumps(issue(ns.key, licensee=ns.licensee, seats=ns.seats, expires=ns.expires, features=ns.features.split(","), notes=ns.notes), indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
