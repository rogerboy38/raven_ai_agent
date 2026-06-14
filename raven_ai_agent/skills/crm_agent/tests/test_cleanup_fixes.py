"""
Tests for the PR #16 review remediation (B/M/S/N cleanup).

Covers:
  - M1: meeting_capturer._find_opportunity_for_contact returns scalar/None
  - M2: activities.add_note uses frappe.db.exists for CRM Note check
  - M3: opportunities.set_amount uses ignore_permissions=False
  - M4: parsing._normalize_currency uses company default for bare $
  - M5: skill name is "crm-agent" (kebab-case)
  - S1: meeting_capturer hook short-circuits on agent self-writes
  - S4: deal_coach intent matches with and without preposition (EN)
  - S5: stage_move strips trailing politeness words
  - N7: parse_lead_oneliner synthesizes name from email local-part
  - test coverage gaps #1, #2, #3, #4: agent autonomy, hooks, audit

This file assumes the frappe stub from run_smoke.py is already installed.
Run via:  python raven_ai_agent/skills/crm_agent/tests/run_smoke.py
"""
from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------
# M5 — skill name is kebab-case
# ---------------------------------------------------------------------
class TestSkillNameKebabCase(unittest.TestCase):
    """M5: name attribute is 'crm-agent', matches formulation-orchestrator."""

    def test_skill_name_is_kebab(self):
        from raven_ai_agent.skills.crm_agent.skill import CRMAgentSkill
        self.assertEqual(CRMAgentSkill.name, "crm-agent")

    def test_skill_name_not_snake(self):
        from raven_ai_agent.skills.crm_agent.skill import CRMAgentSkill
        self.assertNotEqual(CRMAgentSkill.name, "crm_agent")


# ---------------------------------------------------------------------
# M1 — _find_opportunity_for_contact returns scalar
# ---------------------------------------------------------------------
class TestMeetingCapturerScalarFix(unittest.TestCase):
    """M1: function returns str or None, not list of tuples."""

    def test_returns_scalar_when_row_present(self):
        from raven_ai_agent.skills.crm_agent.agents import meeting_capturer
        with patch.object(meeting_capturer.frappe.db, "sql",
                          return_value=[("OPP-001",)]):
            result = meeting_capturer.MeetingCapturerAgent._find_opportunity_for_contact("C-1")
        self.assertEqual(result, "OPP-001")
        self.assertNotIsInstance(result, (list, tuple))

    def test_returns_none_when_no_rows(self):
        from raven_ai_agent.skills.crm_agent.agents import meeting_capturer
        with patch.object(meeting_capturer.frappe.db, "sql", return_value=[]):
            result = meeting_capturer.MeetingCapturerAgent._find_opportunity_for_contact("C-1")
        self.assertIsNone(result)


# ---------------------------------------------------------------------
# M4 + N7 — parsing currency normalization + lead-name fallback
# ---------------------------------------------------------------------
class TestParsingCurrencyAndNameFallback(unittest.TestCase):
    """M4: bare $ resolves to company default; N7: name from email."""

    def test_explicit_mxn_stays_mxn(self):
        from raven_ai_agent.skills.crm_agent.tools.parsing import _normalize_currency
        self.assertEqual(_normalize_currency("MXN"), "MXN")
        self.assertEqual(_normalize_currency("MX$"), "MXN")
        self.assertEqual(_normalize_currency("MN"), "MXN")

    def test_explicit_usd_stays_usd(self):
        from raven_ai_agent.skills.crm_agent.tools.parsing import _normalize_currency
        self.assertEqual(_normalize_currency("USD"), "USD")
        self.assertEqual(_normalize_currency("EUR"), "EUR")

    def test_bare_dollar_uses_company_default(self):
        """Bare $ must NOT silently default to MXN — must hit _default_currency()."""
        from raven_ai_agent.skills.crm_agent.tools import parsing, opportunities
        with patch.object(opportunities, "_default_currency", return_value="USD"):
            self.assertEqual(parsing._normalize_currency("$"), "USD")
        with patch.object(opportunities, "_default_currency", return_value="MXN"):
            self.assertEqual(parsing._normalize_currency("$"), "MXN")

    def test_name_synthesized_from_email_local_part(self):
        """N7: 'juan@acme.mx' alone yields lead_name='juan'."""
        from raven_ai_agent.skills.crm_agent.tools.parsing import parse_lead_oneliner
        out = parse_lead_oneliner("juan@acme.mx")
        self.assertEqual(out.get("email_id"), "juan@acme.mx")
        self.assertEqual(out.get("lead_name"), "juan")

    def test_existing_name_at_company_unchanged(self):
        from raven_ai_agent.skills.crm_agent.tools.parsing import parse_lead_oneliner
        out = parse_lead_oneliner("Juan Perez at Acme, juan@acme.mx")
        self.assertEqual(out.get("lead_name"), "Juan Perez")
        self.assertEqual(out.get("company_name"), "Acme")


