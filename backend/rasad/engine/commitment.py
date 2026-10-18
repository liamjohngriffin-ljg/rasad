"""Hash-chained commitment log.

A forecast is committed before resolution with a SHA-256 over the previous commit, the
question, the as-of date, the probability and the full decomposition. The chain can be
re-verified by anyone holding the table; that is the technical basis of the published record.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date


def commit_hash(prev_hash: str | None, question_code: str, as_of: date, final_prob: float, decomposition: dict) -> str:
    payload = "|".join(
        [
            prev_hash or "GENESIS",
            question_code,
            as_of.isoformat(),
            f"{final_prob:.6f}",
            json.dumps(decomposition, sort_keys=True, separators=(",", ":"), default=str),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_chain(rows: list[dict]) -> tuple[bool, int | None]:
    """rows: ordered dicts with prev_hash, question_code, as_of (date), final_prob, decomposition, commit_hash.
    Returns (ok, index_of_first_bad_row)."""
    prev: str | None = None
    for i, r in enumerate(rows):
        if r["prev_hash"] != prev:
            return False, i
        expected = commit_hash(prev, r["question_code"], r["as_of"], r["final_prob"], r["decomposition"])
        if expected != r["commit_hash"]:
            return False, i
        prev = r["commit_hash"]
    return True, None
