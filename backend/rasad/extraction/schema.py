from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ExtractedEvent(BaseModel):
    event_date: date
    event_type: str
    country: str | None = None
    location_name: str | None = None
    actor: str | None = None  # actor code
    target: str | None = None
    fatalities: int | None = None
    severity: int = Field(2, ge=1, le=5)
    description_en: str
    description_ar: str | None = None
    confidence: float = Field(0.5, ge=0, le=1)
    quote: str | None = None


class ExtractedObservation(BaseModel):
    actor: str
    issue: str
    observed_at: date
    track: str = "stated"
    channel: str = "statement"
    cost_class: str = "cheap_talk"
    speaker_level: str = "spokesperson"
    score: float = Field(0.0, ge=-1, le=1)
    confidence: float = Field(0.5, ge=0, le=1)
    quote: str
    quote_en: str | None = None


class ExtractionResult(BaseModel):
    events: list[ExtractedEvent] = []
    observations: list[ExtractedObservation] = []
    provider: str = "rules"
