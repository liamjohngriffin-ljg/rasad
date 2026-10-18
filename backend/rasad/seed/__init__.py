"""Seed data for a first deployment.

Two kinds of rows live here and the flag `is_synthetic` separates them without exception:
  * sourced rows: dates and facts taken from the research behind the concept document (the
    source is named in `provenance`), coded to the ledger schema;
  * synthetic rows: illustrative series and statements needed to exercise the engine before
    live feeds are connected. The UI shows a banner while any synthetic row is present, and
    every indicator evidence block reports its synthetic share.
"""
