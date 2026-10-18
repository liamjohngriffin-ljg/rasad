"""Lexicon-based extraction. Deliberately simple and transparent: it exists so the pipeline
runs with no model at all, and so a reviewer can see why a row was proposed. Confidence is
capped at 0.45 and the verification quota for Arabic and Farsi is higher than for English."""

from __future__ import annotations

import re
from datetime import date

from .schema import ExtractedEvent, ExtractedObservation, ExtractionResult

EVENT_LEXICON = [
    # (event_type, severity, patterns in en / ar / fa)
    ("missile_strike", 4, [r"\bmissile (strike|attack)s?\b", r"\bballistic missile", r"صاروخ", r"صواريخ", r"موشک"]),
    ("drone_strike", 3, [r"\bdrone (strike|attack)s?\b", r"\buav\b", r"مسيّرة", r"مسيرة", r"طائرات مسيرة", r"پهپاد"]),
    ("intercept", 2, [r"\bintercept(ed|ion)\b", r"اعتراض", r"اعترضت", r"رهگیری"]),
    ("maritime_attack", 4, [r"\b(tanker|vessel|ship)[^.]{0,60}(attack|struck|hit|explosion)", r"هجوم على (ناقلة|سفينة)", r"استهداف (ناقلة|سفينة)", r"حمله به (نفتکش|کشتی)"]),
    ("seizure", 4, [r"\b(seized|seizure|detained)[^.]{0,40}(tanker|vessel|ship)", r"احتجاز (ناقلة|سفينة)", r"توقیف (نفتکش|کشتی)"]),
    ("cyber_incident", 3, [r"\bcyber ?attack\b", r"\bransomware\b", r"هجوم سيبراني", r"حمله سایبری"]),
    ("airspace_closure", 2, [r"\bairspace (closed|closure)\b", r"إغلاق المجال الجوي", r"بستن حریم هوایی"]),
    ("expulsion", 3, [r"\bexpel(led|s)?\b[^.]{0,60}(attach|diplomat|official)", r"طرد (الملحق|الدبلوماسي|المسؤولين)", r"اخراج (وابسته|دیپلمات)"]),
    ("ceasefire", 2, [r"\bceasefire\b", r"\btruce\b", r"وقف إطلاق النار", r"هدنة", r"آتش‌بس", r"آتش بس"]),
    ("exercise", 1, [r"\b(military|naval|joint) exercise", r"مناورات", r"تمرين عسكري", r"رزمایش"]),
    ("deployment", 2, [r"\bdeploy(ed|ment|s)\b", r"نشر (قوات|بطاريات|منظومة)", r"استقرار (نیرو|سامانه)"]),
]

COUNTRY_LEXICON = {
    "SA": [r"saudi", r"riyadh", r"السعودية", r"الرياض", r"عربستان"],
    "AE": [r"\buae\b", r"emirates", r"abu dhabi", r"dubai", r"الإمارات", r"أبوظبي", r"دبي", r"امارات"],
    "QA": [r"qatar", r"doha", r"قطر", r"الدوحة"],
    "KW": [r"kuwait", r"الكويت", r"کویت"],
    "BH": [r"bahrain", r"manama", r"البحرين", r"المنامة", r"بحرین"],
    "OM": [r"\boman\b", r"muscat", r"عمان", r"مسقط"],
    "IR": [r"\biran", r"tehran", r"إيران", r"طهران", r"ایران", r"تهران"],
    "IQ": [r"\biraq", r"baghdad", r"العراق", r"بغداد", r"عراق"],
    "YE": [r"yemen", r"sanaa", r"hodeidah", r"اليمن", r"صنعاء", r"الحديدة", r"یمن"],
    "IL": [r"israel", r"tel aviv", r"إسرائيل", r"اسرائیل"],
    "HORMUZ": [r"hormuz", r"هرمز"],
    "RED_SEA": [r"red sea", r"bab[- ]?(al|el)[- ]?mand", r"البحر الأحمر", r"باب المندب", r"دریای سرخ"],
}

ACTOR_LEXICON = {
    "YE-HOUTHI": [r"houthi", r"ansar ?allah", r"الحوثي", r"أنصار الله", r"حوثی"],
    "IR": [r"\birgc\b", r"revolutionary guard", r"الحرس الثوري", r"سپاه"],
    "US": [r"\bu\.?s\.?\b", r"united states", r"pentagon", r"centcom", r"الولايات المتحدة", r"أمريك", r"آمریکا"],
    "IL": [r"\bidf\b", r"israeli", r"الجيش الإسرائيلي", r"اسرائیل"],
}

