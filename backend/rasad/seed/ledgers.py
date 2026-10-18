"""Seed rows for the two ledgers and the series.

Each sourced row names its source in `prov`. Rows with `synthetic=True` are illustrative
and must be replaced by connector output before any client sees the board.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

WIKI_WAR = "https://en.wikipedia.org/wiki/2026_Iran_war"
WIKI_HORMUZ = "https://en.wikipedia.org/wiki/2026_Strait_of_Hormuz_crisis"
WIKI_SA = "https://en.wikipedia.org/wiki/Saudi_Arabia_in_the_2026_Iran_war"
WIKI_OM = "https://en.wikipedia.org/wiki/2026_Iranian_strikes_on_Oman"
GULFNEWS_UAE = "https://gulfnews.com/uae/uae-stands-resilient-one-month-after-more-than-2000-iranian-missile-and-drone-attacks-1.500489892"
AJ_QA = "https://www.aljazeera.com/news/2026/3/18/qatar-says-iran-missile-attack-sparks-fire-causes-damage-at-gas-facility"
KT_RIYADH = "https://www.khaleejtimes.com/world/gulf/yemen-houthis-claim-attacks-riyadh-king-khalid-international-airport-oct-2026"
AHRAM = "https://english.ahram.org.eg/News/579004.aspx"
JWLA = "https://lmalloyds.com/wp-content/uploads/2026/03/JWLA-033_Iran.pdf"
JMIC21 = "https://mscio.eu/media/documents/JMIC_Week_21_Dashboard.pdf"
UKMTO098 = "https://www.ukmto.org/-/media/ukmto/products/20260728-ukmto_advisory-098-26.pdf"
MARSH = "https://www.spglobal.com/energy/en/news-research/latest-news/shipping/072226-middle-east-shipping-insurance-costs-rise-on-hormuz-risks-marsh"
PLATTS_MAR = "https://www.spglobal.com/commodity-insights/en/news-research/latest-news/shipping/033026-war-risk-insurance-cost-off-highs-but-still-elevated-in-persian-gulf"
INS_JUL = "https://www.insurancebusinessmag.com/uk/news/marine/hormuz-warrisk-rates-surge-again-as-ceasefire-collapses-581985.aspx"
LL_RED = "https://www.lloydslist.com/LL1147660/Red-Sea-war-risk-rates-still-rising-after-doubling-in-past-week"
WM_HORMUZ = "https://www.worldmonitor.app/research/strait-of-hormuz-transit-report-2026-07/"
UKMOD = "https://www.gov.uk/government/news/gulf-air-defences-boosted-further-as-defence-secretary-visits-middle-east"
MWN_GCC = "https://www.moroccoworldnews.com/2025/09/259912/gcc-to-bolster-military-intelligence-alliance-following-qatar-summit/"
MAJALLA = "https://en.majalla.com/node/328576"
ARABNEWS = "https://www.arabnews.com/node/2641559/"
KT_FNC = "https://www.khaleejtimes.com/uae/uae-ready-to-take-all-necessary-measures-if-iran-attacks-again-says-official"
KT_AUG31 = "https://www.khaleejtimes.com/uae/gulf-countries-joint-missile-defence-system-respond-to-attacks"
BD_WAIVERS = "https://breakingdefense.com/2026/05/us-clears-8-6-billion-arms-sales-to-middle-east-countries-waiving-congressional-review/"
STATE_FMS = "https://www.state.gov/arms-sales-congressional-notifications/"
HORN = "https://hornreview.org/2026/07/08/the-gulf-in-the-aftermath-of-the-u-s-iran-war/"
HST_NOTAM = "https://www.hstoday.us/subject-matter-areas/transportation/military-action-restricts-air-transport-over-gulf-region/"


def P(src: str, url: str, grade: str = "B2") -> dict:
    return {"source": src, "url": url, "grade": grade}


# (date, event_type, location, country, actor, target, fatalities, severity, description_en, provenance, synthetic)
EVENTS: list[tuple] = [
    ("2026-02-28", "missile_strike", "Abu Dhabi", "AE", "IR", "AE", None, 5, "Iranian missile and drone strikes on the UAE in the first wave of retaliation after US and Israeli strikes on Iran.", P("Wikipedia, 2026 Iran war", WIKI_WAR), False),
    ("2026-02-28", "missile_strike", "Riyadh and Eastern Province", "SA", "IR", "SA", None, 5, "Iranian strikes on Riyadh and the Eastern Province from 28 February.", P("Wikipedia, Saudi Arabia in the 2026 Iran war", WIKI_SA), False),
    ("2026-02-28", "missile_strike", "Manama", "BH", "IR", "BH", None, 5, "Manama hit in the first wave; Fifth Fleet base reported inoperable by OSINT.", P("Wikipedia, 2026 Iran war", WIKI_WAR), False),
    ("2026-02-28", "maritime_attack", "Manama port", "BH", "IR", "BH", 1, 4, "The Stena Imperative struck in port, killing a port worker.", P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-02-28", "drone_strike", "Kuwait International Airport", "KW", "IR", "KW", None, 4, "Kuwait airport targeted on day one.", P("Wikipedia, 2026 Iran war", WIKI_WAR), False),
    ("2026-02-28", "maritime_attack", "Red Sea", "RED_SEA", "YE-HOUTHI", None, None, 4, "Houthi attacks on Red Sea shipping resumed on 28 February 2026.", P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-03-01", "drone_strike", "Ras Laffan and Mesaieed", "QA", "IR", "QA", None, 4, "Iranian drones struck Ras Laffan and Mesaieed around 1 to 2 March.", P("Wikipedia, 2026 Iran war", WIKI_WAR), False),
    ("2026-03-01", "missile_strike", "Duqm and Salalah ports", "OM", "IR", "OM", None, 4, "Duqm and Salalah ports struck repeatedly from 1 March.", P("Wikipedia, 2026 Iranian strikes on Oman", WIKI_OM), False),
    ("2026-03-02", "intercept", "Qatar airspace", "QA", "QA", "IR", None, 3, "Qatari air defences shot down two Iranian Su-24s around 2 March.", P("Wikipedia, 2026 Iran war", WIKI_WAR), False),
    ("2026-03-02", "missile_strike", "US embassy, Kuwait City", "KW", "IR", "US", None, 4, "US embassy in Kuwait struck on 2 March.", P("Wikipedia, 2026 Iran war", WIKI_WAR), False),
    ("2026-03-02", "closure", "Strait of Hormuz", "HORMUZ", "IR", None, None, 5, "IRGC confirmed closure of the Strait of Hormuz; traffic had fallen about 70 percent on 28 February.", P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-03-03", "insurer_listing", "Gulf, Gulf of Oman, Red Sea", "HORMUZ", None, None, None, 3, "JWLA-033 added Bahrain, Kuwait, Oman, Qatar and Djibouti to listed areas and widened the Gulf box.", P("Lloyd's JWC JWLA-033", JWLA, "A1"), False),
    ("2026-03-03", "missile_strike", "Ras Tanura", "SA", "IR", "SA", None, 5, "Ras Tanura hit on 3 to 4 March.", P("Wikipedia, Saudi Arabia in the 2026 Iran war", WIKI_SA), False),
    ("2026-03-04", "missile_strike", "Al Udeid Air Base", "QA", "IR", "US", None, 4, "Al Udeid targeted around 4 March.", P("Wikipedia, 2026 Iran war", WIKI_WAR), False),
    ("2026-03-08", "drone_strike", "Al-Kharj", "SA", "IR", "SA", 2, 4, "A drone killed two people in Al-Kharj around 8 March.", P("Wikipedia, Saudi Arabia in the 2026 Iran war", WIKI_SA), False),
    ("2026-03-10", "mine_warning", "Strait of Hormuz", "HORMUZ", "IR", None, None, 5, "Mines reportedly laid in the strait on 10 to 11 March.", P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-03-13", "missile_strike", "Prince Sultan Air Base", "SA", "IR", "US", None, 4, "Strikes damaged US tankers at Prince Sultan Air Base on 13 March.", P("Wikipedia, Saudi Arabia in the 2026 Iran war", WIKI_SA), False),
    ("2026-03-13", "missile_strike", "Kuwait", "KW", "IR", "KW", None, 4, "Kuwait reported damage to defence equipment and the airport on 13 March; 12 killed and 190 injured over the war.", P("Wikipedia, 2026 Iran war", WIKI_WAR), False),
    ("2026-03-13", "missile_strike", "Sohar", "OM", "IR", "OM", None, 4, "Sohar struck on 13 March.", P("Wikipedia, 2026 Iranian strikes on Oman", WIKI_OM), False),
    ("2026-03-18", "missile_strike", "Ras Laffan", "QA", "IR", "QA", None, 5, "Missile attack on Ras Laffan caused fires and significant damage; Qatar expelled Iran's military attaches within 24 hours.", P("Al Jazeera, 18 Mar 2026", AJ_QA, "B1"), False),
    ("2026-03-18", "expulsion", "Doha", "QA", "QA", "IR", None, 3, "Qatar expelled Iran's military attaches.", P("Al Jazeera, 18 Mar 2026", AJ_QA, "B1"), False),
    ("2026-03-21", "expulsion", "Riyadh", "SA", "SA", "IR", None, 3, "Saudi Arabia expelled Iranian defence officials.", P("Wikipedia, Saudi Arabia in the 2026 Iran war", WIKI_SA), False),
    ("2026-03-27", "missile_strike", "Prince Sultan Air Base", "SA", "IR", "US", None, 4, "Further strikes on 27 to 28 March damaged an E-3.", P("Wikipedia, Saudi Arabia in the 2026 Iran war", WIKI_SA), False),
    ("2026-03-29", "intercept", "UAE", "AE", "AE", "IR", 11, 3, "Official tally: 378 ballistic missiles, 15 cruise missiles and 1,835 drones, with 11 killed and 171 injured.", P("Gulf News, 29 Mar 2026", GULFNEWS_UAE, "B1"), False),
    ("2026-03-31", "deployment", "Saudi Arabia, Qatar, Kuwait", "SA", "UK", None, None, 2, "UK deployed Sky Sabre to Saudi Arabia, extended Typhoons in Qatar and sent ORCUS counter-drone detection to Kuwait.", P("UK MOD, 31 Mar 2026", UKMOD, "A1"), False),
    ("2026-04-08", "ceasefire", "Region", "HORMUZ", "IR", "US", None, 2, "Ceasefire took effect on 8 April; brief reopening of the strait.", P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-05-20", "mine_warning", "Arabian Gulf, Hormuz, Gulf of Oman", "HORMUZ", None, None, None, 4, "JMIC week 21 dashboard rated the Gulf, Hormuz and Gulf of Oman CRITICAL with a mine warning.", P("JMIC Week 21 dashboard", JMIC21, "A2"), False),
    ("2026-06-17", "ceasefire", "Islamabad", "HORMUZ", "IR", "US", None, 2, "Islamabad Memorandum produced a brief reopening of the strait.", P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-07-08", "closure", "Strait of Hormuz", "HORMUZ", "IR", None, None, 5, "Truce collapsed on 8 July; Iran re-closed the strait.", P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-07-28", "maritime_attack", "Southern Red Sea", "RED_SEA", "YE-HOUTHI", None, None, 3, "UKMTO advisory 098-26 reported an explosion in the southern Red Sea.", P("UKMTO advisory 098-26", UKMTO098, "A2"), False),
    ("2026-08-12", "maritime_attack", "Bab al-Mandab", "RED_SEA", "YE-HOUTHI", "SA", None, 4, "Houthi strike on a Saudi vessel in Bab al-Mandab.", P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-08-31", "intercept", "UAE territorial waters", "AE", "AE", "IR", None, 3, "An Iranian drone was intercepted over UAE waters.", P("Khaleej Times, 15 Oct 2026", KT_AUG31, "B2"), False),
    ("2026-10-05", "drone_strike", "Saudi airport (unspecified)", "SA", "YE-HOUTHI", "SA", None, 3, "First of the October airport attacks; five Saudi airports attacked since 5 October with 20 deaths by 14 October.", P("Shafaq and AFP via Ahram, 14 to 15 Oct 2026", AHRAM, "C3"), True),
    ("2026-10-10", "missile_strike", "King Khalid International Airport, Riyadh", "SA", "YE-HOUTHI", "SA", 13, 5, "Strike on Riyadh's King Khalid airport killed 12 to 13 people with more than 300 injured.", P("Khaleej Times, 11 Oct 2026", KT_RIYADH, "B1"), False),
    ("2026-10-13", "drone_strike", "Dammam airport and Dhahran", "SA", "YE-HOUTHI", "SA", None, 4, "Houthis claimed attacks on Riyadh airport, Dammam and an Aramco building in Dhahran on 13 to 14 October.", P("Ahram/AFP, 15 Oct 2026", AHRAM, "B2"), False),
]

# (date, series, value, unit, source, synthetic)
SERIES_ANCHORS: list[tuple] = [
    ("2026-02-15", "war_risk_premium_hormuz_pct", 0.12, "pct_hull", "Platts, 30 Mar 2026 (pre-war 0.1 to 0.15)", False),
    ("2026-03-10", "war_risk_premium_hormuz_pct", 2.5, "pct_hull", "Platts, 30 Mar 2026 (March peak)", False),
    ("2026-03-30", "war_risk_premium_hormuz_pct", 1.0, "pct_hull", "Platts, 30 Mar 2026", False),
    ("2026-05-15", "war_risk_premium_hormuz_pct", 0.8, "pct_hull", "demo interpolation", True),
    ("2026-07-10", "war_risk_premium_hormuz_pct", 4.0, "pct_hull", "Insurance Business, 10 Jul 2026 (2 to 6 percent per transit)", False),
    ("2026-07-22", "war_risk_premium_hormuz_pct", 8.75, "pct_hull", "Marsh via Platts, 22 Jul 2026 (7.5 to 10 percent)", False),
    ("2026-09-15", "war_risk_premium_hormuz_pct", 7.0, "pct_hull", "demo interpolation", True),
    ("2026-10-15", "war_risk_premium_hormuz_pct", 7.5, "pct_hull", "demo interpolation", True),
    ("2026-07-22", "war_risk_premium_red_sea_pct", 0.5, "pct_hull", "Marsh via Platts, 22 Jul 2026", False),
    ("2026-07-30", "war_risk_premium_red_sea_pct", 1.5, "pct_hull", "Lloyd's List, 30 Jul 2026 (1 to 2 percent)", False),
    ("2026-10-15", "war_risk_premium_red_sea_pct", 1.2, "pct_hull", "demo interpolation", True),
    ("2026-01-01", "jwc_gcc_states_listed", 2, "count", "demo assumption: Saudi Arabia and the UAE in the pre-war Gulf box", True),
    ("2026-03-03", "jwc_gcc_states_listed", 6, "count", "JWLA-033, 3 Mar 2026", False),
]


def hormuz_transit_series(start: date, end: date, seed: int = 7) -> list[tuple[date, float, bool]]:
    """Synthetic daily transits shaped by sourced anchors: 103.2 a day in 2025; 9.9 a day from
    1 March 2026 (PortWatch via World Monitor); brief reopenings after 8 April and 17 June;
    re-closure from 8 July; attacks continuing into October. Every row is flagged synthetic."""
    rng = random.Random(seed)
    out = []
    d = start
    while d <= end:
        if d < date(2026, 2, 28):
            level = 103.2
        elif d < date(2026, 4, 8):
            level = 9.9 if d >= date(2026, 3, 1) else 31.0
        elif d < date(2026, 6, 17):
            level = 38.0
        elif d < date(2026, 7, 8):
            level = 55.0
        elif d < date(2026, 10, 2):
            level = 14.0
        else:
            level = 11.0
        value = max(0.0, level + rng.gauss(0, level * 0.12) + 3 * math.sin(d.toordinal() / 3.7))
        out.append((d, round(value, 1), True))
        d += timedelta(days=1)
    return out


def bab_el_mandeb_series(start: date, end: date, seed: int = 11) -> list[tuple[date, float, bool]]:
    rng = random.Random(seed)
    out = []
    d = start
    while d <= end:
        level = 28.0 if d < date(2026, 2, 28) else 16.0
        if d >= date(2026, 8, 12):
            level = 12.0
        out.append((d, round(max(0.0, level + rng.gauss(0, 2.5)), 1), True))
        d += timedelta(days=1)
    return out


# Policy observations: (date, actor, issue, track, channel, cost_class, speaker_level, lang, score, grade, excerpt, excerpt_en, provenance, synthetic)
OBSERVATIONS: list[tuple] = [
    # GCC integration agenda (sourced)
    ("2025-09-18", "GCC", "gcc_defence_integration", "stated", "communique", "hands_tying", "institution", "en", 0.6, "B2",
     "GCC Unified Military Command announced five actions: more intelligence sharing, a shared air picture, an accelerated ballistic missile early-warning system, updated joint defence plans and joint air defence exercises.", None, P("Morocco World News, 19 Sep 2025", MWN_GCC), False),
    ("2025-12-03", "GCC", "gcc_defence_integration", "stated", "communique", "hands_tying", "head_of_state", "en", 0.7, "B1",
     "46th GCC Summit in Manama adopted One Region, One Security, finalised a joint air and missile defence shield concept and adopted a GCC Vision for Regional Security.", None, P("Al Majalla, 5 Dec 2025", MAJALLA), False),
    ("2026-04-28", "GCC", "gcc_defence_integration", "stated", "communique", "hands_tying", "head_of_state", "en", 0.8, "B1",
     "Jeddah consultative summit directed the Secretariat to expedite the ballistic missile early-warning system and declared Gulf security indivisible.", None, P("Arab News, 28 Apr 2026", ARABNEWS), False),
    # Qatar and Saudi Arabia on Iran (sourced, revealed)
    ("2026-03-18", "QA", "engagement_with_iran", "revealed", "event", "revealed_action", "head_of_state", "en", -0.8, "B1",
     "Qatar expelled Iran's military attaches within 24 hours of the Ras Laffan attack.", None, P("Al Jazeera, 18 Mar 2026", AJ_QA), False),
    ("2026-03-21", "SA", "engagement_with_iran", "revealed", "event", "revealed_action", "head_of_state", "en", -0.8, "B2",
     "Saudi Arabia expelled Iranian defence officials.", None, P("Wikipedia, Saudi Arabia in the 2026 Iran war", WIKI_SA), False),
    ("2026-03-26", "SA", "strike_willingness", "stated", "statement", "hands_tying", "minister", "ar", 0.3, "B2",
     "Saudi cabinet pledged all necessary measures to defend the Kingdom.", "The cabinet pledged all necessary measures to defend the Kingdom.", P("Wikipedia, Saudi Arabia in the 2026 Iran war", WIKI_SA), False),
    # UAE (sourced)
    ("2026-10-15", "AE", "strike_willingness", "stated", "statement", "cheap_talk", "legislature", "en", 0.4, "B2",
     "FNC defence committee chair said all options remain open if Iran strikes again.", None, P("Khaleej Times, 15 Oct 2026", KT_FNC), False),
    ("2026-10-15", "AE", "gcc_defence_integration", "stated", "interview", "cheap_talk", "institution", "en", 0.5, "B2",
     "Adviser in the foreign minister's office: the decisive work must be done before a crisis, rules of engagement pre-agreed, and radar and command systems from different partners made to interoperate.", None, P("Khaleej Times, 15 Oct 2026", KT_AUG31), False),
    # United Kingdom (sourced, revealed)
    ("2026-03-31", "UK", "gulf_force_posture", "revealed", "deployment", "revealed_action", "minister", "en", 0.6, "A1",
     "Sky Sabre deployed to Saudi Arabia, Typhoons extended in Qatar, ORCUS counter-drone detection sent to Kuwait.", None, P("UK MOD, 31 Mar 2026", UKMOD), False),
    # United States (sourced, revealed)
    ("2026-02-28", "US", "strike_willingness", "revealed", "event", "revealed_action", "head_of_state", "en", 1.0, "A1",
     "US and Israeli strikes on Iran (Operation Epic Fury) killed the Supreme Leader.", None, P("Wikipedia, 2026 Iran war", WIKI_WAR), False),
    ("2026-02-12", "US", "gulf_force_posture", "revealed", "notification", "revealed_action", "institution", "en", -0.2, "A1",
     "FAA NOTAM barred US operators from Iran, the Baghdad FIR, the Persian Gulf and the Gulf of Oman.", None, P("HSToday, 12 Feb 2026", HST_NOTAM), False),
    ("2026-04-08", "US", "strike_willingness", "revealed", "event", "revealed_action", "head_of_state", "en", -0.5, "A1",
     "Ceasefire took effect on 8 April.", None, P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-05-12", "US", "gulf_force_posture", "revealed", "notification", "sunk_cost", "institution", "en", 0.5, "A1",
     "USD 8.6bn of arms sales to Middle East countries cleared with congressional review waived.", None, P("Breaking Defense, May 2026", BD_WAIVERS), False),
    ("2026-07-08", "US", "strike_willingness", "revealed", "event", "revealed_action", "head_of_state", "en", 0.4, "B2",
     "Truce collapsed on 8 July.", None, P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-09-17", "US", "gulf_force_posture", "revealed", "notification", "sunk_cost", "institution", "en", 0.4, "A1",
     "State Department notified Congress of an F-35 sale to Saudi Arabia.", None, P("State Department notifications via Forum on the Arms Trade, Oct 2026", STATE_FMS), False),
    ("2026-10-02", "US", "gulf_force_posture", "revealed", "notification", "sunk_cost", "institution", "en", 0.4, "A1",
     "Notifications for Patriot to Kuwait and APKWS to the UAE.", None, P("State Department notifications via Forum on the Arms Trade, Oct 2026", STATE_FMS), False),
    # Iran (sourced, revealed)
    ("2026-03-02", "IR", "hormuz_posture", "revealed", "event", "revealed_action", "institution", "fa", 1.0, "B2",
     "IRGC confirmed closure of the Strait of Hormuz.", None, P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-03-10", "IR", "hormuz_posture", "revealed", "event", "revealed_action", "institution", "fa", 1.0, "B2",
     "Mines reportedly laid on 10 to 11 March.", None, P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-04-08", "IR", "hormuz_posture", "revealed", "event", "revealed_action", "head_of_state", "fa", -0.4, "B2",
     "Ceasefire and brief reopening of the strait.", None, P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-06-17", "IR", "hormuz_posture", "revealed", "event", "revealed_action", "head_of_state", "fa", -0.6, "B2",
     "Islamabad Memorandum; brief reopening.", None, P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-07-08", "IR", "hormuz_posture", "revealed", "event", "revealed_action", "institution", "fa", 0.9, "B2",
     "Strait re-closed as the truce collapsed.", None, P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-10-05", "IR", "hormuz_posture", "revealed", "event", "revealed_action", "institution", "fa", 0.8, "B2",
     "Attacks on tankers off the UAE and Qatar continued into October.", None, P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    # Iran stated track (synthetic: illustrative statements to exercise the stated-versus-revealed divergence)
    ("2026-06-20", "IR", "hormuz_posture", "stated", "statement", "cheap_talk", "minister", "fa", -0.5, "B3",
     "مقام وزارت خارجه: تنگه هرمز برای کشتیرانی غیرخصمانه باز است.", "Foreign ministry official: the strait is open to non-hostile shipping.", P("Demo statement", "", "B3"), True),
    ("2026-07-12", "IR", "hormuz_posture", "stated", "statement", "hands_tying", "institution", "fa", 0.6, "B3",
     "سپاه: عبور از تنگه منوط به مجوز است.", "IRGC: passage through the strait is subject to authorisation.", P("Demo statement", "", "B3"), True),
    ("2026-08-15", "IR", "hormuz_posture", "stated", "speech", "cheap_talk", "head_of_state", "fa", 0.3, "B3",
     "رئیس‌جمهور: امنیت خلیج فارس مسئولیت کشورهای منطقه است، نه بیگانگان.", "President: Gulf security is the responsibility of regional states, not outsiders.", P("Demo statement", "", "B3"), True),
    ("2026-09-20", "IR", "hormuz_posture", "stated", "statement", "cheap_talk", "spokesperson", "fa", -0.3, "B3",
     "سخنگو: ایران آماده گفتگو درباره امنیت دریانوردی است.", "Spokesperson: Iran is ready for talks on maritime security.", P("Demo statement", "", "B3"), True),
    ("2026-10-08", "IR", "hormuz_posture", "stated", "statement", "cheap_talk", "spokesperson", "fa", -0.2, "B3",
     "سخنگو: مسئولیت ناامنی بر عهده حضور نظامی بیگانه است.", "Spokesperson: responsibility for insecurity lies with foreign military presence.", P("Demo statement", "", "B3"), True),
    ("2026-09-01", "IR", "nuclear_threshold", "stated", "statement", "cheap_talk", "spokesperson", "fa", 0.2, "B3",
     "سخنگو: برنامه صلح‌آمیز است و بازرسی‌ها مشروط است.", "Spokesperson: the programme is peaceful and inspections are conditional.", P("Demo statement", "", "B3"), True),
    ("2026-08-01", "IR", "proxy_activation", "stated", "statement", "cheap_talk", "institution", "fa", 0.3, "B3",
     "سپاه: محور مقاومت آماده پاسخ است.", "IRGC: the axis of resistance is ready to respond.", P("Demo statement", "", "B3"), True),
    # Houthis (sourced revealed; synthetic stated)
    ("2026-02-28", "YE-HOUTHI", "red_sea_attacks", "revealed", "event", "revealed_action", "institution", "ar", 0.9, "B2",
     "Red Sea attacks resumed on 28 February 2026.", None, P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-08-12", "YE-HOUTHI", "red_sea_attacks", "revealed", "event", "revealed_action", "institution", "ar", 0.8, "B2",
     "Strike on a Saudi vessel in Bab al-Mandab.", None, P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    ("2026-07-15", "YE-HOUTHI", "yemen_front", "revealed", "event", "revealed_action", "institution", "ar", 0.7, "B2",
     "Yemen's war restarted in July 2026.", None, P("Khaleej Times, 11 Oct 2026", KT_RIYADH), False),
    ("2026-10-10", "YE-HOUTHI", "yemen_front", "revealed", "event", "revealed_action", "institution", "ar", 1.0, "B1",
     "Strike on Riyadh's King Khalid airport.", None, P("Khaleej Times, 11 Oct 2026", KT_RIYADH), False),
    ("2026-10-14", "YE-HOUTHI", "yemen_front", "revealed", "event", "revealed_action", "institution", "ar", 1.0, "B2",
     "Claimed attacks on Riyadh airport, Dammam and Dhahran.", None, P("Ahram/AFP, 15 Oct 2026", AHRAM), False),
    ("2026-10-11", "YE-HOUTHI", "yemen_front", "stated", "statement", "hands_tying", "institution", "ar", 0.9, "B3",
     "المتحدث العسكري: العمليات ضد المطارات السعودية مستمرة.", "Military spokesman: operations against Saudi airports continue.", P("Demo statement", "", "B3"), True),
    ("2026-09-05", "YE-HOUTHI", "red_sea_attacks", "stated", "statement", "hands_tying", "institution", "ar", 0.7, "B3",
     "المتحدث: استهداف السفن المرتبطة بالعدو سيستمر.", "Spokesman: targeting of vessels linked to the enemy will continue.", P("Demo statement", "", "B3"), True),
    # Israel (sourced revealed)
    ("2026-02-28", "IL", "strike_willingness", "revealed", "event", "revealed_action", "head_of_state", "he", 1.0, "A1",
     "Israeli strikes on Iran with the US on 28 February.", None, P("Wikipedia, 2026 Iran war", WIKI_WAR), False),
    ("2026-04-08", "IL", "strike_willingness", "revealed", "event", "revealed_action", "head_of_state", "he", -0.4, "B2",
     "Ceasefire of 8 April.", None, P("Wikipedia, 2026 Strait of Hormuz crisis", WIKI_HORMUZ), False),
    # US stated track (synthetic, to exercise divergence)
    ("2026-09-10", "US", "gulf_force_posture", "stated", "statement", "cheap_talk", "spokesperson", "en", 0.3, "B3",
     "Spokesperson: the United States remains committed to the security of its Gulf partners.", None, P("Demo statement", "", "B3"), True),
    ("2026-10-01", "US", "gulf_force_posture", "stated", "interview", "cheap_talk", "minister", "en", -0.3, "B3",
     "Secretary: partners must carry more of the burden; force levels will be reviewed.", None, P("Demo statement", "", "B3"), True),
    ("2026-10-12", "US", "gulf_force_posture", "stated", "statement", "cheap_talk", "spokesperson", "en", -0.2, "B3",
     "Spokesperson: no decisions on posture have been made.", None, P("Demo statement", "", "B3"), True),
    ("2026-09-25", "US", "sanctions_enforcement_iran", "revealed", "event", "revealed_action", "institution", "en", 0.8, "B2",
     "Blockade of Iranian exports in force; Iranian loadings reported at 50,789 bpd in September.", None, P("UANI tanker tracker, 7 Oct 2026", "https://www.unitedagainstnucleariran.com/tanker-tracker"), False),
]

# Panel seats (demo). Forecasts are illustrative.
FORECASTERS = [
    ("seat1", "Panel seat 1 (demo)", "human", 1.0),
    ("seat2", "Panel seat 2 (demo)", "human", 1.0),
    ("seat3", "Panel seat 3 (demo)", "human", 1.1),
    ("seat4", "Panel seat 4 (demo)", "human", 0.9),
    ("seat5", "Panel seat 5 (demo)", "human", 1.0),
    ("seat6", "Panel seat 6 (demo)", "human", 1.0),
    ("llm_ensemble", "Machine ensemble (not configured)", "machine", 1.0),
]

# question -> list of (seat, probability) for the latest panel round (demo)
PANEL_ROUND = {
    "gulf_infra_strike_90": [("seat1", 0.72), ("seat2", 0.65), ("seat3", 0.8), ("seat4", 0.6), ("seat5", 0.7), ("seat6", 0.68)],
    "hormuz_closure_90": [("seat1", 0.7), ("seat2", 0.6), ("seat3", 0.75), ("seat4", 0.55), ("seat5", 0.65), ("seat6", 0.62)],
    "red_sea_attacks_60": [("seat1", 0.78), ("seat2", 0.7), ("seat3", 0.82), ("seat4", 0.65), ("seat5", 0.74), ("seat6", 0.7)],
    "israel_iran_exchange_60": [("seat1", 0.3), ("seat2", 0.35), ("seat3", 0.4), ("seat4", 0.25), ("seat5", 0.3), ("seat6", 0.33)],
    "cyber_cni_90": [("seat1", 0.35), ("seat2", 0.4), ("seat3", 0.3), ("seat4", 0.45), ("seat5", 0.35), ("seat6", 0.38)],
    "iraq_groups_90": [("seat1", 0.3), ("seat2", 0.25), ("seat3", 0.35), ("seat4", 0.2), ("seat5", 0.3), ("seat6", 0.28)],
    "yemen_escalation_sa_90": [("seat1", 0.85), ("seat2", 0.8), ("seat3", 0.9), ("seat4", 0.75), ("seat5", 0.82), ("seat6", 0.8)],
    "us_posture_change_180": [("seat1", 0.35), ("seat2", 0.4), ("seat3", 0.3), ("seat4", 0.45), ("seat5", 0.38), ("seat6", 0.36)],
    "sanctions_gulf_entity_90": [("seat1", 0.6), ("seat2", 0.55), ("seat3", 0.65), ("seat4", 0.5), ("seat5", 0.58), ("seat6", 0.6)],
    "gcc_rupture_180": [("seat1", 0.05), ("seat2", 0.08), ("seat3", 0.04), ("seat4", 0.1), ("seat5", 0.06), ("seat6", 0.05)],
}
