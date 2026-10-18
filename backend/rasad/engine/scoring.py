"""Scoring: Brier, Brier skill against a named baseline, calibration bins.

The baseline is the question's status-quo base rate, which is the honest comparator for a
warning system (most public early-warning models are beaten by no-change baselines, so a
record that does not beat one is not worth publishing).
"""

from __future__ import annotations

from dataclasses import dataclass


def brier(p: float, outcome: bool) -> float:
    y = 1.0 if outcome else 0.0
    return (p - y) ** 2


@dataclass
class ScoreSummary:
    n: int
    mean_brier: float | None
    baseline_brier: float | None
    skill: float | None  # 1 - BS/BS_baseline
    calibration: list[dict]

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "mean_brier": None if self.mean_brier is None else round(self.mean_brier, 4),
            "baseline_brier": None if self.baseline_brier is None else round(self.baseline_brier, 4),
            "skill": None if self.skill is None else round(self.skill, 4),
            "calibration": self.calibration,
        }


def summarise(pairs: list[tuple[float, float, bool]], bins: int = 5) -> ScoreSummary:
    """pairs: (forecast_prob, baseline_prob, outcome)."""
    n = len(pairs)
    if n == 0:
        return ScoreSummary(0, None, None, None, [])
    bs = sum(brier(p, y) for p, _, y in pairs) / n
    bb = sum(brier(b, y) for _, b, y in pairs) / n
    skill = None if bb == 0 else 1 - bs / bb
    edges = [i / bins for i in range(bins + 1)]
    cal = []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        inbin = [(p, y) for p, _, y in pairs if (lo <= p < hi) or (i == bins - 1 and p == hi)]
        if inbin:
            cal.append(
                {
                    "bin": f"{lo:.1f}-{hi:.1f}",
                    "n": len(inbin),
                    "mean_forecast": round(sum(p for p, _ in inbin) / len(inbin), 3),
                    "observed_rate": round(sum(1 for _, y in inbin if y) / len(inbin), 3),
                }
            )
        else:
            cal.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": 0, "mean_forecast": None, "observed_rate": None})
    return ScoreSummary(n, bs, bb, skill, cal)