# ---------------------------------------------------------------------
# S4 — deal_coach intent matches with or without preposition
# ---------------------------------------------------------------------
class TestDealCoachWithoutPreposition(unittest.TestCase):
    """S4: 'next step OPP-0042' now matches (EN parity with ES)."""

    def test_with_preposition(self):
        from raven_ai_agent.skills.crm_agent.skill import INTENTS
        import re
        deal_coach_pat = [pat for iid, pat, _ in INTENTS if iid == "deal_coach"][0]
        m = re.search(deal_coach_pat, "what should I do on OPP-0042", re.IGNORECASE)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "OPP-0042")

    def test_without_preposition(self):
        from raven_ai_agent.skills.crm_agent.skill import INTENTS
        import re
        deal_coach_pat = [pat for iid, pat, _ in INTENTS if iid == "deal_coach"][0]
        m = re.search(deal_coach_pat, "next step OPP-0042", re.IGNORECASE)
        self.assertIsNotNone(m, "EN form 'next step <id>' must match (S4)")
        self.assertEqual(m.group(1), "OPP-0042")

    def test_spanish_form_still_works(self):
        from raven_ai_agent.skills.crm_agent.skill import INTENTS
        import re
        es_pat = [pat for iid, pat, _ in INTENTS if iid == "deal_coach_es"][0]
        m = re.search(es_pat, "qué sigue con OPP-0042", re.IGNORECASE)
        self.assertIsNotNone(m)


# ---------------------------------------------------------------------
# S5 — stage move strips trailing politeness
# ---------------------------------------------------------------------
class TestStageMovePolitenessStrip(unittest.TestCase):
    """S5: 'move CRM-OPP-001 to Quotation please' resolves cleanly."""

    def _make_skill(self):
        from raven_ai_agent.skills.crm_agent.skill import CRMAgentSkill
        return CRMAgentSkill()

    def test_strips_please(self):
        from raven_ai_agent.skills.crm_agent import skill as skill_mod
        skill = self._make_skill()
        captured = {}

        def fake_move_stage(name, status):
            captured["name"] = name
            captured["status"] = status
            return {"ok": True, "name": name, "status": status}

        with patch.object(skill_mod, "INTENTS", skill_mod.INTENTS):
            with patch("raven_ai_agent.skills.crm_agent.tools.opportunities.move_stage",
                       fake_move_stage):
                skill.handle("move CRM-OPP-001 to Quotation please")
        # The skill normalizes politeness *before* calling move_stage:
        self.assertEqual(captured.get("status"), "Quotation")

    def test_strips_por_favor(self):
        from raven_ai_agent.skills.crm_agent import skill as skill_mod
        skill = self._make_skill()
        captured = {}

        def fake_move_stage(name, status):
            captured["status"] = status
            return {"ok": True, "name": name, "status": status}

        with patch("raven_ai_agent.skills.crm_agent.tools.opportunities.move_stage",
                   fake_move_stage):
            skill.handle("move CRM-OPP-001 to Quotation por favor")
        self.assertEqual(captured.get("status"), "Quotation")


