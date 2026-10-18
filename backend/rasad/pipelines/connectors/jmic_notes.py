"""JMIC advisory notes (CMF / UKMTO, mscio.eu): the dated situation notes issued during the
2025 Israel-Iran strikes (JMIC# 008-25) and the 2026 regional war (JMIC# 001-26, updates
001 onward).

Three generations of layout exist and the parser reads all of them from the extracted text,
with pdfplumber tables used where the PDF carries ruled tables:

* a header block "Regional Threat Level : CRITICAL" and a date range "01 March – 9 April 2026"
* area levels in prose ("Bab el-Mandeb Strait and Gulf of Aden remain at a MODERATE threat
  level") or, from mid-April 2026, a "Regional Threat Overview" table
* operational indicators ("Vessel attacks past 48 hours: 0", "30 April: 10 transits")
* confirmed vessel incidents: UKMTO incident numbers in the daily table (March) and the
  cumulative "Confirmed Maritime Security Incidents" annex (dated, vessel-named, from mid-March)
* dated incidents in the operational summary (skiff approaches, boardings, small-craft attacks)
* marine infrastructure attacks with dates in prose
* S&P AIS transit tables for the Strait of Hormuz and Bab el-Mandeb (cargo and tankers)
* NAVAREA mine warnings with positions, and the count of vessels held off Somalia

Everything that becomes a ThreatEvent lands `pending`; series points carry the note as source.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import SeriesPoint, ThreatEvent
from .base import RawDoc, fetch_bytes, upsert_document

SOURCE = "jmic"
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
LEVELS = {"LOW": 1, "MODERATE": 2, "ELEVATED": 3, "SUBSTANTIAL": 3, "SIGNIFICANT": 4, "SEVERE": 4, "HIGH": 4, "CRITICAL": 5}
LEVEL_RE = r"(LOW|MODERATE|ELEVATED|SUBSTANTIAL|SIGNIFICANT|SEVERE|HIGH|CRITICAL)"
MONTH_RE = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"

AREA_TOKENS = {
    "arabian_gulf": [r"arabian gulf", r"\bAG\b", r"persian gulf"],
    "hormuz": [r"strait of hormuz", r"\bSoH\b", r"\bhormuz\b"],
    "gulf_of_oman": [r"gulf of oman", r"\bGoO\b"],
    "arabian_sea": [r"arabian sea"],
    "gulf_of_aden": [r"gulf of aden", r"\bGoA\b"],
    "bab_al_mandab": [r"bab[- ]?(?:al|el)[- ]?mand[ae]b", r"\bBAM\b"],
    "red_sea": [r"southern red sea", r"central red sea", r"\bred sea\b", r"\bRS\b"],
    "northern_red_sea": [r"northe?r?n red sea", r"suez"],
    "somali_basin": [r"somali", r"indian ocean", r"horn of africa"],
    "eastern_med": [r"eastern mediterranean", r"\bmed\b", r"levant"],
}

GULF_PLACES = [
    (re.compile(r"\b(iraq|basrah|basra|umm qasr|khor al zubair)\b", re.I), "IQ"),
    (re.compile(r"\b(kuwait|shuaiba|shuwaikh|mina al[- ]ahmadi)\b", re.I), "KW"),
    (re.compile(r"\b(saudi|jubail|jubayl|ras tanura|yanbu|jeddah|samref|dammam|khafji|ksa)\b", re.I), "SA"),
    (re.compile(r"\b(bahrain|bapco|sitra|khalifa bin salman|manama)\b", re.I), "BH"),
    (re.compile(r"\b(qatar|ras laffan|mesaieed|doha|hamad port)\b", re.I), "QA"),
    (re.compile(r"\b(uae|united arab emirates|jebel ali|fujairah|khor fakkan|abu dhabi|dubai|ruwais|das island|ras al khaimah|sharjah)\b", re.I), "AE"),
    (re.compile(r"\b(oman|salalah|duqm|sohar|muscat|omani|musandam)\b", re.I), "OM"),
    (re.compile(r"\b(iran|bandar abbas|kharg|qeshm|larak|iranian|sirik|jask)\b", re.I), "IR"),
    (re.compile(r"\b(yemen|hodeidah|hudaydah|\baden\b|mokha|ras isa|mukalla)\b", re.I), "YE"),
    (re.compile(r"\b(israel|eilat|haifa|ashdod)\b", re.I), "IL"),
    (re.compile(r"\b(somali|somalia|\beyl\b|hobyo)\b", re.I), "SO"),
    (re.compile(r"\b(strait of hormuz|soh|hormuz)\b", re.I), "HORMUZ"),
    (re.compile(r"\b(red sea|bab[- ]?(?:al|el)[- ]?mand[ae]b)\b", re.I), "RED_SEA"),
    (re.compile(r"\b(gulf of aden)\b", re.I), "GULF_OF_ADEN"),
]

UPDATE_RE = re.compile(r"Update[_\s]*(\d{3})", re.I)
RANGE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s*(?:–|-|to)\s*(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})")
SINGLE_DATE_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})\b")
US_DATE_RE = re.compile(r"\b([A-Z][a-z]{2,8})\s+(\d{1,2}),\s*(20\d{2})\b")
REGIONAL_LEVEL_RE = re.compile(r"Regional Threat Level\s*:\s*([A-Z][A-Z ]{2,20})")
OVERALL_LEVEL_RE = re.compile(r"Overall Maritime (?:Risk|Threat) Level\s*:[^A-Za-z]*" + LEVEL_RE, re.I)
INDICATOR_RES = {
    "jmic_incidents_since_1mar": re.compile(r"(?:Confirmed maritime attacks/incidents/suspicious activity since 1 March:|Total of)\s*(\d+)\s*(?:incidents since 1 March)?", re.I),
    "jmic_vessel_attacks_48h": re.compile(r"Vessel attacks past 48 hours:\s*(\d+)", re.I),
    "jmic_soh_observed_traffic_24h": re.compile(r"Current observed SoH vessel traffic last 24 hours:\s*(\d+)", re.I),
    "jmic_bam_transits_72h": re.compile(r"(\d+)\s+vessel transits in past 72 hours", re.I),
}
TRAFFIC_BULLET_RE = re.compile(r"[o•]\s*(\d{1,2})\s+([A-Za-z]{3,9})(?:\s+20\d{2})?:\s*(\d+)\s+transits", re.I)
INCIDENT_ID_RE = re.compile(r"^(\d{3}-\d{2})\s+(.+)$")
UKMTO_REF_RE = re.compile(r"UKMTO\s*(?:WARNING|ADVISORY)?\s*(\d{3})\s*-\s*(\d{2})", re.I)
SECTION_RE = re.compile(r"^\s*(\d{1,2}[A-Z]?)\.\s+([A-Z][^\n]{3,90})$", re.M)
POS_RE = re.compile(r"(\d{1,2})[°\s](\d{1,2}(?:\.\d+)?)['’]?\s*([NS])[,\s]+(\d{1,3})[°\s](\d{1,2}(?:\.\d+)?)['’]?\s*([EW])")
HELD_RE = re.compile(r"held since\s+(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})", re.I)
TRANSIT_TITLE_RE = re.compile(r"(CARGO VESSELS?|TANKERS? \(ALL TYPES\) VESSELS?|TANKERS?)\s+TRANSITS COMPARISON(?:\s+(\d{1,2})\s*(?:([A-Za-z]+)\s*)?(?:to|–|-)\s*(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2}))?", re.I)
DATE_HEADER_RE = re.compile(r"^Date((?:\s+\d{1,2}[.\-]?\s*[A-Za-z]{3,9})+)\s*$", re.M)
ROW_RE = re.compile(r"^(SoH E|SoH W|SoH Total|BAM NW|BAM SE|BAM Total|East transit|West transit)\s+((?:\d+\s*)+)$", re.M)
DATED_EVENT_RE = re.compile(
    r"(?:\(|\b)(?:(?:mon|tues|wednes|thurs|fri|satur|sun)day\s+)?"
    r"(?:(\d{1,2})\s+([A-Z][a-z]{2,8})|([A-Z][a-z]{2,8})\s+(\d{1,2})(?:,\s*(20\d{2}))?)\)?",
)
OPS_DATE_RE = re.compile(r"^(?:[•o\-]\s*)?(?:On\s+)?(\d{1,2})\s+([A-Z][a-z]{2,8})(?:\s+(20\d{2}))?\b", re.I)
THREAT_PROSE_RE = re.compile(r"(piracy|harassment|blockade|gnss|emi)\s+threat level\s+(?:remains?|is|has been (?:raised|lowered|increased|decreased) to|assessed(?: as)?)\s+(?:at\s+)?(?:a\s+)?" + LEVEL_RE, re.I)
INFRA_LEXICON = [
    (re.compile(r"drone|uav|uas\b", re.I), "drone_strike", 4),
    (re.compile(r"missile|projectile|ballistic", re.I), "missile_strike", 4),
    (re.compile(r"suspended|halted|closure|closed|shut", re.I), "closure", 3),
    (re.compile(r"strike|struck|attack|impact|explosion|fire", re.I), "missile_strike", 4),
]
OPS_LEXICON = [
    (re.compile(r"boarded|seized|hijack|detained|taken by", re.I), "seizure", 4),
    (re.compile(r"mine", re.I), "mine_warning", 4),
    (re.compile(r"attack|projectile|struck|fired|explosion|detonat|impact", re.I), "maritime_attack", 4),
    (re.compile(r"approach|skiff|small craft|harass|hail|suspicious|interrogat", re.I), "maritime_harassment", 2),
]


@dataclass
class ParsedNote:
    update_no: int | None
    note_date: date | None
    regional_level: int | None
    area_levels: dict[str, int] = field(default_factory=dict)
    threats: dict[str, int] = field(default_factory=dict)
    indicators: dict[str, float] = field(default_factory=dict)
    dated_indicators: dict[str, list[tuple[date, float]]] = field(default_factory=dict)
    transits: dict[str, list[tuple[date, float]]] = field(default_factory=dict)
    incidents: list[dict] = field(default_factory=list)
    ops_events: list[dict] = field(default_factory=list)
    infrastructure: list[dict] = field(default_factory=list)
    mine_warnings: list[dict] = field(default_factory=list)
    vessels_held: int | None = None
    ceasefire: bool = False


def _month(name: str) -> int | None:
    return MONTHS.get(name.lower()[:3])


def _mkdate(y: int, mon: str, d: str | int) -> date | None:
    m = _month(mon)
    if not m:
        return None
    try:
        return date(y, m, int(d))
    except ValueError:
        return None


def _dms(deg: str, minutes: str, hemi: str) -> float:
    v = float(deg) + float(minutes) / 60
    return -v if hemi.upper() in ("S", "W") else v


def _dominant_year(text: str) -> int | None:
    years = Counter(re.findall(r"\b(20[23]\d)\b", text))
    return int(years.most_common(1)[0][0]) if years else None


def _date_from_filename(name: str | None, fallback_year: int | None) -> date | None:
    if not name:
        return None
    m = re.search(r"(\d{1,2})[_\- ]?([A-Za-z]{3,9})[_\- ]?(20\d{2})", name)
    if m:
        return _mkdate(int(m.group(3)), m.group(2), m.group(1))
    m = re.search(r"(\d{1,2})[_\- ]([A-Za-z]{3,9})\b", name)
    if m and fallback_year and _month(m.group(2)):
        return _mkdate(fallback_year, m.group(2), m.group(1))
    return None


def note_date_of(text: str, filename: str | None = None) -> date | None:
    head = text[:1200]
    m = RANGE_RE.search(head)
    if m:
        d = _mkdate(int(m.group(5)), m.group(4), m.group(3))
        if d:
            return d
    m = re.search(r"as of (?:this report dated )?(?:[A-Za-z]+,\s*)?(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})", text[:6000], re.I)
    if m:
        d = _mkdate(int(m.group(3)), m.group(2), m.group(1))
        if d:
            return d
    m = re.search(r"as of (?:[A-Za-z]+,\s*)?([A-Z][a-z]{2,8})\s+(\d{1,2}),\s*(20\d{2})", text[:6000], re.I)
    if m:
        d = _mkdate(int(m.group(3)), m.group(1), m.group(2))
        if d:
            return d
    for m in SINGLE_DATE_RE.finditer(head):
        d = _mkdate(int(m.group(3)), m.group(2), m.group(1))
        if d:
            return d
    m = US_DATE_RE.search(head)
    if m:
        d = _mkdate(int(m.group(3)), m.group(1), m.group(2))
        if d:
            return d
    return _date_from_filename(filename, _dominant_year(text))


def _sections(text: str) -> dict[str, str]:
    """Map numbered section headings ("3. Confirmed Vessel Incidents") to their body text."""
    marks = [(m.start(), m.end(), m.group(2).strip()) for m in SECTION_RE.finditer(text)]
    out: dict[str, str] = {}
    for i, (s, e, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out[title.lower()] = text[e:end]
    return out


def _section(sections: dict[str, str], *needles: str) -> str:
    for title, body in sections.items():
        if all(n in title for n in needles):
            return body
    return ""


def _areas_in(text: str) -> list[str]:
    return [area for area, pats in AREA_TOKENS.items() if any(re.search(p, text, re.I) for p in pats)]


def _area_levels_from_tables(tables: list) -> dict[str, int]:
    levels: dict[str, int] = {}
    for tb in tables:
        if not tb or not tb[0]:
            continue
        header = [(c or "").replace("\n", " ").strip().lower() for c in tb[0]]
        if "region" not in header or not any("threat level" in h for h in header):
            continue
        lvl_col = next(i for i, h in enumerate(header) if "threat level" in h)
        blocks: list[tuple[str, int]] = []
        region_text = ""
        current: int | None = None
        for row in tb[1:]:
            cells = [(c or "").replace("\n", " ").strip() for c in row]
            if len(cells) <= lvl_col:
                continue
            lv = cells[lvl_col].upper().strip()
            region_part = " ".join(c for c in cells[:lvl_col] if c)
            if lv in LEVELS:
                if current is not None:
                    blocks.append((region_text, current))
                region_text, current = region_part, LEVELS[lv]
            else:
                region_text += " " + region_part
        if current is not None:
            blocks.append((region_text, current))
        for rt, lv in blocks:
            for area in _areas_in(rt):
                levels[area] = lv
    return levels


def _area_levels_from_text(text: str) -> dict[str, int]:
    levels: dict[str, int] = {}
    table_area = re.compile(r"^(Arabian Gulf|Strait of Hormuz|Gulf of Oman|Arabian Sea|Gulf of Aden|Bab el-Mandeb(?: /)?|Southern Red Sea|Somali Coast(?: /)?|Somali Basin|Northern Red Sea(?: /)?|Suez Canal|Eastern Mediterranean|Mediterranean)\s+" + LEVEL_RE + r"\b", re.M | re.I)
    for m in table_area.finditer(text):
        for area in _areas_in(m.group(1)):
            levels[area] = LEVELS[m.group(2).upper()]
    flat = " ".join(text.split())
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", flat)
    prose = re.compile(r"(?:remains?|are|is|stays?|remain assessed|assessed)\s+(?:at\s+)?(?:a\s+|an\s+)?" + LEVEL_RE + r"\s+(?:threat|risk)\s+level", re.I)
    prose2 = re.compile(r"threat environment (?:across|in) (.+?) remains\s+(?:at\s+)?" + LEVEL_RE, re.I)
    for s in sentences:
        low = s.lower()
        if "overall maritime" in low or "threat scale" in low or "piracy threat level" in low:
            continue
        m = prose.search(s)
        if m:
            lvl, subject = LEVELS[m.group(1).upper()], s[: m.start()][-220:]
        else:
            m = prose2.search(s)
            if not m:
                continue
            lvl, subject = LEVELS[m.group(2).upper()], m.group(1)
        for area in _areas_in(subject):
            levels.setdefault(area, lvl)
    return levels


def _threats(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in THREAT_PROSE_RE.finditer(" ".join(text.split())):
        key = m.group(1).lower()
        key = {"gnss": "gnss_interference", "emi": "gnss_interference", "harassment": "soh_harassment", "blockade": "soh_blockade"}.get(key, key)
        out[key] = LEVELS[m.group(2).upper()]
    return out


def _transits(text: str, year: int) -> dict[str, list[tuple[date, float]]]:
    out: dict[str, list[tuple[date, float]]] = {}
    titles = list(TRANSIT_TITLE_RE.finditer(text))
    headers = list(DATE_HEADER_RE.finditer(text))
    for i, hm in enumerate(headers):
        prior = [t for t in titles if t.start() < hm.start()]
        kind = "tanker" if prior and prior[-1].group(1).upper().startswith("TANKER") else "cargo"
        yr = int(prior[-1].group(6)) if prior and prior[-1].group(6) else year
        cells = re.findall(r"(\d{1,2})[.\-]?\s*([A-Za-z]{3,9})", hm.group(1))
        dates = [_mkdate(yr, mon, d) for d, mon in cells]
        if prior and len(dates) >= 2 and dates[0] and dates[-1] and dates[-1] < dates[0]:
            dates = [(_mkdate(yr - 1, mon, d) if _month(mon) == 12 else _mkdate(yr, mon, d)) for d, mon in cells]
        block_end = headers[i + 1].start() if i + 1 < len(headers) else min(len(text), hm.end() + 1500)
        block = text[hm.end():block_end]
        rows = {m.group(1): [float(x) for x in m.group(2).split()] for m in ROW_RE.finditer(block)}
        if "East transit" in rows and "West transit" in rows:
            rows = {"SoH Total": [a + b for a, b in zip(rows["East transit"], rows["West transit"])]}
        for label, series in (("SoH Total", f"jmic_soh_{kind}_transits"), ("BAM Total", f"jmic_bam_{kind}_transits")):
            vals = rows.get(label)
            if not vals:
                continue
            for d, v in zip(dates, vals):
                if d is not None:
                    out.setdefault(series, []).append((d, v))
    return out


def _country(text: str) -> str | None:
    for rx, code in GULF_PLACES:
        if rx.search(text):
            return code
    return None


def _incidents_from_tables(tables: list, year: int) -> list[dict]:
    items: list[dict] = []
    idx: dict[str, int] | None = None
    ncols = 0
    for tb in tables:
        if not tb or not tb[0]:
            continue
        header = [(c or "").replace("\n", " ").strip().lower() for c in tb[0]]
        rows = tb[1:]
        if "date" in header and any("summary" in h or "event" in h for h in header):
            idx = {h: i for i, h in enumerate(header)}
            ncols = len(header)
        elif idx is not None and len(header) == ncols and re.match(r"\d{1,2}\s+[A-Za-z]{3}", header[0] or ""):
            rows = tb  # continuation page of the cumulative annex: no header row
        elif header and header[0] == "incident" and "location" in header:
            for row in rows:
                cells = [(c or "").replace("\n", " ").strip() for c in row]
                if not cells or not re.match(r"\d{3}-\d{2}", cells[0]):
                    continue
                items.append({"ref": cells[0], "vessel": cells[1].split("/")[0].strip() if len(cells) > 1 else "", "date": None, "vessel_type": cells[1].split("/")[1].strip() if len(cells) > 1 and "/" in cells[1] else "", "kind": "Attack", "location": cells[-1], "summary": " ".join(cells[2:-1]), "country": _country(cells[-1])})
            continue
        else:
            continue
        for row in rows:
            cells = [(c or "").replace("\n", " ").strip() for c in row]
            if not any(cells):
                continue
            raw_date = cells[idx["date"]] if "date" in idx and idx["date"] < len(cells) else ""
            dm = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})", raw_date)
            d = _mkdate(int(dm.group(3)), dm.group(2), dm.group(1)) if dm else None
            rm = UKMTO_REF_RE.search(raw_date)
            ref = f"{rm.group(1)}-{rm.group(2)}" if rm else None

            def col(name: str) -> str:
                i = idx.get(name)
                return cells[i] if i is not None and i < len(cells) else ""

            summ = col("summary") or " ".join(cells)
            loc = col("location")
            items.append({"ref": ref, "vessel": col("vessel"), "date": d, "vessel_type": col("vessel type"), "kind": col("event type") or "Attack", "location": loc, "summary": summ, "country": _country(loc + " " + summ)})
    return items


def _incidents_from_text(body: str) -> list[dict]:
    """March 2026 daily table as text: 'NNN-26 VESSEL / Type / Status  Damage  Location' wrapped over lines."""
    items: list[dict] = []
    cur: dict | None = None
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        m = INCIDENT_ID_RE.match(line)
        if m:
            cur = {"ref": m.group(1), "vessel": "", "date": None, "vessel_type": "", "kind": "Attack", "location": "", "summary": m.group(2), "country": None}
            items.append(cur)
            continue
        if cur is None:
            continue
        if len(line) > 95 or re.match(r"^(On |Among |All |Caution|Incident reporting|No |NTR|None)", line):
            cur = None
            continue
        cur["summary"] += " " + line
    place_rx = re.compile(r"(Arabian Gulf|Gulf of Oman|Strait of Hormuz|Iraq TTW|Red Sea|Gulf of Aden)")
    for it in items:
        s = it["summary"]
        parts = [p.strip() for p in s.split("/")]
        it["vessel"] = parts[0].strip()
        if len(parts) >= 2:
            it["vessel_type"] = parts[1].split()[0] if parts[1] else ""
        loc = re.search(r"(\d{1,3}\s*nm\s+[A-Za-z ]+?of\s+[A-Z][A-Za-z ]+(?:,\s*[A-Z][A-Za-z ]+)?)", s)
        pm = place_rx.search(s)
        it["location"] = loc.group(1) if loc else (pm.group(1) if pm else "")
        it["country"] = _country(it["location"]) or _country(s)
        if re.search(r"boarded|seized|hijack|detained", s, re.I):
            it["kind"] = "Seizure"
        elif re.search(r"no\s*-\s*close proximity|near miss|splash", s, re.I):
            it["kind"] = "Near miss"
    return items


def _ops_events(body: str, year: int) -> list[dict]:
    """Dated incident lines in the operational summary (bullets and 'On 03 May 2026, UKMTO received...')."""
    items: list[dict] = []
    flat = re.sub(r"\n(?![•o\-]\s)", " ", body)
    for line in flat.split("\n"):
        for s in re.split(r"(?<=[.!?])\s+(?=(?:On|At|In)\s+\d{1,2}\s+[A-Z])", line.strip()):
            m = OPS_DATE_RE.match(s)
            if not m:
                continue
            d = _mkdate(int(m.group(3)) if m.group(3) else year, m.group(2), m.group(1))
            if d is None:
                continue
            s = " ".join(re.split(r"(?<=[.!?])\s+", s)[:2])  # the dated sentence and one of context
            etype = None
            sev = 2
            for rx, t, sv in OPS_LEXICON:
                if rx.search(s):
                    etype, sev = t, sv
                    break
            if etype is None or etype == "mine_warning":
                continue
            if re.search(r"\bno (?:new|confirmed|verified|further)\b", s[:80], re.I):
                continue
            rm = UKMTO_REF_RE.search(s)
            desc = re.sub(r"^[•o\-]\s*", "", s).strip()
            items.append({"date": d, "event_type": etype, "severity": sev, "ref": f"{rm.group(1)}-{rm.group(2)}" if rm else None, "country": _country(desc), "summary": " ".join(desc.split())[:500]})
    return items


def _infrastructure(body: str, year: int, note_date: date | None) -> list[dict]:
    items: list[dict] = []
    flat = " ".join(body.split())
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", flat):
        if not re.search(r"strike|struck|attack|impact|explosion|fire|suspended|halted|damage", s, re.I):
            continue
        if re.search(r"^no\b|no confirmed|not been|have not|no reported|no new|none|no attacks", s, re.I):
            continue
        d: date | None = None
        for m in DATED_EVENT_RE.finditer(s):
            if m.group(1) and m.group(2) and _month(m.group(2)):
                d = _mkdate(year, m.group(2), m.group(1))
            elif m.group(3) and m.group(4) and _month(m.group(3)):
                d = _mkdate(int(m.group(5)) if m.group(5) else year, m.group(3), m.group(4))
            if d:
                break
        country = _country(s)
        if not country or country in ("HORMUZ", "RED_SEA", "GULF_OF_ADEN"):
            continue
        if d is None and note_date is None:
            continue
        etype, sev = "missile_strike", 4
        for rx, t, sv in INFRA_LEXICON:
            if rx.search(s):
                etype, sev = t, sv
                break
        items.append({"date": d or (note_date - timedelta(days=1)), "country": country, "event_type": etype, "severity": sev, "summary": s[:500], "dated": d is not None})
    return items


def _mines(text: str, year: int) -> list[dict]:
    items: list[dict] = []
    flat = " ".join(text.split())
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", flat):
        if not re.search(r"\bmine", s, re.I) or not re.search(r"NAVAREA|navigational warning|navtex", s, re.I):
            continue
        if re.search(r"no confirmation|unconfirmed|no verified|not been confirmed", s, re.I):
            continue
        d = None
        dm = re.search(r"\b(\d{1,2})\s+([A-Z][a-z]{2,8})\b", s)
        if dm:
            d = _mkdate(year, dm.group(2), dm.group(1))
        lat = lon = None
        p = POS_RE.search(s)
        if p:
            lat, lon = _dms(p.group(1), p.group(2), p.group(3)), _dms(p.group(4), p.group(5), p.group(6))
        ref = re.search(r"\(([\d/]+)\)", s)
        items.append({"date": d, "lat": lat, "lon": lon, "ref": ref.group(1) if ref else None, "summary": s[:400]})
    return items


def parse_note(text: str, tables: list | None = None, filename: str | None = None) -> ParsedNote:
    tables = tables or []
    um = UPDATE_RE.search(text[:600]) or UPDATE_RE.search(filename or "")
    update_no = int(um.group(1)) if um else None
    nd = note_date_of(text, filename)
    year = nd.year if nd else (_dominant_year(text) or date.today().year)
    regional: int | None = None
    rl = REGIONAL_LEVEL_RE.search(text[:1500])
    if rl:
        key = re.sub(r"\s+", "", rl.group(1)).upper()  # "SIG NIFICANT" in the 2025 notes
        regional = next((v for k, v in LEVELS.items() if key.startswith(k)), None)
    if regional is None:
        m = OVERALL_LEVEL_RE.search(text[:2500])
        regional = LEVELS[m.group(1).upper()] if m else None
    if regional is None:
        m = re.search(r"threat (?:environment|level)[^.]{0,120}(?:remains|is assessed as)\s+(?:at\s+)?" + LEVEL_RE, text[:4000], re.I)
        regional = LEVELS[m.group(1).upper()] if m else None
    sections = _sections(text)
    p = ParsedNote(update_no=update_no, note_date=nd, regional_level=regional)
    p.area_levels = _area_levels_from_tables(tables) or _area_levels_from_text(text)
    p.threats = _threats(text)
    for key, rx in INDICATOR_RES.items():
        m = rx.search(text)
        if m:
            p.indicators[key] = float(m.group(1))
    for m in TRAFFIC_BULLET_RE.finditer(text):
        d = _mkdate(year, m.group(2), m.group(1))
        if d:
            p.dated_indicators.setdefault("jmic_soh_observed_traffic_24h", []).append((d, float(m.group(3))))
    p.transits = _transits(text, year)
    incidents = _incidents_from_tables(tables, year)
    inc_body = _section(sections, "confirmed", "incident") or _section(sections, "vessel incidents")
    if inc_body:
        text_items = _incidents_from_text(inc_body)
        known = {it["ref"] for it in incidents if it.get("ref")}
        incidents.extend(it for it in text_items if it["ref"] not in known)
    for it in incidents:
        if it["date"] is None and nd:
            it["date"] = nd - timedelta(days=1)
    p.incidents = [it for it in incidents if it["date"] is not None]
    ops_body = _section(sections, "operational summary")
    p.ops_events = _ops_events(ops_body, year) if ops_body else []
    infra_body = _section(sections, "infrastructure")
    p.infrastructure = _infrastructure(infra_body, year, nd) if infra_body else []
    p.mine_warnings = _mines(text, year)
    held = HELD_RE.findall(text)
    p.vessels_held = len(held) if held else (0 if re.search(r"no (?:merchant )?vessels? (?:remain|are) held", text, re.I) else None)
    p.ceasefire = bool(re.search(r"ceasefire|cease fire", text, re.I))
    return p


def _put(db: Session, series: str, d: date, value: float, unit: str, src: str) -> None:
    existing = db.scalar(select(SeriesPoint).where(SeriesPoint.series == series, SeriesPoint.date == d))
    if existing:
        existing.value, existing.is_synthetic, existing.source = value, False, src
    else:
        db.add(SeriesPoint(series=series, date=d, value=value, unit=unit, source=src, is_synthetic=False))


def _event_exists(db: Session, etype: str, desc: str, ref: str | None, vessel: str | None = None) -> bool:
    if ref:
        q = select(ThreatEvent).where(ThreatEvent.event_type == etype, ThreatEvent.provenance["incident_no"].as_string() == ref)
        for ev in db.scalars(q):
            if not vessel or (ev.provenance or {}).get("vessel", "") == vessel:
                return True
    return db.scalar(select(ThreatEvent).where(ThreatEvent.event_type == etype, ThreatEvent.description_en == desc)) is not None


def ingest(db: Session, parsed: ParsedNote, *, external_id: str, text: str, url: str | None = None) -> dict:
    doc, created = upsert_document(db, RawDoc(SOURCE, external_id, text, url=url))
    d = parsed.note_date
    counts = {"series": 0, "events": 0, "created": created}
    if d is None:
        doc.status = "extracted"
        db.commit()
        return counts
    src = f"JMIC advisory note update {parsed.update_no:03d}" if parsed.update_no is not None else f"JMIC advisory note {external_id}"
    points: dict[tuple[str, date], tuple[float, str, str]] = {}
    if parsed.regional_level is not None:
        points[("jmic_regional_threat_level", d)] = (parsed.regional_level, "level_1_to_5", src)
    for area, lvl in parsed.area_levels.items():
        points[(f"jmic_threat_level_{area}", d)] = (lvl, "level_1_to_5", src)
    for threat, lvl in parsed.threats.items():
        points[(f"jmic_threat_{threat}", d)] = (lvl, "level_1_to_5", src)
    for key, val in parsed.indicators.items():
        points[(key, d)] = (val, "count", src)
    for key, pts in parsed.dated_indicators.items():
        for pd, v in pts:
            points[(key, pd)] = (v, "count", src)
    for series, pts in parsed.transits.items():
        for pd, v in pts:
            points[(series, pd)] = (v, "vessels_per_day", src + " (S&P AIS)")
    if parsed.vessels_held is not None:
        points[("jmic_vessels_held_somalia", d)] = (parsed.vessels_held, "count", src)
    for (series, pd), (v, unit, s) in points.items():
        _put(db, series, pd, v, unit, s)
        db.flush()
        counts["series"] += 1
    prov = {"source": src, "url": url or "", "grade": "A2"}
    for it in parsed.incidents:
        kind = it["kind"].lower()
        etype = "seizure" if kind.startswith("seiz") or "board" in kind or "hijack" in kind else "maritime_harassment" if re.search(r"near miss|suspicious|approach|harass", kind) else "maritime_attack"
        desc = (f"{it['kind']} on a {it['vessel_type'].lower()} " if it["vessel_type"] else f"{it['kind']} ") + (f"in {it['location']}. " if it["location"] else "") + it["summary"]
        desc = " ".join(desc.split())[:600]
        if _event_exists(db, etype, desc, it.get("ref"), it.get("vessel")):
            continue
        pv = dict(prov)
        if it.get("ref"):
            pv["incident_no"] = it["ref"]
        if it.get("vessel"):
            pv["vessel"] = it["vessel"]
        db.add(ThreatEvent(event_date=it["date"], event_type=etype, location_name=it["location"] or None, country=it["country"], severity=4 if etype != "maritime_harassment" else 2, description_en=desc, source_doc_id=doc.id, provenance=pv, verification="pending"))
        counts["events"] += 1
    for it in parsed.ops_events:
        if _event_exists(db, it["event_type"], it["summary"], it.get("ref")):
            continue
        pv = dict(prov)
        if it.get("ref"):
            pv["incident_no"] = it["ref"]
        db.add(ThreatEvent(event_date=it["date"], event_type=it["event_type"], location_name=None, country=it["country"], severity=it["severity"], description_en=it["summary"], source_doc_id=doc.id, provenance=pv, verification="pending"))
        counts["events"] += 1
    for it in parsed.infrastructure:
        if _event_exists(db, it["event_type"], it["summary"], None):
            continue
        pv = dict(prov, grade="B2" if not it["dated"] else "A2")
        db.add(ThreatEvent(event_date=it["date"], event_type=it["event_type"], location_name=None, country=it["country"], severity=it["severity"], description_en=it["summary"], source_doc_id=doc.id, provenance=pv, verification="pending"))
        counts["events"] += 1
    for it in parsed.mine_warnings:
        if _event_exists(db, "mine_warning", it["summary"], None):
            continue
        pv = dict(prov)
        if it["ref"]:
            pv["navarea_ref"] = it["ref"]
        db.add(ThreatEvent(event_date=it["date"] or d, event_type="mine_warning", location_name="Strait of Hormuz", country="HORMUZ", lat=it["lat"], lon=it["lon"], severity=4, description_en=it["summary"], source_doc_id=doc.id, provenance=pv, verification="pending"))
        counts["events"] += 1
    doc.status = "extracted"
    db.commit()
    return counts


def read_pdf(data: bytes) -> tuple[str, list]:
    import io

    import pdfplumber

    tables: list = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        for p in pdf.pages:
            try:
                tables.extend(p.extract_tables() or [])
            except Exception:  # noqa: BLE001
                continue
    return text, tables


def ingest_pdf(db: Session, data: bytes, *, external_id: str, url: str | None = None) -> dict:
    text, tables = read_pdf(data)
    parsed = parse_note(text, tables, filename=external_id)
    return ingest(db, parsed, external_id=external_id, text=text, url=url)


def fetch_and_ingest(db: Session, url: str) -> dict:
    return ingest_pdf(db, fetch_bytes(url), external_id=url.rsplit("/", 1)[-1], url=url)
