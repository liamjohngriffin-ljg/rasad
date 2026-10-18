"""Panel aggregation.

Evidence summary (concept document, method section): skill-weighted aggregation of numeric
elicitations with modest extremising beat the unweighted crowd in the IARPA tournaments; the
transformation exponent in Baron et al. (2014) was fitted in-sample, so we default to a mild
1.3 rather than their 2.4 to 3.1, and expose it in settings. Aggregation happens in log-odds
space; medians are reported alongside the mean for the spread shown to the principal.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .bayes import clamp_probability, expit, logit


@dataclass
class PanelSummary:
    probability: float
    median: float
    low: float
    high: float
    n: int
    raw_mean: float

    def as_dict(self) -> dict:
        return {
            "probability": round(self.probability, 4),
            "median": round(self.median, 4),
            "low": round(self.low, 4),
            "high": round(self.high, 4),
            "n": self.n,
            "raw_mean": round(self.raw_mean, 4),
        }


def aggregate(
    forecasts: list[tuple[float, float]],
    *,
    extremise: float = 1.3,
    floor: float = 0.02,
    ceiling: float = 0.98,
) -> PanelSummary | None:
    """forecasts: list of (probability, skill_weight)."""
    if not forecasts:
        return None
    total_w = sum(max(w, 0.0) for _, w in forecasts)
    if total_w <= 0:
        total_w = float(len(forecasts))
        forecasts = [(p, 1.0) for p, _ in forecasts]
    mean_logit = sum(logit(p) * w for p, w in forecasts) / total_w
    raw = expit(mean_logit)
    probs = sorted(p for p, _ in forecasts)
    aggregated = clamp_probability(expit(mean_logit * extremise), floor, ceiling)
    return PanelSummary(
        probability=aggregated,
        median=statistics.median(probs),
        low=probs[0],
        high=probs[-1],
        n=len(probs),
        raw_mean=raw,
    )


def combine(machine_prob: float | None, panel_prob: float | None, machine_weight: float = 0.5) -> float:
    """Blend the indicator posterior with the panel aggregate in log-odds space.

    The literature's robust finding is that the human-machine blend beats either alone
    (SAGE; Halawi et al. system-plus-crowd), so the default weight is an even split.
    """
    if machine_prob is None and panel_prob is None:
        raise ValueError("nothing to combine")
    if panel_prob is None:
        return machine_prob  # type: ignore[return-value]
    if machine_prob is None:
        return panel_prob
    w = min(max(machine_weight, 0.0), 1.0)
    return expit(w * logit(machine_prob) + (1 - w) * logit(panel_prob))
