"""BOM Agent v2 tests — one class per design principle (docs/BOM_AGENT_V2_DESIGN.md)."""
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
    frappe.utils = MagicMock()
    return frappe


def _skill():
    from raven_ai_agent.skills.bom_agent.skill import BOMAgentSkill
    return BOMAgentSkill()


class TestP1Honesty:
    def test_phantom_created_reported_as_not_created(self, frappe_mock):
        """#79: pipeline says Created, no row exists -> NOT CREATED."""
        api = MagicMock(return_value={"message": "✅ Created",
                                      "bom_creator_name": "BC-PHANTOM"})
        frappe_mock.get_attr = MagicMock(return_value=api)
        frappe_mock.db.exists = MagicMock(return_value=False)
        r = _skill().handle("!create bom from tds 0307 spray dried")
        assert "NOT CREATED" in r["response"] and "#79" in r["response"]
        assert '"verified": false' in r["response"]

    def test_real_creation_verified_with_dod(self, frappe_mock):
        api = MagicMock(return_value={"message": "Created", "bom_creator_name": "BC-REAL"})
        frappe_mock.get_attr = MagicMock(return_value=api)
        frappe_mock.db.exists = MagicMock(return_value=True)
        r = _skill().handle("!create bom from tds 0307 spray dried")
        assert "VERIFIED" in r["response"] and "BC-REAL" in r["response"]
        assert '"verified": true' in r["response"]


class TestP2FamilyCoverage:
    def test_juice_resolves_to_0705_not_0227(self, frappe_mock):
        from raven_ai_agent.skills.bom_agent import family
        assert family.resolve("aloe juice concentrate").code == "0705"
        assert family.resolve("jugo concentrado").code == "0705"

    def test_no_template_family_refuses_before_pipeline(self, frappe_mock):
        api = MagicMock()
        frappe_mock.get_attr = MagicMock(return_value=api)
        r = _skill().handle("create bom from tds 0705 TDS pH 3.5-4.0")
        api.assert_not_called()
        assert "No BOM template for family 0705" in r["response"]
        assert "#78" in r["response"] and "no se creó" in r["response"].lower()


class TestP4DryRunGating:
    def test_bom_plan_is_always_dry_run(self, frappe_mock):
        api = MagicMock(return_value={"message": "plan"})
        frappe_mock.get_attr = MagicMock(return_value=api)
        r = _skill().handle("bom plan create 0307 spray dried powder")
        assert api.call_args.kwargs["dry_run"] is True
        assert "Dry run" in r["response"]


class TestP5WoRepair:
    def _wo(self, frappe_mock, docstatus=0, status="Draft", bom_no="BOM-GONE",
            bom_exists=False, candidate=None):
        frappe_mock.db.exists = MagicMock(
            side_effect=lambda dt, name=None: {"Work Order": True,
                                               "BOM": bom_exists}.get(dt, False))
        wo = MagicMock(docstatus=docstatus, status=status, bom_no=bom_no,
                       production_item="0227-PWD", qty=25)
        vals = [wo]
        if candidate is not None:
            frappe_mock.db.get_value = MagicMock(side_effect=[wo, candidate])
        else:
            frappe_mock.db.get_value = MagicMock(side_effect=[wo, None, None])
        return wo

    def test_submitted_wo_refused(self, frappe_mock):
        self._wo(frappe_mock, docstatus=1, status="In Process")
        r = _skill().handle("!bom repair wo MFG-WO-02625")
        assert "REFUSED" in r["response"] and "RECHAZADO" in r["response"]

    def test_plan_mode_reports_without_writing(self, frappe_mock):
        self._wo(frappe_mock, candidate="BOM-0227-009")
        frappe_mock.db.set_value = MagicMock()
        r = _skill().handle("bom repair wo MFG-WO-02625")
        frappe_mock.db.set_value.assert_not_called()
        assert "Plan only" in r["response"] and "BOM-0227-009" in r["response"]

    def test_execute_repoints_draft_wo_with_dod(self, frappe_mock):
        self._wo(frappe_mock, candidate="BOM-0227-009")
        frappe_mock.db.set_value = MagicMock()
        frappe_mock.db.commit = MagicMock()
        r = _skill().handle("!bom repair wo MFG-WO-02625")
        frappe_mock.db.set_value.assert_called_once_with(
            "Work Order", "MFG-WO-02625", "bom_no", "BOM-0227-009")
        assert "EXECUTED" in r["response"] and '"verified": true' in r["response"]

    def test_missing_wo_graceful(self, frappe_mock):
        frappe_mock.db.exists = MagicMock(return_value=False)
        r = _skill().handle("bom repair wo MFG-WO-99999")
        assert "not found" in r["response"]


class TestP7GoldenFefo:
    def test_fefo_orders_by_year_folio_not_date(self, frappe_mock):
        from raven_ai_agent.skills.bom_agent import golden
        codes = ["0227003261", "0227001251", "0227002251", "NOGOLDEN"]
        ranked = sorted(codes, key=golden.fefo_key)
        assert ranked == ["0227001251", "0227002251", "0227003261", "NOGOLDEN"]

    def test_bom_lots_ranks_and_labels(self, frappe_mock):
        rows = [MagicMock(name_=None) for _ in range(2)]
        r1 = MagicMock(batch_qty=10, item="0227"); r1.name = "0227002251"
        r2 = MagicMock(batch_qty=5, item="0227"); r2.name = "0227001251"
        frappe_mock.get_all = MagicMock(return_value=[r1, r2])
        r = _skill().handle("bom lots 0227")
        body = r["response"]
        assert body.index("0227001251") < body.index("0227002251")
        assert "Golden-Number" in body and "manufacturing_date" in body


class TestP9BilingualAndHelp:
    def test_spanish_triggers_match(self, frappe_mock):
        s = _skill()
        assert s.can_handle("salud bom")[0]
        assert s.can_handle("reparar wo MFG-WO-1")[0]
        assert s.can_handle("crear bom desde tds 0307")[0]
        assert s.can_handle("lotes bom 0227")[0]

    def test_help_card_lists_families_and_gates(self, frappe_mock):
        r = _skill().handle("bom help")
        body = r["response"]
        assert "0705🚫#78" in body and "0227✅" in body
        assert "Never" in body and "#77" in body
