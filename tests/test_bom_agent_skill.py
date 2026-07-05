"""bom-agent skill: discovery, precedence over greedy skills, dispatch."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def frappe_mock():
    import frappe
    if not hasattr(frappe, "logger"):
        frappe.logger = MagicMock(return_value=MagicMock())
    if not hasattr(frappe, "conf"):
        frappe.conf = MagicMock()
    frappe.get_all = MagicMock(return_value=[])
    return frappe


class TestDiscoveryAndPrecedence:
    def test_registered_in_framework_registry(self, frappe_mock):
        from raven_ai_agent.skills import framework
        assert "bom-agent" in framework.get_registry().get_all()

    def test_outranks_dqs_for_validate_bom(self, frappe_mock):
        """Live regression 2026-07-05 01:51: 'validate bom BOM-0602-001'
        returned the data-quality-scanner HELP CARD."""
        from raven_ai_agent.skills.framework import get_registry, SkillRouter
        r = SkillRouter(get_registry(), None)
        top = sorted(r._find_matches("validate bom BOM-0602-001"),
                     key=lambda m: (m[1], m[2]), reverse=True)[0]
        assert top[0] == "bom-agent" and top[1] >= 0.9

    def test_outranks_formulation_advisor_for_create_from_tds(self, frappe_mock):
        """Live regression 2026-07-05 01:52: 'create bom from tds …' was
        claimed by formulation-advisor ('No batches found in tds')."""
        from raven_ai_agent.skills.framework import get_registry, SkillRouter
        r = SkillRouter(get_registry(), None)
        top = sorted(r._find_matches("create bom from tds 0705 TDS pH 3.5-4.0"),
                     key=lambda m: (m[1], m[2]), reverse=True)[0]
        assert top[0] == "bom-agent" and top[1] >= 0.9

    def test_does_not_claim_show_or_submit_bom(self, frappe_mock):
        """Write ops + show stay with the workflow stage."""
        from raven_ai_agent.skills.bom_agent.skill import BOMAgentSkill
        s = BOMAgentSkill()
        assert s.can_handle("show bom BOM-0602-001")[0] is False
        assert s.can_handle("!submit bom BOM-0602-001")[0] is False
        assert s.can_handle("!cancel bom BOM-0602-001")[0] is False


class TestDispatch:
    def _skill(self):
        from raven_ai_agent.skills.bom_agent.skill import BOMAgentSkill
        return BOMAgentSkill()

    def test_bom_health_report(self, frappe_mock):
        frappe_mock.db.count = MagicMock(side_effect=[100, 80, 60, 10, 5, 3])
        frappe_mock.db.sql = MagicMock(return_value=[])
        frappe_mock.db.exists = MagicMock(return_value=True)
        r = self._skill().handle("bom health")
        assert r["handled"] and "BOM Health" in r["response"]
        assert "Total BOMs: **100**" in r["response"]

    def test_serial_status_found(self, frappe_mock):
        frappe_mock.db.exists = MagicMock(return_value=True)
        frappe_mock.db.get_value = MagicMock(return_value=MagicMock(
            item_code="0307", status="Active", batch_no="LOTE-26-25-0003",
            warehouse="Stores"))
        r = self._skill().handle("serial status SN-0001")
        assert r["handled"] and "SN-0001" in r["response"] and "LOTE-26-25-0003" in r["response"]

    def test_create_from_tds_delegates_and_reports_draft(self, frappe_mock):
        import sys, types
        agent = MagicMock()
        agent.create_bom_from_tds.return_value = {
            "success": True, "message": "BOM Creator created",
            "bom_creator_name": "BOM-TDS-0705",
        }
        # stub module import (agents/__init__ pulls iot_agent, whose f-string
        # syntax needs py3.12+; bench is 3.14, CI sandboxes may be older)
        pkg = types.ModuleType("raven_ai_agent.agents")
        mod = types.ModuleType("raven_ai_agent.agents.bom_creator_agent")
        mod.BOMCreatorAgent = MagicMock(return_value=agent)
        saved = {k: sys.modules.get(k) for k in (pkg.__name__, mod.__name__)}
        sys.modules[pkg.__name__] = pkg
        sys.modules[mod.__name__] = mod
        try:
            r = self._skill().handle("create bom from tds 0705")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        assert r["handled"] and "BOM-TDS-0705" in r["response"] and "!submit" in r["response"]

    def test_create_from_tds_passes_full_multiword_name(self, frappe_mock):
        """Live regression 2026-07-05 02:08: 'create bom from tds 0705 TDS
        pH 3.5-4.0' extracted only '0705' -> not found."""
        import sys, types
        agent = MagicMock()
        agent.create_bom_from_tds.return_value = {"success": True, "message": "ok",
                                                  "bom_creator_name": "BC-1"}
        pkg = types.ModuleType("raven_ai_agent.agents")
        mod = types.ModuleType("raven_ai_agent.agents.bom_creator_agent")
        mod.BOMCreatorAgent = MagicMock(return_value=agent)
        saved = {k: sys.modules.get(k) for k in (pkg.__name__, mod.__name__)}
        sys.modules[pkg.__name__] = pkg; sys.modules[mod.__name__] = mod
        try:
            r = self._skill().handle("create bom from tds 0705 TDS pH 3.5-4.0")
        finally:
            for k, v in saved.items():
                if v is None: sys.modules.pop(k, None)
                else: sys.modules[k] = v
        agent.create_bom_from_tds.assert_called_once_with("0705 TDS pH 3.5-4.0")
        assert r["handled"] and "BC-1" in r["response"]

    def test_simulate_blend_missing_doctype_is_graceful(self, frappe_mock):
        frappe_mock.db.exists = MagicMock(return_value=False)
        r = self._skill().handle("simulate blend FMIX-0334-001")
        assert r["handled"] and "not installed" in r["response"]

    def test_errors_never_raise(self, frappe_mock):
        frappe_mock.db.count = MagicMock(side_effect=RuntimeError("db down"))
        r = self._skill().handle("bom health")
        assert r["handled"] and "❌" in r["response"]