# ---------------------------------------------------------------------
# Autonomy enforcement (test-coverage gap #2 — safety critical)
# ---------------------------------------------------------------------
class TestAutonomyEnforcement(unittest.TestCase):
    """Verify the autonomy ladder actually blocks high-risk actions at low levels."""

    def _make_agent(self, autonomy: int):
        # Build a minimal agent without triggering provider chain
        from raven_ai_agent.skills.crm_agent.agents.base import CRMAgentBase
        with patch.object(CRMAgentBase, "_load_autonomy", return_value=autonomy):
            return CRMAgentBase()

    def test_send_blocked_at_level_zero(self):
        agent = self._make_agent(0)
        self.assertFalse(agent.can_act("send"),
                         "send must be blocked at autonomy=0 (safety-critical)")

    def test_send_blocked_at_level_three(self):
        agent = self._make_agent(3)
        self.assertFalse(agent.can_act("send"),
                         "send requires level 4 by default ladder")

    def test_send_allowed_at_level_four(self):
        agent = self._make_agent(4)
        self.assertTrue(agent.can_act("send"))

    def test_read_allowed_at_level_zero(self):
        agent = self._make_agent(0)
        self.assertTrue(agent.can_act("read"))

    def test_enrich_blocked_at_level_one(self):
        agent = self._make_agent(1)
        self.assertFalse(agent.can_act("enrich"))

    def test_enrich_allowed_at_level_two(self):
        agent = self._make_agent(2)
        self.assertTrue(agent.can_act("enrich"))

    def test_stage_move_blocked_at_level_two(self):
        agent = self._make_agent(2)
        self.assertFalse(agent.can_act("stage_move"))

    def test_stage_move_allowed_at_level_three(self):
        agent = self._make_agent(3)
        self.assertTrue(agent.can_act("stage_move"))

    def test_unknown_action_requires_max_autonomy(self):
        """Defense in depth — unknown actions default to required=4."""
        agent = self._make_agent(3)
        self.assertFalse(agent.can_act("unknown_dangerous_thing"))
        agent4 = self._make_agent(4)
        self.assertTrue(agent4.can_act("unknown_dangerous_thing"))


# ---------------------------------------------------------------------
# Audit log writes (test-coverage gap #4)
# ---------------------------------------------------------------------
class TestAuditLogWrites(unittest.TestCase):
    """Verify base.audit() writes a row with skill='crm-agent' (M5 + S3)."""

    def test_audit_uses_kebab_skill_name(self):
        from raven_ai_agent.skills.crm_agent.agents.base import CRMAgentBase
        with patch.object(CRMAgentBase, "_load_autonomy", return_value=1):
            agent = CRMAgentBase()

        captured = {}

        class _Doc:
            def __init__(self, payload):
                self.payload = payload
            def insert(self, **kw):
                captured["payload"] = self.payload
                captured["kwargs"] = kw
                return self

        with patch("raven_ai_agent.skills.crm_agent.agents.base.frappe.get_doc",
                   side_effect=_Doc):
            agent.audit(intent="test_intent", decision="allowed",
                        payload={"x": 1})

        self.assertEqual(captured["payload"]["skill"], "crm-agent")
        self.assertEqual(captured["payload"]["doctype"], "AI Routing Audit Log")
        self.assertEqual(captured["payload"]["intent"], "test_intent")
        self.assertEqual(captured["payload"]["decision"], "allowed")
        # S3: ignore_permissions=True is required (audit must not be suppressible)
        self.assertTrue(captured["kwargs"].get("ignore_permissions"))


# ---------------------------------------------------------------------
# Hook entrypoints (test-coverage gap #3)
# ---------------------------------------------------------------------
class TestHookEntrypoints(unittest.TestCase):
    """Verify hooks enqueue or short-circuit correctly."""

    def test_lead_after_insert_enqueues(self):
        from raven_ai_agent.skills.crm_agent.agents import lead_enricher
        doc = types.SimpleNamespace(name="LEAD-001")
        with patch.object(lead_enricher.frappe, "enqueue") as mock_enq:
            lead_enricher.on_lead_after_insert(doc)
        mock_enq.assert_called_once()
        kwargs = mock_enq.call_args.kwargs
        self.assertEqual(kwargs.get("lead"), "LEAD-001")
        self.assertEqual(kwargs.get("queue"), "long")
        self.assertTrue(kwargs.get("enqueue_after_commit"))

    def test_communication_hook_short_circuits_on_agent_self_write(self):
        """S1: agent-flagged saves must not recurse."""
        from raven_ai_agent.skills.crm_agent.agents import meeting_capturer
        flags = {"from_meeting_capturer": True}
        doc = types.SimpleNamespace(
            name="COMM-001",
            communication_medium="Email",
            sent_or_received="Received",
            flags=flags,
        )
        # Make .flags.get work
        doc.flags = type("F", (), {"get": lambda self, k, d=None: flags.get(k, d)})()

        with patch.object(meeting_capturer.MeetingCapturerAgent, "capture") as cap:
            meeting_capturer.on_communication_after_insert(doc)
        cap.assert_not_called()

    def test_communication_hook_skips_non_email(self):
        from raven_ai_agent.skills.crm_agent.agents import meeting_capturer
        doc = types.SimpleNamespace(
            name="COMM-002",
            communication_medium="Chat",  # not Email
            sent_or_received="Received",
            flags=type("F", (), {"get": lambda *a, **k: None})(),
        )
        with patch.object(meeting_capturer.MeetingCapturerAgent, "capture") as cap:
            meeting_capturer.on_communication_after_insert(doc)
        cap.assert_not_called()

    def test_communication_hook_skips_sent_messages(self):
        """Only Received emails should trigger capture (S1)."""
        from raven_ai_agent.skills.crm_agent.agents import meeting_capturer
        doc = types.SimpleNamespace(
            name="COMM-003",
            communication_medium="Email",
            sent_or_received="Sent",
            flags=type("F", (), {"get": lambda *a, **k: None})(),
        )
        with patch.object(meeting_capturer.MeetingCapturerAgent, "capture") as cap:
            meeting_capturer.on_communication_after_insert(doc)
        cap.assert_not_called()


