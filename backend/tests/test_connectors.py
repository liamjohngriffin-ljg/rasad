from __future__ import annotations

import os
from datetime import date

from rasad.extraction import rules
from rasad.pipelines.connectors import jmic, jwc, portwatch, rss_wires, sanctions, state_fms, ukmto
from rasad.pipelines.connectors.base import EgressRefused, check_egress

FIX = os.path.join(os.path.dirname(__file__), "..", "rasad", "pipelines", "fixtures")


def read(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def test_ukmto_parse():
    p = ukmto.parse_advisory(read("ukmto_advisory_sample.txt"))
    assert p.advisory_no == "901-26"
    assert p.event_date == date(2026, 10, 14)
    assert p.event_type == "maritime_attack" and p.area == "RED_SEA"
    assert p.lat and abs(p.lat - 14.205) < 0.01 and p.lon and abs(p.lon - 42.5167) < 0.01


def test_jwc_parse():
    p = jwc.parse_circular(read("jwc_circular_sample.txt"))
    assert p["circular"] == "JWLA-034" and p["date"] == date(2026, 10, 12)
    assert p["gcc_listed"] == ["AE", "BH", "KW", "OM", "QA", "SA"]


def test_jmic_parse():
    p = jmic.parse_dashboard(read("jmic_dashboard_sample.txt"))
    assert p["week"] == 8 and p["year"] == 2026 and p["week_end"] == date(2026, 2, 22)
    assert p["levels"]["red_sea"] == 2 and p["levels"]["gulf_of_aden"] == 2
    assert p["threats"] == {"houthi_to_mariners": 2, "piracy": 1, "gnss_interference": 3, "soh_harassment": 3, "soh_blockade": 2}
    assert p["key_events"] and p["key_events"][0][0] == date(2026, 2, 17)
    assert p["new_incidents"] == 1 and p["total_incidents"] == 128


def test_portwatch_parse():
    rows = portwatch.parse_csv(read("portwatch_sample.csv"))
    assert ("hormuz_transits", date(2026, 10, 11), 9.0) in rows
    assert sum(1 for s, _, _ in rows if s == "bab_el_mandeb_transits") == 2


def test_state_fms_parse():
    items = state_fms.parse_notifications(read("state_fms_sample.txt"))
    codes = {i["recipient"] for i in items}
    assert codes == {"KW", "AE", "SA"}
    sa = next(i for i in items if i["recipient"] == "SA")
    assert sa["date"] == date(2026, 9, 17) and sa["value_usd"] == 14.6e9


def test_ofac_parse():
    rows = sanctions.parse_ofac_sdn_csv(read("ofac_sdn_sample.csv"), read("ofac_add_sample.csv"))
    gulf = [r for r in rows if r["gulf_country"]]
    assert len(gulf) == 2 and all(r["gulf_country"] == "AE" for r in gulf)
    assert sum(1 for r in rows if r["iran_related"]) == 2


def test_rss_parse_and_rules_extraction():
    docs = rss_wires.parse_feed("qna", read("wire_sample.xml"))
    assert len(docs) == 2
    res = rules.extract(docs[0].text, date(2026, 10, 15), "en")
    hormuz = [o for o in res.observations if o.issue == "hormuz_posture"]
    assert hormuz and hormuz[0].score < 0 and hormuz[0].speaker_level == "spokesperson"
    res2 = rules.extract(docs[1].text, date(2026, 10, 14), "en")
    assert res2.events and res2.events[0].event_type == "intercept" and res2.events[0].country == "SA"


def test_egress_allowlist():
    check_egress("https://www.ukmto.org/x.pdf")
    try:
        check_egress("https://example.com/")
    except EgressRefused:
        return
    raise AssertionError("egress should have been refused")


def test_connectors_write_to_ledgers(db):
    ev = ukmto.ingest_text(db, read("ukmto_advisory_sample.txt"), external_id="fixture-901-26")
    assert ev is not None and ev.verification == "pending"
    parsed = jwc.ingest_text(db, read("jwc_circular_sample.txt"), external_id="fixture-jwla-034", previously_listed={"SA", "AE"})
    assert parsed["circular"] == "JWLA-034"
    n = portwatch.ingest_rows(db, portwatch.parse_csv(read("portwatch_sample.csv")))
    assert n >= 5
    n2 = state_fms.ingest(db, state_fms.parse_notifications(read("state_fms_sample.txt")))
    assert n2 == 3
    n3 = sanctions.ingest_designations(db, sanctions.parse_ofac_sdn_csv(read("ofac_sdn_sample.csv"), read("ofac_add_sample.csv")), date(2026, 10, 15))
    assert n3 == 2


def test_jmic_note_parse():
    import json

    from rasad.pipelines.connectors import jmic_notes, mscio

    fx = json.loads(read("jmic_note_sample.json"))
    p = jmic_notes.parse_note(fx["text"], fx["tables"], filename=fx["filename"])
    assert p.update_no == 40 and p.note_date == date(2026, 5, 3) and p.regional_level == 5
    assert p.area_levels["hormuz"] == 5 and p.area_levels["gulf_of_aden"] == 2 and p.area_levels["somali_basin"] == 4
    assert p.threats == {"piracy": 4}
    assert p.indicators["jmic_incidents_since_1mar"] == 37 and p.indicators["jmic_bam_transits_72h"] == 104
    assert (date(2026, 5, 1), 15.0) in p.dated_indicators["jmic_soh_observed_traffic_24h"]
    assert (date(2026, 5, 2), 4.0) in p.transits["jmic_soh_cargo_transits"] and (date(2026, 4, 27), 7.0) in p.transits["jmic_bam_tanker_transits"]
    refs = {i["ref"] for i in p.incidents}
    assert "021-26" in refs and any(i["vessel"] == "STENA IMPERATIVE" and i["country"] == "BH" for i in p.incidents)
    assert any(e["ref"] == "048-26" and e["event_type"] == "maritime_harassment" for e in p.ops_events)
    assert any(e["event_type"] == "seizure" and e["date"] == date(2026, 5, 2) for e in p.ops_events)
    assert mscio.classify(fx["filename"], "jmic_advisories") == "jmic_note"
    assert mscio.classify("20260912-UKMTO_WARNING_134-26.pdf", "ukmto_warnings") == "ukmto"
    assert mscio.classify("JMIC_Week_18_Dashboard.pdf", "jmic_dashboards") == "jmic_dashboard"


def test_ukmto_warning_parse():
    p = ukmto.parse_advisory(read("ukmto_warning_sample.txt"))
    assert p.advisory_no == "045-26" and p.category == "HIJACK" and p.event_type == "seizure"
    assert p.event_date == date(2026, 4, 21) and p.area == "GULF_OF_ADEN"
    assert p.location == "45NM northeast of Mareeyo, Somalia" and p.source_line == "Military authorities"
    assert p.lat and abs(p.lat - 8.93) < 0.01 and p.lon and abs(p.lon - 50.53) < 0.01


def test_mscio_weekly_parse():
    from rasad.pipelines.connectors import mscio, mscio_weekly

    p = mscio_weekly.parse_report(read("mscio_weekly_sample.txt"), "MSCIO_ATALANTA_WEEKLY_REPORT_09_OCT-16_OCT.pdf")
    assert p["week_end"] == date(2026, 10, 16) and p["counts"]["total"] == 13 and p["counts"]["attack"] == 12
    refs = {i["ref"] for i in p["incidents"]}
    assert "136/26" in refs and "138/26" in refs
    a136 = next(i for i in p["incidents"] if i["ref"] == "136/26")
    assert a136["date"] == date(2026, 10, 10) and a136["country"] == "HORMUZ" and a136["category"] == "attack"
    a138 = next(i for i in p["incidents"] if i["ref"] == "138/26")
    assert a138["country"] == "OM"
    assert mscio.classify("MSCIO_ATALANTA_WEEKLY_REPORT_09_OCT-16_OCT.pdf", "weekly_threat_assessment") == "mscio_weekly"
