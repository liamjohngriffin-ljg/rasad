"""Connectors: fetch under an egress allow-list, parse deterministically, write to the ledgers.

Each connector exposes `parse(...)` (pure, tested on fixtures) and `fetch(...)` (network, used on
the host that is allowed to reach the source). Nothing a parser produces enters a ledger as
verified; connector rows land as `pending` unless the source is itself the authority
(gazettes, official lists, PortWatch counts), in which case they are marked verified with the
source as verifier.
"""
