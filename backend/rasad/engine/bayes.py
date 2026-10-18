"""Bayesian updating over indicators with explicit likelihood ratios.

Each indicator carries two ratios elicited from the panel and refined on resolved questions:
  lr_present = P(indicator present | outcome) / P(indicator present | no outcome)
  lr_absent  = P(indicator absent  | outcome) / P(indicator absent  | no outcome)
The posterior log-odds is the prior log-odds plus the sum of the log ratios for the observed
states. Unknown states contribute nothing. Each contribution is capped so that no single
indicator can move the estimate by more than a factor of `max_lr`, which keeps a mis-elicited
ratio from dominating and makes the decomposition readable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Contribution:
    indicator_code: str
    state: str
    log_lr: float
    evidence: dict = field(default_factory=dict)


@dataclass
class Posterior:
    prior: float
    probability: float
    log_odds: float
    contributions: list[Contribution]

    def as_dict(self) -> dict:
        return {
            "prior": round(self.prior, 4),
            "probability": round(self.probability, 4),
            "log_odds": round(self.log_odds, 4),
            "contributions": [
                {
                    "indicator": c.indicator_code,
                    "state": c.state,
                    "log_lr": round(c.log_lr, 4),
                    "evidence": c.evidence,
                }
                for c in self.contributions
            ],
        }


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def expit(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1 / (1 + z)
    z = math.exp(x)
    return z / (1 + z)


def clamp_probability(p: float, floor: float = 0.02, ceiling: float = 0.98) -> float:
    return min(max(p, floor), ceiling)


def update(
    prior: float,
    states: list[tuple[str, str, float, float, dict]],
    *,
    max_lr: float = 10.0,
    floor: float = 0.02,
    ceiling: float = 0.98,
) -> Posterior:
    """states: list of (indicator_code, state, lr_present, lr_absent, evidence)."""
    cap = math.log(max_lr)
    lo = logit(prior)
    contributions: list[Contribution] = []
    for code, state, lr_present, lr_absent, evidence in states:
        if state == "present":
            l = math.log(max(lr_present, 1e-6))
        elif state == "absent":
            l = math.log(max(lr_absent, 1e-6))
        else:
            l = 0.0
        l = max(-cap, min(cap, l))
        contributions.append(Contribution(code, state, l, evidence))
        lo += l
    p = clamp_probability(expit(lo), floor, ceiling)
    return Posterior(prior=prior, probability=p, log_odds=lo, contributions=contributions)
