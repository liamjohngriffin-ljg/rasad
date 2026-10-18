"""Extraction of events and policy observations from documents.

Three providers behind one interface:
  rules      keyword lexicons in Arabic, Farsi and English (always available, low confidence)
  anthropic  Claude via API during development (needs ANTHROPIC_API_KEY)
  local      an OpenAI-compatible endpoint serving an in-country open-weight model (Jais, Fanar)
Every extracted row lands as `pending`; the verification queue is where it becomes evidence.
"""
