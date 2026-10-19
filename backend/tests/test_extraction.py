from datetime import date

from rasad.extraction import rules
from rasad.extraction.service import _numbers, _numbers_agree, _same_story

D = date(2026, 10, 18)


def _types(text, lang="en"):
    return [(e.event_type, e.country) for e in rules.extract(text, D, lang).events]


def test_arabic_words_with_other_senses_do_not_fire():
    assert _types("الأمانة العامة تعلن بدء مشروع تطوير البنية التحتية ضمن مسيرة التنمية في قطر", "ar") == []  # a path, not a drone
    assert _types("أبدت قطر اعتراضها على القرار", "ar") == []  # an objection, not an interception


def test_interceptions_are_not_strikes_and_places_are_found():
    assert _types("قوات التحالف تعلن اعتراض وتدمير طائرتين مسيرتين بالمنطقة الشرقية", "ar") == [("intercept", "SA")]
    assert _types("Coalition Announces Intercepting Drone in Saudi Arabia's Eastern Province") == [("intercept", "SA")]
    assert _types("Houthi drone attack hits Jizan airport; two killed") == [("drone_strike", "SA")]
    assert _types("Oil tanker on fire after hitting mine in Hormuz : Iran Guards") == [("maritime_attack", "HORMUZ")]
    assert _types("Zelensky calls EU leaders as Trump ceasefire collapses") == [("ceasefire", None)]  # dropped at ingest: no Gulf geography


def test_story_matching_respects_counts_and_dates():
    assert _numbers("قوات التحالف: اعتراض وتدمير 4 مسيرات الرياض في 17 أكتوبر") == {"4"}
    assert _numbers("Coalition: Two Drones Intercepted, Riyadh, October 17 (QNA)") == {"2"}
    assert not _same_story("Coalition: Two Drones Intercepted and Destroyed in Riyadh", "Coalition: Four Drones Intercepted and Destroyed in Riyadh", 0.25)
    assert _same_story("CENTCOM claims Iran unable to finance proxy militia amid US naval blockade aninews.in India",
                       "CENTCOM claims Iran unable to finance proxy militia amid US naval blockade iraqsun.com Iraq")
    assert _numbers_agree("Four UAVs intercepted", "اعتراض وتدمير 4 مسيرات") and not _numbers_agree("Four UAVs intercepted", "اعتراض طائرة مسيرة")
