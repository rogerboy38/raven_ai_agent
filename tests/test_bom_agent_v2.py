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
    # order-independence: default = amb_w_tds absent; tests that exercise the
    # amb path override get_attr explicitly (mock module is shared across files)
    frappe.get_attr = MagicMock(side_effect=ImportError("amb_w_tds not installed"))
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


class TestEsHandleCoverage:
    """Regression 09:10: 'salud bom' matched at 0.9 but handle() had no ES
    branch -> fell through to the LLM. Matching AND handling must agree."""

    def test_salud_bom_returns_health_report(self, frappe_mock):
        frappe_mock.db.count = MagicMock(side_effect=[10, 8, 6, 1, 0, 2])
        frappe_mock.db.sql = MagicMock(return_value=[])
        frappe_mock.db.exists = MagicMock(return_value=True)
        r = _skill().handle("salud bom")
        assert r is not None and "BOM Health" in r["response"]

    def test_every_own_match_is_handled(self, frappe_mock):
        """Structural guarantee: any phrase THIS skill claims (>=0.9) must be
        handled by THIS skill — never return None into the fallthrough."""
        frappe_mock.db.count = MagicMock(return_value=0)
        frappe_mock.db.sql = MagicMock(return_value=[])
        frappe_mock.db.exists = MagicMock(return_value=False)
        frappe_mock.db.get_value = MagicMock(return_value=None)
        s = _skill()
        phrases = ["bom health", "salud bom", "bom issues", "bom lots 0227",
                   "lotes bom 0227", "bom help", "ayuda bom", "serial health",
                   "bom repair wo MFG-WO-1", "reparar wo MFG-WO-1",
                   "validate bom BOM-1", "validar bom BOM-1",
                   "bom status 0602", "bom inspect BOM-1",
                   "simulate blend FMIX-1", "simular mezcla FMIX-1"]
        for q in phrases:
            can, conf = s.can_handle(q)
            if can and conf >= 0.9:
                assert s.handle(q) is not None, f"claimed but unhandled: {q!r}"


class TestRepairDraftQuickWin:
    def test_draft_bom_surfaces_b1_path(self, frappe_mock):
        """#70 B1: MFG-WO-02625 -> draft BOM-0433-001 should be offered."""
        frappe_mock.db.exists = MagicMock(
            side_effect=lambda dt, name=None: dt == "Work Order")
        wo = MagicMock(docstatus=0, status="Draft", bom_no="BOM-0433-002",
                       production_item="0433", qty=25)
        # get_value calls: WO fields -> submitted candidates (2x None) -> draft
        frappe_mock.db.get_value = MagicMock(side_effect=[wo, None, None, "BOM-0433-001"])
        r = _skill().handle("bom repair wo MFG-WO-02625")
        assert "BOM-0433-001" in r["response"] and "quick-win" in r["response"]


class TestFefoGoldenSource:
    """rvnv2r1 evidence-pack regression: goldens live in Batch AMB.custom_
    golden_number, not tabBatch.name — ranking must use them when present."""

    def test_ranks_by_batch_amb_golden_not_name(self, frappe_mock):
        b1 = MagicMock(batch_qty=10, item="0334"); b1.name = "LOTE-B"   # golden y26 f009
        b2 = MagicMock(batch_qty=5, item="0334");  b2.name = "LOTE-A"   # golden y26 f002
        def get_all(dt, filters=None, fields=None, limit=None):
            if dt == "Batch":
                return [b1, b2]
            if dt == "Batch AMB" and "name" in (filters or {}):
                return [{"name": "LOTE-B", "custom_golden_number": "0334009263"},
                        {"name": "LOTE-A", "custom_golden_number": "0334002263"}]
            return []
        frappe_mock.get_all = MagicMock(side_effect=get_all)
        frappe_mock.db.exists = MagicMock(return_value=True)
        r = _skill().handle("bom lots 0334")
        body = r["response"]
        # LOTE-A (folio 002) must rank before LOTE-B (folio 009)
        assert body.index("LOTE-A") < body.index("LOTE-B")
        assert "Batch AMB" in body and "0334002263" in body

    def test_falls_back_to_name_then_no_golden(self, frappe_mock):
        b1 = MagicMock(batch_qty=1, item="0227"); b1.name = "0227001251"  # parseable name
        b2 = MagicMock(batch_qty=1, item="0227"); b2.name = "LOTE-XYZ"    # nothing
        def get_all(dt, filters=None, fields=None, limit=None):
            return [b1, b2] if dt == "Batch" else []
        frappe_mock.get_all = MagicMock(side_effect=get_all)
        frappe_mock.db.exists = MagicMock(return_value=True)
        r = _skill().handle("bom lots 0227")
        body = r["response"]
        assert body.index("0227001251") < body.index("LOTE-XYZ")
        assert "from batch name" in body and "no-golden" in body

    def test_batch_amb_absent_fails_open(self, frappe_mock):
        b1 = MagicMock(batch_qty=1, item="0227"); b1.name = "LOTE-1"
        frappe_mock.get_all = MagicMock(return_value=[b1])
        frappe_mock.db.exists = MagicMock(return_value=False)
        r = _skill().handle("bom lots 0227")
        assert r["handled"] and "no-golden" in r["response"]


