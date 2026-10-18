"""Brief generator: a template that is always available, and an optional model pass that
polishes prose without adding a fact (the template output is passed in as the only source
of facts, and the model is instructed to keep every number and date)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..engine import run as engine_run
from ..models import Brief, Forecast, Indicator, Question, ThreatEvent
from . import yardstick

STR = {
    "en": {
        "title": "Assessment",
        "as_of": "As of",
        "judgement": "Judgement",
        "prob": "Probability",
        "confidence": "Analytical confidence",
        "movement": "Movement over 30 days",
        "moved": "What moved it",
        "watch": "What would move it next",
        "decisions": "Decisions this informs",
        "resolution": "Resolution criteria",
        "panel": "Panel",
        "sources": "Evidence",
        "no_panel": "No panel round in the last three weeks.",
        "points": "points",
        "synthetic": "This brief draws on demo data for some indicators; treat the number as an illustration until live feeds replace the flagged rows.",
        "present": "present",
        "absent": "absent",
        "unknown": "unknown",
        "base_rate": "Status-quo base rate",
    },
    "ar": {
        "title": "تقدير",
        "as_of": "حتى تاريخ",
        "judgement": "الحكم",
        "prob": "الاحتمال",
        "confidence": "الثقة التحليلية",
        "movement": "التغير خلال 30 يوماً",
        "moved": "ما الذي حرّك التقدير",
        "watch": "ما الذي قد يحرّكه لاحقاً",
        "decisions": "القرارات التي يخدمها هذا التقدير",
        "resolution": "معايير الحسم",
        "panel": "لجنة المتنبئين",
        "sources": "الأدلة",
        "no_panel": "لا توجد جولة للجنة خلال الأسابيع الثلاثة الأخيرة.",
        "points": "نقطة",
        "synthetic": "يعتمد هذا الموجز على بيانات توضيحية في بعض المؤشرات؛ يُعدّ الرقم إيضاحياً إلى أن تحل البيانات الحية محل الصفوف المعلّمة.",
        "present": "قائم",
        "absent": "غير قائم",
        "unknown": "غير معروف",
        "base_rate": "المعدل الأساسي للوضع الراهن",
    },
}


def _pct(p: float) -> str:
    return f"{round(p * 100):d}%"


def _evidence_lines(db: Session, contribution: dict, lang: str) -> list[str]:
    ev = contribution.get("evidence") or {}
    lines: list[str] = []
    ids = ev.get("event_ids") or []
    if ids:
        for e in db.scalars(select(ThreatEvent).where(ThreatEvent.id.in_(ids[:4]))).all():
            text = e.description_ar if (lang == "ar" and e.description_ar) else e.description_en
            flag = " (demo)" if e.is_synthetic else ""
            src = e.provenance.get("source", "") if e.provenance else ""
            lines.append(f"{e.event_date.isoformat()}: {text}{flag} [{src}]")
    if "series" in ev and "value" in ev:
        lines.append(f"{ev['series']} = {ev['value']} {ev.get('unit', '')} ({ev.get('date', '')}){' (demo)' if ev.get('is_synthetic') else ''}")
    if "recent_mean" in ev:
        lines.append(f"{ev['series']}: {ev['recent_mean']} vs baseline {ev['baseline_mean']} (ratio {ev['ratio']})")
    if "score" in ev and "actor" in ev:
        lines.append(f"{ev['actor']} / {ev['issue']} ({ev.get('track', '')}): position {ev['score']} from {ev['n']} observations")
    if "divergence" in ev:
        lines.append(f"{ev['actor']} / {ev['issue']}: stated {ev['stated'].get('score')} vs revealed {ev['revealed'].get('score')}, divergence {ev['divergence']}")
    if "ratio" in ev and "recent_count" in ev:
        lines.append(f"{ev['actor']} / {ev['issue']}: {ev['recent_count']} statements in window against {ev['expected_in_window']} expected")
    return lines


def render_template(db: Session, question: Question, as_of: date, lang: str = "en") -> str:
    s = STR["ar" if lang == "ar" else "en"]
    fc = db.scalar(select(Forecast).where(Forecast.question_id == question.id, Forecast.as_of <= as_of).order_by(Forecast.as_of.desc()).limit(1))
    if fc is None:
        fc = engine_run.commit(db, question, as_of)
    dec = fc.decomposition or {}
    machine = dec.get("machine", {})
    contributions = machine.get("contributions", [])
    panel = dec.get("panel")
    hist = engine_run.history(db, question.id, 30, as_of)
    first = hist[0]["final_prob"] if hist else fc.final_prob
    delta = (fc.final_prob - first) * 100
    inds = {i.code: i for i in question.indicators}
    present = sorted([c for c in contributions if c["state"] == "present"], key=lambda c: abs(c["log_lr"]), reverse=True)
    absent = [c for c in contributions if c["state"] in ("absent", "unknown")]
    synth_share = 0.0
    n_ev = 0
    for c in contributions:
        ev = c.get("evidence") or {}
        if "synthetic_share" in ev:
            synth_share = max(synth_share, float(ev["synthetic_share"]))
        if ev.get("is_synthetic"):
            synth_share = max(synth_share, 1.0)
        n_ev += len(ev.get("event_ids") or []) + (1 if ev.get("score") is not None else 0) + (1 if ev.get("value") is not None else 0)
    conf = yardstick.confidence_words(n_ev, synth_share, lang)
    title = question.title_ar if (lang == "ar" and question.title_ar) else question.title_en

    def name(code: str) -> str:
        ind: Indicator | None = inds.get(code)
        if ind is None:
            return code
        return ind.name_ar if (lang == "ar" and ind.name_ar) else ind.name_en

    out = [f"# {s['title']}: {title}", "", f"{s['as_of']}: {as_of.isoformat()}", ""]
    out.append(f"## {s['judgement']}")
    out.append(f"{s['prob']}: {_pct(fc.final_prob)} ({yardstick.band(fc.final_prob, lang)}). {s['confidence']}: {conf}. {s['movement']}: {delta:+.0f} {s['points']}. {s['base_rate']}: {_pct(question.base_rate)}.")
    out.append("")
    out.append(f"## {s['moved']}")
    if present:
        for c in present[:4]:
            out.append(f"- {name(c['indicator'])} ({s['present']}, log LR {c['log_lr']:+.2f})")
            for line in _evidence_lines(db, c, lang):
                out.append(f"    - {line}")
    else:
        out.append("- " + ("لا مؤشر قائم؛ التقدير عند المعدل الأساسي." if lang == "ar" else "No indicator present; the estimate sits at the base rate."))
    out.append("")
    out.append(f"## {s['watch']}")
    for c in absent[:5]:
        ind = inds.get(c["indicator"])
        direction = "+" if ind and ind.lr_present > 1 else "-"
        out.append(f"- {name(c['indicator'])} ({s[c['state']]}; {direction})")
    out.append("")
    out.append(f"## {s['panel']}")
    if panel:
        out.append(f"{_pct(panel['probability'])} ({panel['n']}; {_pct(panel['low'])} to {_pct(panel['high'])}, {'median' if lang == 'en' else 'الوسيط'} {_pct(panel['median'])})")
    else:
        out.append(s["no_panel"])
    out.append("")
    out.append(f"## {s['decisions']}")
    for h in question.decision_hooks or []:
        out.append(f"- {h}")
    out.append("")
    out.append(f"## {s['resolution']}")
    out.append(question.resolution_criteria)
    if synth_share > 0:
        out.append("")
        out.append(f"_{s['synthetic']}_")
    out.append("")
    out.append(f"_commit {fc.commit_hash[:16]}_")
    return "\n".join(out)


def _model_polish(markdown: str, lang: str) -> tuple[str, str] | None:
    settings = get_settings()
    if settings.model_provider == "anthropic" and settings.anthropic_api_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            lang_name = "Arabic" if lang == "ar" else "English"
            msg = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=2000,
                system=(
                    "You polish an intelligence brief for a national security principal. Keep every number, date, "
                    "percentage, hash and source reference exactly as given. Do not add facts, examples or judgements. "
                    f"Write in {lang_name}, plain and measured, no dashes as punctuation, headings kept."
                ),
                messages=[{"role": "user", "content": markdown}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            return text, f"anthropic:{settings.anthropic_model}"
        except Exception:  # pragma: no cover - network dependent
            return None
    return None


def generate(db: Session, question_code: str, as_of: date, lang: str = "en", *, polish: bool = True) -> Brief:
    q = db.scalar(select(Question).where(Question.code == question_code))
    if q is None:
        raise KeyError(question_code)
    md = render_template(db, q, as_of, lang)
    generator = "template"
    if polish:
        polished = _model_polish(md, lang)
        if polished:
            md, generator = polished
    b = Brief(question_id=q.id, lang=lang, content_md=md, generator=generator)
    db.add(b)
    db.commit()
    return b
