"""R3: bilingual misroute canaries.

Each utterance asserts which dispatcher stage claims it, using the REAL
framework skill registry (no skill mocks). If a routing change moves any
canary, this suite fails and the change must be justified.
"""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def frappe_mock():
    import frappe
    if not hasattr(frappe, "logger"):
        frappe.logger = MagicMock(return_value=MagicMock())
    if not hasattr(frappe, "conf"):
        frappe.conf = MagicMock()
    # registry doctype lookups fail open in tests
    frappe.get_all = MagicMock(return_value=[])
    return frappe


def _route(frappe_mock, utterance):
    """Real registry + real matching; skill EXECUTION stubbed (handlers need
    a live DB). Canaries assert routing selection only."""
    from raven_ai_agent.api import dispatcher
    from raven_ai_agent.skills.framework import get_registry, SkillRouter

    router = SkillRouter(get_registry(), None)

    def _route_stub(query, context=None):
        matches = sorted(router._find_matches(query), key=lambda m: (m[1], m[2]), reverse=True)
        if not matches:
            return None
        return {"handled": True, "response": "stubbed", "skill": matches[0][0]}

    router.route = _route_stub
    agent = MagicMock()
    agent.skill_router = router
    agent.provider = None  # semantic stage disabled -> deterministic canaries
    agent.process_query.return_value = {
        "success": True, "response": "v2", "context_used": {},
    }
    with patch("raven_ai_agent.api.agent_v2.RaymondLucyAgentV2", return_value=agent):
        return dispatcher.route(utterance, "canary@x.com")


# (utterance, expected_stage, expected_skill_substring_or_None)
CANARIES = [
    # --- explicit COA ids (EN + ES) must hit coa_validator exactly --------
    ("validate COA-26-0010",            "skill_exact", "coa_validator"),
    ("validar coa COA-26-0011",         "skill_exact", "coa_validator"),
    ("please revalidate COA 26 0431",   "skill_exact", "coa_validator"),
    # --- DQS precise patterns (doc-type + id) ------------------------------
    ("validate SO-00769",               "skill_exact", "data-quality-scanner"),
    ("scan sales order SO-00123",       "skill_exact", "data-quality-scanner"),
    # --- deterministic multi-agent pipelines -------------------------------
    ("workflow run SO-00752",           "multi_agent", None),
    ("full status SO-00123",            "multi_agent", None),
    # --- CRM agent owns digest/coaching phrasings (EN + ES, 0.9 patterns).
    #     NOTE: this shadows the older multi_agent 'morning_briefing' pipeline;
    #     if the aggregate sales+WO+payments briefing is ever wanted back,
    #     rename its trigger — do not lower crm-agent's confidence.
    ("morning briefing",                "skill_exact", "crm-agent"),
    ("resumen del día",                 "skill_exact", "crm-agent"),
    ("what should i do on OPP-0042",    "skill_exact", "crm-agent"),
    # --- broad triggers stay with the V2 agent (its internal skills route) -
    ("scan my data please",             "agent_v2", None),
    ("show my pending invoices",        "agent_v2", None),
    # --- explicit sensor id -> exact IoT skill (post best-score fix) -------
    ("temperature L01",                 "skill_exact", "iot_temperature"),
    # --- BOM/serial family -> bom-agent (2026-07-05 audit fixes) ----------
    ("bom health",                      "skill_exact", "bom-agent"),
    ("serial health",                   "skill_exact", "bom-agent"),
    ("validate bom BOM-0602-001",       "skill_exact", "bom-agent"),
    ("create bom from tds 0705 TDS pH 3.5-4.0", "skill_exact", "bom-agent"),
    ("bom status 0602",                 "skill_exact", "bom-agent"),
    # --- v2 commands (EN + ES) ---------------------------------------------
    ("bom repair wo MFG-WO-02625",      "skill_exact", "bom-agent"),
    ("reparar wo MFG-WO-02625",         "skill_exact", "bom-agent"),
    ("bom lots 0227",                   "skill_exact", "bom-agent"),
    ("bom plan create 0307 powder",     "skill_exact", "bom-agent"),
    ("salud bom",                       "skill_exact", "bom-agent"),
    ("bom help",                        "skill_exact", "bom-agent"),
]


class TestCanaries:
    @pytest.mark.parametrize("utterance,stage,skill", CANARIES,
                             ids=[c[0][:30] for c in CANARIES])
    def test_canary(self, frappe_mock, utterance, stage, skill):
        with patch("raven_ai_agent.api.multi_agent_router.execute_pipeline",
                   return_value="pipeline result"):
            result = _route(frappe_mock, utterance)
        assert result.get("stage") == stage, (
            f"{utterance!r} routed to {result.get('stage')} (skill={result.get('skill_used')}), "
            f"expected {stage}"
        )
        if skill:
            assert skill in (result.get("skill_used") or ""), (
                f"{utterance!r} handled by {result.get('skill_used')}, expected {skill}"
            )
