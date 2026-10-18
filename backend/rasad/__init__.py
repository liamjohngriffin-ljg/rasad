"""Rasad (working name): a sovereign indicators-and-warnings engine.

Layers, bottom up:
  pipelines/   connectors that fetch and parse sources into documents and series
  extraction/  LLM-assisted extraction of events and policy observations (human verified)
  models/      the two ledgers (threat events, policy observations), questions, forecasts
  engine/      indicator rules, Bayesian updating, panel aggregation, commitment log, scoring
  policy/      position book: stated and revealed tracks, divergence, change-points, silence
  briefs/      Arabic and English briefs for the principal
  api/         FastAPI surface used by the front end
"""

__version__ = "0.2.0"
