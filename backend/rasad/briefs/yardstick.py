"""PHIA probability yardstick (UK Common Analytical Standards, March 2025) with Arabic forms.

Bands: remote chance (to about 5 percent), highly unlikely (10 to 20), unlikely (25 to 35),
realistic possibility (40 to under 50), likely or probable (55 to 75), highly likely (80 to 90),
almost certain (95 and above). The gaps are deliberate in the doctrine; a number inside a gap
is mapped to the nearer band and the number is always shown beside the words.
"""

from __future__ import annotations

BANDS = [
    (0.0, 0.075, "remote chance", "احتمال بعيد"),
    (0.075, 0.225, "highly unlikely", "مستبعد جداً"),
    (0.225, 0.375, "unlikely", "مستبعد"),
    (0.375, 0.525, "realistic possibility", "احتمال واقعي"),
    (0.525, 0.775, "likely", "مرجح"),
    (0.775, 0.925, "highly likely", "مرجح جداً"),
    (0.925, 1.01, "almost certain", "شبه مؤكد"),
]


def band(p: float, lang: str = "en") -> str:
    for lo, hi, en, ar in BANDS:
        if lo <= p < hi:
            return ar if lang == "ar" else en
    return "almost certain" if lang == "en" else "شبه مؤكد"


def confidence_words(effective_evidence: int, synthetic_share: float, lang: str = "en") -> str:
    """Analytical confidence, reported separately from likelihood as the doctrine requires."""
    if synthetic_share > 0.3 or effective_evidence < 2:
        return ("low", "منخفضة")[lang == "ar"]
    if effective_evidence < 4:
        return ("moderate", "متوسطة")[lang == "ar"]
    return ("high", "عالية")[lang == "ar"]
