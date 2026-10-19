"""The two ledgers and everything that hangs off them.

Design rules carried from the concept document:
  * every number decomposes to named indicators and dated evidence, so events and
    observations carry provenance and a verification state;
  * forecasts are committed to a hash chain before resolution and never edited;
  * synthetic demo rows are flagged so a reader can never mistake them for the record.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Sources and documents
# ---------------------------------------------------------------------------


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    tier: Mapped[int] = mapped_column(Integer)  # 1 law/budget, 2 official statements, 3 procurement, 4 broadcast, 5 commercial
    kind: Mapped[str] = mapped_column(String(64))  # gazette, wire, advisory, series, procurement, sanctions, rss, broadcast
    url: Mapped[str | None] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(8), default="en")
    licence_note: Mapped[str | None] = mapped_column(Text)
    reuse_ok: Mapped[bool] = mapped_column(Boolean, default=True)

    documents: Mapped[list[Document]] = relationship(back_populates="source")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_doc_source_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(800))
    title: Mapped[str | None] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(8), default="en")
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    sha256: Mapped[str | None] = mapped_column(String(64))
    raw_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="ingested")  # ingested, extracted, reviewed
    meta: Mapped[dict | None] = mapped_column(JSON, default=dict)  # connector hints: question_codes, folder, domain

    source: Mapped[Source] = relationship(back_populates="documents")


# ---------------------------------------------------------------------------
# Actors and issues (the position book's axes)
# ---------------------------------------------------------------------------


class Actor(Base):
    __tablename__ = "actors"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)  # US, IR, SA, QA, AE, YE-HOUTHI, IL ...
    name_en: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str | None] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(24), default="state")  # state, institution, leader, non_state, body


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True)
    name_en: Mapped[str] = mapped_column(String(160))
    name_ar: Mapped[str | None] = mapped_column(String(160))
    low_label_en: Mapped[str] = mapped_column(String(160))  # meaning of -1
    high_label_en: Mapped[str] = mapped_column(String(160))  # meaning of +1
    cap_code: Mapped[str | None] = mapped_column(String(8))  # Comparative Agendas subtopic, where one fits


# ---------------------------------------------------------------------------
# Ledger 1: threat events and series
# ---------------------------------------------------------------------------


class ThreatEvent(Base):
    __tablename__ = "threat_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    # missile_strike, drone_strike, intercept, maritime_attack, maritime_harassment, seizure,
    # gnss_interference, mine_warning, cyber_incident, airspace_closure, insurer_listing,
    # expulsion, deployment, exercise, statement_threat
    location_name: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(16))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("actors.id"))
    target_actor_id: Mapped[int | None] = mapped_column(ForeignKey("actors.id"))
    fatalities: Mapped[int | None] = mapped_column(Integer)
    severity: Mapped[int] = mapped_column(Integer, default=2)  # 1 low .. 5 severe
    description_en: Mapped[str] = mapped_column(Text)
    description_ar: Mapped[str | None] = mapped_column(Text)
    source_doc_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)  # {"source": ..., "url": ..., "grade": "B2"}
    # cross-source incident linking: every report of one real-world incident carries the id of the
    # canonical report (its own id for the canonical one); link is anchored | probable | manual | detached
    incident_id: Mapped[int | None] = mapped_column(Integer, index=True)
    incident_link: Mapped[str | None] = mapped_column(String(16))
    verification: Mapped[str] = mapped_column(String(16), default="pending")  # pending, verified, rejected
    verified_by: Mapped[str | None] = mapped_column(String(80))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    actor: Mapped[Actor | None] = relationship(foreign_keys=[actor_id])
    target_actor: Mapped[Actor | None] = relationship(foreign_keys=[target_actor_id])


class SeriesPoint(Base):
    __tablename__ = "series_points"
    __table_args__ = (UniqueConstraint("series", "date", name="uq_series_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series: Mapped[str] = mapped_column(String(64), index=True)
    # hormuz_transits, bab_el_mandeb_transits, suez_transits, war_risk_premium_hormuz_pct,
    # war_risk_premium_red_sea_pct, jwc_gcc_states_listed
    date: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(120))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------
# Ledger 2: policy observations
# ---------------------------------------------------------------------------


class PolicyObservation(Base):
    __tablename__ = "policy_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), index=True)
    observed_at: Mapped[date] = mapped_column(Date, index=True)
    track: Mapped[str] = mapped_column(String(12))  # stated | revealed
    channel: Mapped[str] = mapped_column(String(32))
    # gazette, budget, award, notification, appointment, vote, deployment, event,
    # statement, speech, interview, social, broadcast, communique
    cost_class: Mapped[str] = mapped_column(String(24))  # cheap_talk, hands_tying, sunk_cost, revealed_action
    speaker_level: Mapped[str] = mapped_column(String(24))
    # head_of_state, minister, spokesperson, official_media, semi_official, legislature, institution
    language: Mapped[str] = mapped_column(String(8), default="en")
    score: Mapped[float] = mapped_column(Float)  # signed position on the issue scale, -1 .. +1
    source_grade: Mapped[str] = mapped_column(String(2), default="B2")  # adapted 6x6: reliability A-F, credibility 1-6
    model_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    text_excerpt: Mapped[str] = mapped_column(Text)
    text_excerpt_en: Mapped[str | None] = mapped_column(Text)
    source_doc_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    verification: Mapped[str] = mapped_column(String(16), default="pending")
    verified_by: Mapped[str | None] = mapped_column(String(80))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    actor: Mapped[Actor] = relationship()
    issue: Mapped[Issue] = relationship()


# ---------------------------------------------------------------------------
# Questions, indicators, forecasts
# ---------------------------------------------------------------------------


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True)
    title_en: Mapped[str] = mapped_column(String(300))
    title_ar: Mapped[str | None] = mapped_column(String(300))
    horizon_days: Mapped[int] = mapped_column(Integer)
    resolution_criteria: Mapped[str] = mapped_column(Text)
    resolution_criteria_ar: Mapped[str | None] = mapped_column(Text)
    decision_hooks: Mapped[list] = mapped_column(JSON, default=list)
    decision_hooks_ar: Mapped[list | None] = mapped_column(JSON)
    base_rate: Mapped[float] = mapped_column(Float)  # status-quo baseline probability for the horizon
    base_rate_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open, resolved
    opened_at: Mapped[date] = mapped_column(Date)
    resolves_at: Mapped[date] = mapped_column(Date)
    order: Mapped[int] = mapped_column(Integer, default=0)

    indicators: Mapped[list[Indicator]] = relationship(back_populates="question", order_by="Indicator.id")


class Indicator(Base):
    __tablename__ = "indicators"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    name_en: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # Likelihood ratios elicited from the panel and refined on resolved questions:
    # P(indicator present | event) / P(indicator present | no event), and the same for absence.
    lr_present: Mapped[float] = mapped_column(Float)
    lr_absent: Mapped[float] = mapped_column(Float)
    rule: Mapped[dict] = mapped_column(JSON)  # see engine/indicators.py for rule types
    polarity: Mapped[str] = mapped_column(String(12), default="emerging")  # emerging | not_emerging

    question: Mapped[Question] = relationship(back_populates="indicators")


class IndicatorState(Base):
    __tablename__ = "indicator_states"
    __table_args__ = (UniqueConstraint("indicator_id", "as_of", name="uq_indicator_asof"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicators.id"), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    state: Mapped[str] = mapped_column(String(12))  # present, absent, unknown
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Forecaster(Base):
    __tablename__ = "forecasters"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), default="human")  # human | machine
    skill_weight: Mapped[float] = mapped_column(Float, default=1.0)


class PanelForecast(Base):
    __tablename__ = "panel_forecasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    forecaster_id: Mapped[int] = mapped_column(ForeignKey("forecasters.id"))
    as_of: Mapped[date] = mapped_column(Date, index=True)
    probability: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str | None] = mapped_column(Text)

    forecaster: Mapped[Forecaster] = relationship()


class Forecast(Base):
    """A committed forecast. Immutable once written; the hash chain proves it."""

    __tablename__ = "forecasts"
    __table_args__ = (UniqueConstraint("question_id", "as_of", name="uq_forecast_question_asof"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    machine_prob: Mapped[float | None] = mapped_column(Float)
    panel_prob: Mapped[float | None] = mapped_column(Float)
    final_prob: Mapped[float] = mapped_column(Float)
    decomposition: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    commit_hash: Mapped[str] = mapped_column(String(64), unique=True)
    committed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    question: Mapped[Question] = relationship()


class Resolution(Base):
    __tablename__ = "resolutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), unique=True)
    resolved_at: Mapped[date] = mapped_column(Date)
    outcome: Mapped[bool] = mapped_column(Boolean)
    notes: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(80))


# ---------------------------------------------------------------------------
# Outputs for the principal
# ---------------------------------------------------------------------------


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"))
    lang: Mapped[str] = mapped_column(String(4))
    content_md: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    generator: Mapped[str] = mapped_column(String(64))  # template | anthropic:<model> | local:<model>


class TaskingRequest(Base):
    __tablename__ = "tasking_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="open")  # open, framed, answered
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"))
    answer_md: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Alerts: what changed, for people who were not watching
# ---------------------------------------------------------------------------


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # indicator_flip, forecast_move, severe_event, series_break, chain_broken, resolution_due
    severity: Mapped[int] = mapped_column(Integer, default=2)  # 1 info, 2 notable, 3 urgent
    question_code: Mapped[str | None] = mapped_column(String(48), index=True)
    title_en: Mapped[str] = mapped_column(String(300))
    title_ar: Mapped[str | None] = mapped_column(String(300))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(80))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
