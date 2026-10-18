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
    assert p.advisory_no == "101-26"
    assert p.event_date == date(2026, 10, 14)
    assert p.event_type == "maritime_attack" and p.area == "RED_SEA"
    assert p.lat and abs(p.lat - 14.205) < 0.01 and p.lon and abs(p.lon - 42.5167) < 0.01


def test_jwc_parse():
    p = jwc.parse_circular(read("jwc_circular_sample.txt"))
    assert p["circular"] == "JWLA-034" and p["date"] == date(2026, 10, 12)
    assert p["gcc_listed"] == ["AE", "BH", "KW", "OM", "QA", "SA"]


def test_jmic_parse():
    p = jmic.parse_dashboard(read("jmic_dashboard_sample.txt"))
    assert p["week"] == 41 and p["week_end"] == date(2026, 10, 11)
    assert p["levels"]["hormuz"] == 5 and p["levels"]["red_sea"] == 3 and p["mine_warning"]


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
    ev = ukmto.ingest_text(db, read("ukmto_advisory_sample.txt"), external_id="fixture-101-26")
    assert ev is not None and ev.verification == "pending"
    parsed = jwc.ingest_text(db, read("jwc_circular_sample.txt"), external_id="fixture-jwla-034", previously_listed={"SA", "AE"})
    assert parsed["circular"] == "JWLA-034"
    n = portwatch.ingest_rows(db, portwatch.parse_csv(read("portwatch_sample.csv")))
    assert n >= 5
    n2 = state_fms.ingest(db, state_fms.parse_notifications(read("state_fms_sample.txt")))
    assert n2 == 3
    n3 = sanctions.ingest_designations(db, sanctions.parse_ofac_sdn_csv(read("ofac_sdn_sample.csv"), read("ofac_add_sample.csv")), date(2026, 10, 15))
    assert n3 == 2
