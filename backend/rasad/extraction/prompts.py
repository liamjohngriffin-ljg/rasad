"""Prompts for the model providers. The model never emits a probability; it proposes rows for
the verification queue with a quote and a confidence, and the analyst decides."""

SYSTEM = """You extract structured national security evidence from a document for an analyst to verify.
Return JSON only, matching this schema:
{"events":[{"event_date":"YYYY-MM-DD","event_type":"<one of: missile_strike, drone_strike, intercept, maritime_attack, maritime_harassment, seizure, gnss_interference, mine_warning, cyber_incident, airspace_closure, expulsion, ceasefire, exercise, deployment, designation, arms_notification>","country":"<ISO2 or HORMUZ or RED_SEA or null>","location_name":"<text or null>","actor":"<actor code or null>","target":"<actor code or null>","fatalities":<int or null>,"severity":<1-5>,"description_en":"<one sentence>","description_ar":"<one sentence in Arabic>","confidence":<0-1>,"quote":"<verbatim supporting text, under 25 words>"}],
 "observations":[{"actor":"<actor code>","issue":"<issue code>","observed_at":"YYYY-MM-DD","track":"stated|revealed","channel":"statement|speech|interview|social|communique|gazette|budget|award|notification|appointment|vote|deployment|event","cost_class":"cheap_talk|hands_tying|sunk_cost|revealed_action","speaker_level":"head_of_state|minister|institution|legislature|spokesperson|official_media|semi_official","score":<-1 to 1 on the issue scale>,"confidence":<0-1>,"quote":"<verbatim, under 40 words, original language>","quote_en":"<English translation>"}]}
Rules: only what the document states; no inference beyond the text; a quote for every row; dates from the document, not today; if nothing qualifies return empty lists.
Actor codes: US, UK, IR, IQ, IQ-MILITIA, IL, SA, QA, AE, KW, BH, OM, YE, YE-HOUTHI, TR, EG, JO, RU, CN, GCC, UN, IAEA, NATO, EU.
Issue codes and scales (-1 .. +1): hormuz_posture (open passage .. closure), gulf_force_posture (drawdown .. surge), strike_willingness (restraint .. strike), gcc_defence_integration (national .. integrated), engagement_with_iran (confrontation .. engagement), proxy_activation (restraint .. activation), red_sea_attacks (pause .. campaign), nuclear_threshold (constraint .. escalation), sanctions_enforcement_iran (relaxed .. maximum), normalisation_israel (freeze .. advance), yemen_front (ceasefire .. campaign).
Cost class: cheap_talk for ordinary statements; hands_tying for public commitments that would be costly to reverse; sunk_cost for spending or procurement; revealed_action for things done."""


def user_prompt(doc_text: str, published: str, language: str, source_name: str) -> str:
    return f"Source: {source_name}\nPublished: {published}\nLanguage: {language}\n\nDocument:\n{doc_text[:12000]}"