# Stance lexicons per issue: (regex, score). Scores are crude by design.
STANCE_LEXICON = {
    "hormuz_posture": [
        (r"(close|closure of|closing) (the )?strait", 0.8), (r"إغلاق (مضيق|المضيق)", 0.8), (r"بستن تنگه", 0.8),
        (r"(subject to|requires?) (authori[sz]ation|permission)", 0.6), (r"بإذن", 0.5), (r"مجوز", 0.5),
        (r"open to (all|non-hostile|commercial) shipping", -0.5), (r"حرية الملاحة", -0.5), (r"آزادی کشتیرانی", -0.5), (r"باز است", -0.4),
        (r"ready for (talks|dialogue|negotiat)", -0.4), (r"مستعدة للحوار", -0.4), (r"آماده (گفتگو|مذاکره)", -0.4),
    ],
    "gulf_force_posture": [
        (r"(reinforc|surge|deploy(ing|ment of) additional|carrier strike group arriv)", 0.6), (r"(drawdown|withdraw|reduce (our )?(presence|forces)|burden[- ]sharing)", -0.5), (r"remain(s)? committed to", 0.2),
    ],
    "strike_willingness": [
        (r"(all options|military option) (are|is|remain) (on the table|open)", 0.4), (r"(will|would) (respond|retaliate)", 0.4), (r"سترد", 0.4), (r"پاسخ (قاطع|سخت)", 0.4), (r"(restraint|de-escalat|calm)", -0.4), (r"ضبط النفس", -0.4), (r"خویشتن‌داری", -0.4),
    ],
    "gcc_defence_integration": [
        (r"(joint|unified|integrated) (air|missile|defen[cs]e|command)", 0.6), (r"(دفاع|قيادة) (مشترك|موحد)", 0.6), (r"one region, one security", 0.6),
    ],
    "engagement_with_iran": [
        (r"(dialogue|engagement|talks) with (iran|tehran)", 0.5), (r"(الحوار|التواصل) مع (إيران|طهران)", 0.5), (r"(expel|sever|cut) (diplomatic|ties|relations)", -0.7), (r"طرد", -0.6),
    ],
    "red_sea_attacks": [
        (r"(will|shall) (continue|resume) (targeting|attacks|operations)", 0.7), (r"ستستمر (العمليات|الهجمات)", 0.7), (r"(halt|pause|suspend) (attacks|operations)", -0.6), (r"وقف (العمليات|الهجمات)", -0.6),
    ],
    "yemen_front": [
        (r"(saudi|riyadh)[^.]{0,80}(target|operation|strike)", 0.6), (r"(استهداف|عملية)[^.]{0,60}(السعودية|الرياض)", 0.6), (r"(truce|ceasefire) with (saudi|the coalition)", -0.6), (r"هدنة", -0.5),
    ],
    "nuclear_threshold": [
        (r"(enrich(ment)? to|60 ?%|90 ?%|weapon)", 0.6), (r"تخصيب", 0.5), (r"غنی‌سازی", 0.5), (r"(inspect|safeguard|cooperat)[^.]{0,30}(iaea|agency)", -0.4), (r"الوكالة الدولية", -0.3), (r"آژانس", -0.3),
    ],
    "sanctions_enforcement_iran": [
        (r"(maximum pressure|designat|blockade|interdict)", 0.6), (r"(waiver|relief|ease sanctions)", -0.6),
    ],
    "proxy_activation": [
        (r"(axis of resistance|resistance front)[^.]{0,40}(ready|respond)", 0.5), (r"محور (المقاومة|مقاومت)", 0.4), (r"(restrain|disarm)[^.]{0,30}(militia|proxies)", -0.5),
    ],
}

SPEAKER_LEXICON = [
    ("head_of_state", [r"\b(president|emir|king|crown prince|supreme leader|prime minister)\b", r"(الرئيس|الأمير|الملك|ولي العهد|المرشد|رئيس الوزراء)", r"(رئیس‌جمهور|رهبر)"]),
    ("spokesperson", [r"\bspokes(man|woman|person)\b", r"المتحدث", r"سخنگو"]),
    ("minister", [r"\b(minister|secretary of (state|defen[cs]e))\b", r"وزير", r"وزیر"]),
    ("institution", [r"\b(irgc|ministry|general staff|command|cabinet|council)\b", r"(الحرس الثوري|وزارة|هيئة الأركان|القيادة|مجلس)", r"(سپاه|ستاد|وزارت)"]),
]


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def _first(lexicon: dict[str, list[str]], text: str) -> str | None:
    for code, patterns in lexicon.items():
        if _any(patterns, text):
            return code
    return None


def extract(text: str, published: date, language: str = "en") -> ExtractionResult:
    text_norm = " ".join(text.split())
    events: list[ExtractedEvent] = []
    for etype, sev, patterns in EVENT_LEXICON:
        if _any(patterns, text_norm):
            country = _first(COUNTRY_LEXICON, text_norm)
            actor = _first(ACTOR_LEXICON, text_norm)
            events.append(ExtractedEvent(event_date=published, event_type=etype, country=country, actor=actor, severity=sev, description_en=text_norm[:400], confidence=0.4 if language == "en" else 0.3, quote=text_norm[:200]))
            break
    observations: list[ExtractedObservation] = []
    speaker = next((lvl for lvl, pats in SPEAKER_LEXICON if _any(pats, text_norm)), "official_media")
    actor = _first(ACTOR_LEXICON, text_norm) or _first({k: v for k, v in COUNTRY_LEXICON.items() if k not in ("HORMUZ", "RED_SEA")}, text_norm)
    if actor:
        for issue, rules in STANCE_LEXICON.items():
            hits = [(s, p) for p, s in rules if re.search(p, text_norm, re.I)]
            if hits:
                score = max(min(sum(s for s, _ in hits) / len(hits), 1.0), -1.0)
                observations.append(ExtractedObservation(actor=actor, issue=issue, observed_at=published, track="stated", channel="statement", cost_class="cheap_talk", speaker_level=speaker, score=round(score, 2), confidence=0.45 if language == "en" else 0.35, quote=text_norm[:300]))
    return ExtractionResult(events=events, observations=observations, provider="rules")
