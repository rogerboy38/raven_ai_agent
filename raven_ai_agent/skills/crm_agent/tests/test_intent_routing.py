"""
Smoke tests for crm_agent intent routing.

These tests assume `frappe` and `raven_ai_agent.skills.framework` are
already stubbed (see sibling `run_smoke.py`) OR a live Frappe bench is
available. Run from a bench:

    bench --site <site> run-tests --app raven_ai_agent \\
        --module raven_ai_agent.skills.crm_agent.tests.test_intent_routing

Or standalone (CI-friendly):

    python raven_ai_agent/skills/crm_agent/tests/run_smoke.py
"""
from __future__ import annotations

import unittest
from unittest.mock import patch
import re

from raven_ai_agent.skills.crm_agent.skill import CRMAgentSkill, INTENTS


class IntentRoutingTests(unittest.TestCase):
    """Verify the regex INTENTS table maps utterances to expected intents."""

    EXPECTED = [
        # (utterance, expected_intent_id)
        ("morning brief", "pipeline_digest"),
        ("pipeline digest", "pipeline_digest"),
        ("resumen del día", "pipeline_digest"),
        ("show pipeline", "pipeline_list"),
        ("list my opportunities", "pipeline_list"),
        ("what should I do next on Opp-0042?", "deal_coach"),
        ("next step on Opp-0042", "deal_coach"),
        ("¿qué sigue con Opp-0042?", "deal_coach_es"),
        ("draft follow-up for Opp-0042", "follow_up_draft"),
        ("write followup for Opp-0042", "follow_up_draft"),
        ("redacta un seguimiento para Opp-0042", "follow_up_draft_es"),
        ("move Opp-0042 to Quotation", "stage_move"),
        ("enrich lead LEAD-2026-00031", "enrich"),
        ("completa lead LEAD-2026-00031", "enrich"),
        ("new lead Juan Perez at Acme, juan@acme.mx", "create_lead"),
        ("create opportunity Renewal Acme Q3, 250000 MXN", "create_opportunity"),
        ("crm help", "crm_help"),
    ]

    @staticmethod
    def _match_intent(utterance: str):
        for intent_id, pattern, _handler in INTENTS:
            if re.search(pattern, utterance, re.IGNORECASE):
                return intent_id
        return None

    def test_each_expected_utterance_matches(self):
        for utterance, expected in self.EXPECTED:
            with self.subTest(utterance=utterance):
                self.assertEqual(
                    self._match_intent(utterance), expected,
                    f"`{utterance}` should route to `{expected}`"
                )

    def test_unmatched_utterance_returns_none(self):
        for utterance in ("what's the weather", "deploy to prod",
                          "calcula la fórmula del aloe"):
            with self.subTest(utterance=utterance):
                self.assertIsNone(self._match_intent(utterance))


class SkillHandleTests(unittest.TestCase):
    """handle() should dispatch and return a SkillBase response dict."""

    def setUp(self):
        self.skill = CRMAgentSkill()

    def test_help_intent_is_handled_directly(self):
        out = self.skill.handle("crm help")
        self.assertIsNotNone(out)
        self.assertTrue(out["handled"])
        self.assertIn("CRM Agent", out["response"])
        self.assertEqual(out["intent"], "crm_help")

    def test_pipeline_list_uses_opportunities_tool(self):
        with patch(
            "raven_ai_agent.skills.crm_agent.tools.opportunities.list_open_opportunities",
            return_value=[],
        ):
            out = self.skill.handle("show pipeline")
        self.assertIsNotNone(out)
        self.assertEqual(out["intent"], "pipeline_list")

    def test_unrelated_query_returns_none(self):
        self.assertIsNone(self.skill.handle("calcula la fórmula del aloe 200L"))


class ParsingTests(unittest.TestCase):
    """One-liner parsers used by create_lead / create_opportunity."""

    def test_lead_parser_extracts_email_and_company(self):
        from raven_ai_agent.skills.crm_agent.tools.parsing import parse_lead_oneliner
        out = parse_lead_oneliner(
            "Juan Perez at Acme, juan@acme.mx, interested in 5L sanitizer"
        )
        self.assertEqual(out.get("lead_name"), "Juan Perez")
        self.assertEqual(out.get("company_name"), "Acme")
        self.assertEqual(out.get("email_id"), "juan@acme.mx")
        self.assertIn("sanitizer", (out.get("notes") or "").lower())

    def test_opp_parser_extracts_amount_currency_date(self):
        from raven_ai_agent.skills.crm_agent.tools.parsing import parse_opp_oneliner
        out = parse_opp_oneliner(
            "Renewal Acme Q3 for Acme, 250000 MXN, closing 2026-09-30"
        )
        self.assertEqual(out.get("opportunity_amount"), 250000.0)
        self.assertEqual(out.get("currency"), "MXN")
        self.assertEqual(out.get("expected_closing"), "2026-09-30")
        self.assertEqual(out.get("party_name"), "Acme")


if __name__ == "__main__":
    unittest.main()
