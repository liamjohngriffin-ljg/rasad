from __future__ import annotations

import math
from datetime import date, timedelta

from rasad.engine import bayes, panel, scoring
from rasad.engine.commitment import commit_hash, verify_chain
from rasad.policy import positions as P


def test_bayes_update_moves_in_the_right_direction():
    post = bayes.update(0.3, [("a", "present", 3.0, 0.5, {}), ("b", "absent", 2.0, 0.5, {}), ("c", "unknown", 9.0, 0.1, {})])
    expected = bayes.expit(bayes.logit(0.3) + math.log(3.0) + math.log(0.5))
    assert abs(post.probability - expected) < 1e-9
    assert [c.log_lr for c in post.contributions][2] == 0.0


def test_bayes_caps_single_indicator():
    post = bayes.update(0.5, [("huge", "present", 1000.0, 0.001, {})], max_lr=10)
    assert abs(post.log_odds - math.log(10)) < 1e-9


def test_panel_extremises_and_bounds():
    s = panel.aggregate([(0.7, 1.0), (0.8, 1.0), (0.75, 1.0)], extremise=1.3)
    assert s is not None and s.probability > s.raw_mean
    assert s.low == 0.7 and s.high == 0.8 and s.n == 3
    assert panel.aggregate([]) is None
    assert panel.aggregate([(0.999, 1.0)]).probability <= 0.98


def test_combine_blends_in_logit_space():
    assert panel.combine(0.6, None) == 0.6
    assert panel.combine(None, 0.4) == 0.4
    mid = panel.combine(0.2, 0.8, 0.5)
    assert abs(mid - 0.5) < 1e-9


def test_commit_chain_verifies_and_detects_tampering():
    rows = []
    prev = None
    for i in range(3):
        d = date(2026, 10, 1) + timedelta(days=i)
        h = commit_hash(prev, "q", d, 0.5 + i / 10, {"i": i})
        rows.append({"prev_hash": prev, "question_code": "q", "as_of": d, "final_prob": 0.5 + i / 10, "decomposition": {"i": i}, "commit_hash": h})
        prev = h
    assert verify_chain(rows) == (True, None)
    rows[1]["final_prob"] = 0.9
    assert verify_chain(rows)[0] is False


def test_scoring_skill_against_baseline():
    s = scoring.summarise([(0.9, 0.5, True), (0.1, 0.5, False)])
    assert s.mean_brier < s.baseline_brier and s.skill > 0
    assert scoring.summarise([]).n == 0


def test_positions_weight_actions_over_talk():
    today = date(2026, 10, 18)
    obs = [
        P.Observation(today - timedelta(days=2), "stated", -0.5, "cheap_talk", "spokesperson"),
        P.Observation(today - timedelta(days=3), "revealed", 0.9, "revealed_action", "institution"),
    ]
    stated = P.estimate(obs, today, track="stated")
    revealed = P.estimate(obs, today, track="revealed")
    assert stated.score == -0.5 and revealed.score == 0.9
    assert P.divergence(stated, revealed) == 0.7
    assert P.observation_weight(obs[1], today) > P.observation_weight(obs[0], today)


def test_positions_recency_decay_and_silence():
    today = date(2026, 10, 18)
    obs = [P.Observation(today - timedelta(days=d), "stated", 0.5, "cheap_talk", "minister") for d in range(20, 110, 7)]
    s = P.silence(obs, today)
    assert s["flagged"] is True and s["recent_count"] == 0
    assert P.estimate(obs, today, track="stated").score is not None


def test_change_points_detect_a_shift():
    pts = [(date(2026, 1, 1) + timedelta(days=7 * i), -0.5 if i < 8 else 0.6) for i in range(16)]
    cps = P.change_points(pts)
    assert cps and cps[0]["direction"] == "up"