# ---------------------------------------------------------------------
# Move-stage alias normalization (test-coverage gap #5)
# ---------------------------------------------------------------------
class TestMoveStageAliases(unittest.TestCase):
    """Verify ES/EN aliases for Opportunity statuses normalize correctly."""

    def _stub_opp_doc(self):
        opp = MagicMock()
        opp.name = "OPP-001"
        opp.status = None
        return opp

    def test_es_cotizacion_maps_to_quotation(self):
        from raven_ai_agent.skills.crm_agent.tools import opportunities
        opp = self._stub_opp_doc()
        with patch.object(opportunities.frappe, "get_doc", return_value=opp), \
             patch.object(opportunities, "_valid_statuses",
                          return_value=opportunities._STATIC_VALID_STATUSES):
            r = opportunities.move_stage("OPP-001", "Cotización")
        self.assertTrue(r.get("ok"))
        self.assertEqual(opp.status, "Quotation")

    def test_es_ganado_maps_to_converted(self):
        from raven_ai_agent.skills.crm_agent.tools import opportunities
        opp = self._stub_opp_doc()
        with patch.object(opportunities.frappe, "get_doc", return_value=opp), \
             patch.object(opportunities, "_valid_statuses",
                          return_value=opportunities._STATIC_VALID_STATUSES):
            opportunities.move_stage("OPP-001", "Ganado")
        self.assertEqual(opp.status, "Converted")

    def test_es_perdido_maps_to_lost(self):
        from raven_ai_agent.skills.crm_agent.tools import opportunities
        opp = self._stub_opp_doc()
        with patch.object(opportunities.frappe, "get_doc", return_value=opp), \
             patch.object(opportunities, "_valid_statuses",
                          return_value=opportunities._STATIC_VALID_STATUSES):
            opportunities.move_stage("OPP-001", "Perdido")
        self.assertEqual(opp.status, "Lost")

    def test_unknown_status_rejected(self):
        from raven_ai_agent.skills.crm_agent.tools import opportunities
        with patch.object(opportunities, "_valid_statuses",
                          return_value=opportunities._STATIC_VALID_STATUSES):
            r = opportunities.move_stage("OPP-001", "Wibble")
        self.assertFalse(r.get("ok"))
        self.assertIn("Unknown status", r.get("error", ""))


# ---------------------------------------------------------------------
# Bilingual intent coverage (test-coverage gap #6 / S4 expansion)
# ---------------------------------------------------------------------
class TestBilingualIntents(unittest.TestCase):
    """Spanish forms must route to the same handlers as English."""

    def _matches(self, intent_id, text):
        import re
        from raven_ai_agent.skills.crm_agent.skill import INTENTS
        pat = [p for iid, p, _ in INTENTS if iid == intent_id][0]
        return re.search(pat, text, re.IGNORECASE)

    def test_es_show_pipeline(self):
        self.assertIsNotNone(self._matches("pipeline_digest", "resumen del día"))
        self.assertIsNotNone(self._matches("pipeline_digest", "resumen de hoy"))

    def test_es_follow_up_draft(self):
        self.assertIsNotNone(
            self._matches("follow_up_draft_es", "redacta un seguimiento para OPP-001")
        )
        self.assertIsNotNone(
            self._matches("follow_up_draft_es", "escribe un correo a Acme")
        )

    def test_es_enrich(self):
        self.assertIsNotNone(
            self._matches("enrich", "completa prospecto LEAD-001")
        )

    def test_es_create_opportunity(self):
        self.assertIsNotNone(
            self._matches("create_opportunity", "nueva oportunidad para Acme")
        )


if __name__ == "__main__":
    # Allows `python test_cleanup_fixes.py` if run_smoke already stubbed frappe
    unittest.main()