class TestFefoBatchAmbPrimary:
    """Second executor finding: tabBatch<->Batch AMB row link is EMPTY on prod
    (two-hop join = 0). Batch AMB via golden product-prefix is PRIMARY."""

    def test_batch_amb_rows_listed_directly(self, frappe_mock):
        def get_all(dt, filters=None, fields=None, limit=None):
            if dt == "Batch AMB" and "custom_golden_number" in (filters or {}):
                return [{"name": "LOTE-26-16-0001", "custom_golden_number": "0334009263",
                         "lote_amb_reference": "rc737cemaj"},
                        {"name": "LOTE-26-14-0001", "custom_golden_number": "0334002263",
                         "lote_amb_reference": ""}]
            return []
        frappe_mock.get_all = MagicMock(side_effect=get_all)
        frappe_mock.db.exists = MagicMock(return_value=True)
        r = _skill().handle("bom lots 0334")
        body = r["response"]
        assert "Batch AMB production lots" in body and "authoritative" in body
        # folio 002 before folio 009
        assert body.index("LOTE-26-14-0001") < body.index("LOTE-26-16-0001")
        assert "rc737cemaj" in body

    def test_no_amb_rows_falls_back_to_tabbatch(self, frappe_mock):
        b1 = MagicMock(batch_qty=1, item="0227"); b1.name = "0227001251"
        def get_all(dt, filters=None, fields=None, limit=None):
            if dt == "Batch AMB":
                return []
            if dt == "Batch":
                return [b1]
            return []
        frappe_mock.get_all = MagicMock(side_effect=get_all)
        frappe_mock.db.exists = MagicMock(return_value=True)
        r = _skill().handle("bom lots 0227")
        assert "0227001251" in r["response"] and "from batch name" in r["response"]


class TestServerScriptHazardDetector:
    """2026-07-05 incident: DB-resident 'Raven Channel Permission Patch' with
    illegal import broke every Batch insert once server_script_enabled=1."""

    def _health(self, frappe_mock, scripts, enabled=True):
        frappe_mock.db.count = MagicMock(return_value=0)
        frappe_mock.db.sql = MagicMock(return_value=[])
        frappe_mock.db.exists = MagicMock(return_value=True)
        def get_all(dt, filters=None, fields=None, **kw):
            if dt == "Server Script":
                return scripts
            return []
        frappe_mock.get_all = MagicMock(side_effect=get_all)
        frappe_mock.conf = MagicMock()
        frappe_mock.conf.get = MagicMock(return_value=enabled)
        return _skill().handle("bom health")["response"]

    def test_illegal_import_flagged_active(self, frappe_mock):
        body = self._health(frappe_mock, [
            {"name": "Raven Channel Permission Patch", "script_type": "DocType Event",
             "reference_doctype": "Batch",
             "script": "import frappe\nfrappe.msgprint('x')"}], enabled=True)
        assert "ILLEGAL imports" in body
        assert "Raven Channel Permission Patch" in body
        assert "breaking NOW" in body

    def test_latent_when_flag_off(self, frappe_mock):
        body = self._health(frappe_mock, [
            {"name": "Bad One", "script_type": "API", "reference_doctype": None,
             "script": "from x import y"}], enabled=False)
        assert "latent" in body

    def test_clean_scripts_pass(self, frappe_mock):
        body = self._health(frappe_mock, [
            {"name": "Good", "script_type": "DocType Event", "reference_doctype": "Batch",
             "script": "doc = frappe.get_doc(doctype, name)\n# importantly not an import"}])
        assert "✅ No illegal-import Server Scripts" in body
