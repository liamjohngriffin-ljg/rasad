"""The weekly situation brief: one document across the whole board for the principal's Monday.

Sections: the board (every open question with its probability, yardstick band and seven-day
move), what moved (alerts and indicator changes in the period), reported incidents by area and
type with the most severe listed, position-book change-points, open tasking, and data
freshness. Every number is read from the ledgers at generation time; nothing is composed by
a model. Arabic and English templates; Word export through the same path as question briefs.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..engine import run as engine_run
from ..models import Actor, Alert, Forecast, Issue, Question, SeriesPoint, TaskingRequest, ThreatEvent
from ..policy import book as policy_book
from . import yardstick

STR = {
    "en": {
        "title": "Weekly situation brief", "period": "Period", "board": "The board", "question": "Question", "prob": "Probability", "move": "7-day move",
        "moved": "What moved", "no_moves": "No forecast moved by five points or more this week.", "incidents": "Reported incidents", "by_area": "By area",
        "by_type": "By type", "severe": "Most severe", "positions": "Position book: change-points this fortnight", "no_cp": "No change-points detected.",
        "tasking": "Open tasking", "no_tasking": "No open requests.", "freshness": "Data freshness", "stale": "days since last point", "pending": "pending verification",
        "none": "None in the period.", "flips": "indicator changes", "up": "up", "down": "down", "points": "points", "stated": "stated", "revealed": "revealed",
        "total_events": "reported events in the period", "alerts_open": "alerts open", "note": "Probabilities are the committed values on the chain; counts include connector rows pending analyst verification, marked where so.",
    },
    "ar": {
        "title": "موجز الموقف الأسبوعي", "period": "الفترة", "board": "اللوحة", "question": "السؤال", "prob": "الاحتمال", "move": "التغير خلال 7 أيام",
        "moved": "ما الذي تغيّر", "no_moves": "لم يتحرك أي تقدير بخمس نقاط أو أكثر هذا الأسبوع.", "incidents": "الحوادث المُبلّغ عنها", "by_area": "حسب المنطقة",
        "by_type": "حسب النوع", "severe": "الأشد خطورة", "positions": "سجل المواقف: نقاط التحول خلال أسبوعين", "no_cp": "لم تُرصد نقاط تحول.",
        "tasking": "الطلبات المفتوحة", "no_tasking": "لا طلبات مفتوحة.", "freshness": "حداثة البيانات", "stale": "يوماً منذ آخر نقطة", "pending": "قيد التحقق",
        "none": "لا شيء في الفترة.", "flips": "تغيرات المؤشرات", "up": "ارتفاع", "down": "انخفاض", "points": "نقطة", "stated": "المعلن", "revealed": "الفعلي",
        "total_events": "حدثاً مُبلّغاً عنه في الفترة", "alerts_open": "تنبيهات مفتوحة", "note": "الاحتمالات هي القيم المعتمدة على السلسلة؛ تشمل الأعداد صفوف الموصلات قيد تحقق المحللين حيث يُشار إلى ذلك.",
    },
}
AREA_NAMES = {"HORMUZ": ("Strait of Hormuz", "مضيق هرمز"), "ARABIAN_GULF": ("Arabian Gulf", "الخليج العربي"), "RED_SEA": ("Red Sea and Bab el-Mandeb", "البحر الأحمر وباب المندب"), "GULF_OF_ADEN": ("Gulf of Aden and Somali Basin", "خليج عدن والحوض الصومالي"), "OM": ("Oman and Gulf of Oman", "عُمان وخليج عُمان"), "AE": ("UAE", "الإمارات"), "SA": ("Saudi Arabia", "السعودية"), "QA": ("Qatar", "قطر"), "KW": ("Kuwait", "الكويت"), "BH": ("Bahrain", "البحرين"), "IQ": ("Iraq", "العراق"), "IR": ("Iran", "إيران"), "YE": ("Yemen", "اليمن"), "IL": ("Israel", "إسرائيل")}
WATCHED = ("hormuz_transits", "bab_el_mandeb_transits", "jmic_regional_threat_level", "war_risk_premium_hormuz_pct", "uk_designated_vessels_iran")


def _pct(p: float | None) -> str:
    return "n/a" if p is None else f"{round(p * 100)}%"


def render(db: Session, as_of: date, lang: str = "en", days: int = 7) -> str:
    s = STR[lang]
    start = as_of - timedelta(days=days)
    out = [f"# {s['title']}", f"_{s['period']}: {start.isoformat()} / {as_of.isoformat()}_", ""]
    # the board
    out += [f"## {s['board']}", ""]
    moves = []
    for q in db.scalars(select(Question).where(Question.status == "open").order_by(Question.order)):
        latest = db.scalar(select(Forecast).where(Forecast.question_id == q.id, Forecast.as_of <= as_of).order_by(Forecast.as_of.desc()).limit(1))
        before = db.scalar(select(Forecast).where(Forecast.question_id == q.id, Forecast.as_of <= start).order_by(Forecast.as_of.desc()).limit(1))
        if latest is None:
            continue
        delta = (latest.final_prob - before.final_prob) * 100 if before else 0.0
        title = q.title_ar if lang == "ar" and q.title_ar else q.title_en
        sign = "+" if delta > 0 else ""
        out.append(f"- {title}: {_pct(latest.final_prob)} ({yardstick.band(latest.final_prob, lang)}), {sign}{delta:.0f} {s['points']}")
        prev_states = {c["indicator"]: c["state"] for c in ((before.decomposition if before else {}) or {}).get("machine", {}).get("contributions", [])}
        flips = [(c["indicator"], prev_states.get(c["indicator"]), c["state"]) for c in (latest.decomposition or {}).get("machine", {}).get("contributions", []) if prev_states.get(c["indicator"]) not in (None, c["state"])]
        if abs(delta) >= 5 or flips:
            moves.append((q, delta, flips, latest))
    out.append("")
    # what moved
    out += [f"## {s['moved']}", ""]
    if not moves:
        out.append(s["no_moves"])
    for q, delta, flips, latest in moves:
        title = q.title_ar if lang == "ar" and q.title_ar else q.title_en
        names = {i.code: (i.name_ar if lang == "ar" and i.name_ar else i.name_en) for i in q.indicators}
        direction = s["up"] if delta > 0 else s["down"]
        line = f"- {title}: {direction} {abs(delta):.0f} {s['points']} to {_pct(latest.final_prob)}" if abs(delta) >= 5 else f"- {title}: {_pct(latest.final_prob)}"
        out.append(line)
        for code, a, b in flips:
            out.append(f"    - {names.get(code, code)}: {a} → {b}")
    open_alerts = db.scalar(select(func.count(Alert.id)).where(Alert.acknowledged_at.is_(None))) or 0
    out += ["", f"_{open_alerts} {s['alerts_open']}_", ""]
    # incidents
    out += [f"## {s['incidents']}", ""]
    evs = db.scalars(select(ThreatEvent).where(ThreatEvent.event_date > start, ThreatEvent.event_date <= as_of, ThreatEvent.verification != "rejected", ThreatEvent.is_synthetic.is_(False), ThreatEvent.event_type.notin_(["designation", "insurer_listing"])).order_by(ThreatEvent.severity.desc(), ThreatEvent.event_date.desc())).all()
    pending = sum(1 for e in evs if e.verification == "pending")
    out.append(f"{len(evs)} {s['total_events']}" + (f" ({pending} {s['pending']})" if pending else ""))
    if evs:
        by_area = Counter(e.country or "?" for e in evs)
        by_type = Counter(e.event_type for e in evs)
        out += ["", s["by_area"] + ":", ""]
        for area, n in by_area.most_common():
            nm = AREA_NAMES.get(area, (area, area))[1 if lang == "ar" else 0]
            out.append(f"- {nm}: {n}")
        out += ["", s["by_type"] + ":", ""]
        for ty, n in by_type.most_common():
            out.append(f"- {ty.replace('_', ' ')}: {n}")
        out += ["", s["severe"] + ":", ""]
        confirmed = [e for e in evs if e.verification == "verified" or str((e.provenance or {}).get("grade", "C"))[:1].upper() in ("A", "B")]
        for e in confirmed[:6]:
            desc = e.description_ar if lang == "ar" and e.description_ar else e.description_en
            src = (e.provenance or {}).get("source", "")
            out.append(f"- {e.event_date.isoformat()} {e.event_type.replace('_', ' ')} {e.country or ''}: {desc[:220]} [{src}]" + (f" ({s['pending']})" if e.verification == "pending" else ""))
    else:
        out.append(s["none"])
    out.append("")
    # position book change-points
    out += [f"## {s['positions']}", ""]
    cps = []
    actors = db.scalars(select(Actor)).all()
    issues = db.scalars(select(Issue)).all()
    for a in actors:
        for i in issues:
            try:
                entry = policy_book.issue_position(db, a.code, i.code, as_of, history_days=60)
            except Exception:  # noqa: BLE001
                continue
            if (entry.get("stated") or {}).get("n", 0) + (entry.get("revealed") or {}).get("n", 0) == 0:
                continue
            for track in ("stated", "revealed"):
                for cp in (entry.get("change_points") or {}).get(track, []):
                    d = date.fromisoformat(cp["date"]) if isinstance(cp.get("date"), str) else cp.get("date")
                    if d and d > as_of - timedelta(days=14):
                        cps.append((d, a, i, track, cp))
    if not cps:
        out.append(s["no_cp"])
    for d, a, i, track, cp in sorted(cps, key=lambda x: x[0], reverse=True)[:12]:
        an = a.name_ar if lang == "ar" and a.name_ar else a.name_en
        iname = i.name_ar if lang == "ar" and i.name_ar else i.name_en
        out.append(f"- {d.isoformat()} {an} / {iname} ({s[track]}): {cp.get('direction')} {cp.get('magnitude')}")
    out.append("")
    # tasking
    out += [f"## {s['tasking']}", ""]
    tasks = db.scalars(select(TaskingRequest).where(TaskingRequest.status != "answered").order_by(TaskingRequest.created_at.desc()).limit(10)).all()
    if not tasks:
        out.append(s["no_tasking"])
    for t in tasks:
        out.append(f"- {t.created_at.date().isoformat()} [{t.status}] {t.text[:160]}")
    out.append("")
    # freshness
    out += [f"## {s['freshness']}", ""]
    for name in WATCHED:
        latest = db.scalar(select(SeriesPoint).where(SeriesPoint.series == name).order_by(SeriesPoint.date.desc()).limit(1))
        if latest is None:
            continue
        out.append(f"- {name}: {latest.value:g} ({latest.date.isoformat()}, {(as_of - latest.date).days} {s['stale']})")
    out += ["", f"_{s['note']}_"]
    return "\n".join(out)


def generate(db: Session, as_of: date, lang: str = "en", days: int = 7):
    from ..models import Brief

    md = render(db, as_of, lang, days)
    b = Brief(question_id=None, lang=lang, content_md=md, generator="template:weekly", generated_at=datetime.utcnow())
    db.add(b)
    db.commit()
    return b
