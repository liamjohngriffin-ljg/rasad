"""Position estimates from graded observations.

Weighting (concept document, policy layer):
  revealed actions and sunk costs > hands-tying statements > cheap talk;
  seniority of the speaker; source reliability and information credibility on an adapted
  6x6 grade; model confidence; recency decay with a configurable half-life; corroboration
  through independent channels raises effective weight simply by adding observations.

The estimate is a weighted mean of signed scores on the issue scale (-1 .. +1). Confidence is
reported as the effective number of observations and the weighted spread, never as a
probability, because a position is a description, not a forecast. Forecasts that a position
implies are made as questions and scored with everything else.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

COST_CLASS_WEIGHT = {
    "cheap_talk": 0.25,
    "hands_tying": 0.5,
    "sunk_cost": 0.8,
    "revealed_action": 1.0,
}

SPEAKER_WEIGHT = {
    "head_of_state": 1.0,
    "minister": 0.8,
    "institution": 0.8,
    "legislature": 0.6,
    "spokesperson": 0.6,
    "official_media": 0.5,
    "semi_official": 0.4,
}

RELIABILITY_WEIGHT = {"A": 1.0, "B": 0.9, "C": 0.75, "D": 0.6, "E": 0.4, "F": 0.5}
CREDIBILITY_WEIGHT = {"1": 1.0, "2": 0.9, "3": 0.75, "4": 0.6, "5": 0.4, "6": 0.5}


@dataclass
class Observation:
    observed_at: date
    track: str
    score: float
    cost_class: str
    speaker_level: str
    source_grade: str = "B2"
    model_confidence: float = 1.0
    ref: int | None = None  # ledger id for the audit trail


@dataclass
class PositionEstimate:
    score: float | None
    effective_n: float
    n: int
    spread: float | None
    last_observed: date | None
    top_refs: list[int]

    def as_dict(self) -> dict:
        return {
            "score": None if self.score is None else round(self.score, 3),
            "effective_n": round(self.effective_n, 2),
            "n": self.n,
            "spread": None if self.spread is None else round(self.spread, 3),
            "last_observed": None if self.last_observed is None else self.last_observed.isoformat(),
            "top_refs": self.top_refs,
        }


def observation_weight(o: Observation, as_of: date, half_life_days: float = 30.0) -> float:
    age = (as_of - o.observed_at).days
    if age < 0:
        return 0.0
    recency = 0.5 ** (age / half_life_days)
    grade = (o.source_grade or "B2").upper()
    rel = RELIABILITY_WEIGHT.get(grade[:1], 0.5)
    cred = CREDIBILITY_WEIGHT.get(grade[1:2], 0.5)
    return (
        COST_CLASS_WEIGHT.get(o.cost_class, 0.25)
        * SPEAKER_WEIGHT.get(o.speaker_level, 0.5)
        * rel
        * cred
        * min(max(o.model_confidence, 0.0), 1.0)
        * recency
    )


def estimate(
    observations: list[Observation],
    as_of: date,
    *,
    track: str | None = None,
    half_life_days: float = 30.0,
    min_effective_n: float = 0.08,
) -> PositionEstimate:
    obs = [o for o in observations if (track is None or o.track == track) and o.observed_at <= as_of]
    if not obs:
        return PositionEstimate(None, 0.0, 0, None, None, [])
    weighted = [(o, observation_weight(o, as_of, half_life_days)) for o in obs]
    total = sum(w for _, w in weighted)
    if total < min_effective_n:
        return PositionEstimate(None, total, len(obs), None, max(o.observed_at for o in obs), [])
    mean = sum(o.score * w for o, w in weighted) / total
    var = sum(w * (o.score - mean) ** 2 for o, w in weighted) / total
    top = sorted(weighted, key=lambda t: t[1], reverse=True)[:5]
    return PositionEstimate(
        score=mean,
        effective_n=total,
        n=len(obs),
        spread=math.sqrt(var),
        last_observed=max(o.observed_at for o in obs),
        top_refs=[o.ref for o, _ in top if o.ref is not None],
    )


def divergence(stated: PositionEstimate, revealed: PositionEstimate) -> float | None:
    """Normalised distance between the two tracks on the same issue, 0 .. 1."""
    if stated.score is None or revealed.score is None:
        return None
    return abs(stated.score - revealed.score) / 2.0


def series(
    observations: list[Observation],
    start: date,
    end: date,
    *,
    track: str | None = None,
    step_days: int = 7,
    half_life_days: float = 30.0,
) -> list[tuple[date, float | None]]:
    out = []
    d = start
    while d <= end:
        out.append((d, estimate(observations, d, track=track, half_life_days=half_life_days).score))
        d += timedelta(days=step_days)
    return out


def change_points(
    points: list[tuple[date, float | None]],
    *,
    drift: float = 0.05,
    threshold: float = 0.35,
) -> list[dict]:
    """Two-sided CUSUM on a position series. A change-point raises an indicator for a human;
    it never issues a warning on its own (Lange et al. tied 22 of 25 topic changes to events
    and missed the 2014 refugee crisis, which is the right level of trust)."""
    vals = [(d, v) for d, v in points if v is not None]
    if len(vals) < 4:
        return []
    out: list[dict] = []
    ref = vals[0][1]
    s_pos = s_neg = 0.0
    for d, v in vals[1:]:
        s_pos = max(0.0, s_pos + (v - ref) - drift)
        s_neg = max(0.0, s_neg - (v - ref) - drift)
        if s_pos > threshold:
            out.append({"date": d.isoformat(), "direction": "up", "magnitude": round(s_pos, 3)})
            ref, s_pos, s_neg = v, 0.0, 0.0
        elif s_neg > threshold:
            out.append({"date": d.isoformat(), "direction": "down", "magnitude": round(s_neg, 3)})
            ref, s_pos, s_neg = v, 0.0, 0.0
    return out


def silence(
    observations: list[Observation],
    as_of: date,
    *,
    window_days: int = 14,
    baseline_days: int = 90,
    ratio_threshold: float = 0.25,
) -> dict:
    """Statement frequency in the last window against the actor's own baseline rate.
    A drop below the threshold is itself an observation worth a human look."""
    stated = [o for o in observations if o.track == "stated" and o.observed_at <= as_of]
    win_start = as_of - timedelta(days=window_days)
    base_start = win_start - timedelta(days=baseline_days)
    recent = sum(1 for o in stated if win_start < o.observed_at <= as_of)
    baseline = sum(1 for o in stated if base_start < o.observed_at <= win_start)
    baseline_rate = baseline / baseline_days * window_days if baseline_days else 0.0
    ratio = None if baseline_rate == 0 else recent / baseline_rate
    flagged = baseline >= 3 and ratio is not None and ratio < ratio_threshold
    return {
        "recent_count": recent,
        "baseline_count": baseline,
        "expected_in_window": round(baseline_rate, 2),
        "ratio": None if ratio is None else round(ratio, 3),
        "flagged": flagged,
    }
