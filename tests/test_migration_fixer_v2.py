"""migration-fixer v2 tests — census-first, dry-run default, `!` executes,
draft-only writes, DoD JSON, honesty layer, bilingual (house v2 standard)."""
import os
import re
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def frappe_mock():
    import frappe
    if not hasattr(frappe, "logger"):
        frappe.logger = MagicMock(return_value=MagicMock())
    frappe.conf = MagicMock()
    frappe.get_all = MagicMock(return_value=[])
    frappe.utils = MagicMock()
    frappe.utils.today = MagicMock(return_value="2026-07-06")
    return frappe


def _skill():
    from raven_ai_agent.skills.migration_fixer.skill import MigrationFixerSkill
    return MigrationFixerSkill()


PILOT_JSON = {
    "folio": 752,
    "invoice_header": {"folio": 752, "cliente": "LEGOSAN AB", "factura": "F2227",
                       "fecha": "2024-01-15", "moneda": "USD"},
    "invoice_lines": [{"lote_real": "0612185231", "item_code": "ITEM_0612185231",
                       "descripcion": "ALOE QX ALOE 70%+ GOMA BB 30%",
                       "cantidad": 150.0, "precio": 101.81}],
    "coa_data": {},
}


def _census(so_refs=None, batch_status="MISSING"):
    """Minimal census dict shaped like census.census_folio output."""
    from raven_ai_agent.skills.migration_fixer.census import STAGES
    stages = {s: {"status": "MISSING", "refs": [], "note": ""} for s in STAGES}
    if so_refs:
        stages["sales_order"] = {"status": "OK", "refs": so_refs, "note": "matched"}
    lots = {"0612185231": {
        "variants": ["0612185231", "612185231"],
        "batch_amb": {"status": batch_status, "refs": [], "note": ""},
        "native_batch": {"status": "MISSING", "refs": [], "note": ""},
        "c_source": {"source": "regenerated", "pack_kg": 25.0, "count": 6},
    }}
    return {"folio": 752, "header": {"cliente": "LEGOSAN AB", "factura": "F2227",
                                     "fecha": "2024-01-15", "lineas": 1},
            "stages": stages, "lots": lots, "issues": []}


@pytest.fixture()
def executor_env(frappe_mock):
    """execute_stage with sources + census patched to the pilot fixture."""
    src = MagicMock()
    src.load_folio_json = MagicMock(return_value=dict(PILOT_JSON))
    with patch("raven_ai_agent.skills.migration_fixer.executor.get_sources",
               return_value=src), \
         patch("raven_ai_agent.skills.migration_fixer.executor.census_folio") as cf:
        yield cf


class TestRouting:
    def test_v2_commands_score_pattern_confidence(self, frappe_mock):
        s = _skill()
        for q in ["migrate scan folio 752", "migrate scan 2024",
                  "migrate folio 752", "!migrate folio 752 stage so",
                  "migrar folio 752", "censo migración 2024",
                  "migrate help"]:
            can, conf = s.can_handle(q)
            assert can and conf >= 0.9, f"{q!r} scored {conf}"

    def test_legacy_commands_still_match(self, frappe_mock):
        s = _skill()
        for q in ["scan migration 2024", "fix folio 00752 confirm",
                  "compare folio 00752", "migration report 2025"]:
            assert s.can_handle(q)[0], f"{q!r} lost"


class TestCensusReadOnly:
    """Fixture-level guard: the census/sources modules must contain no write
    primitives at all — scan is read-only by construction, not by discipline."""

    FORBIDDEN = re.compile(
        r"\b(new_doc|insert|set_value|\.submit|delete_doc|db\.commit|rename_doc)\b")

    @pytest.mark.parametrize("module", ["census.py", "sources.py", "census_runner.py"])
    def test_no_write_primitives_in_source(self, module):
        base = os.path.join(os.path.dirname(__file__), "..",
                            "raven_ai_agent", "skills", "migration_fixer")
        with open(os.path.join(base, module)) as f:
            src = f.read()
        hits = self.FORBIDDEN.findall(src)
        assert not hits, f"{module} contains write primitives: {hits}"

    def test_scan_folio_returns_census_table(self, frappe_mock):
        with patch("raven_ai_agent.skills.migration_fixer.census.census_folio",
                   return_value=_census(so_refs=["SO-00752-LEGOSAN AB"])):
            r = _skill().handle("migrate scan folio 752")
        body = r["response"]
        assert "SO-00752-LEGOSAN AB" in body
        assert "solo lectura" in body.lower() or "read-only" in body.lower()


class TestDryRunGating:
    def test_stage_command_defaults_to_plan(self, frappe_mock):
        with patch("raven_ai_agent.skills.migration_fixer.executor.execute_stage",
                   return_value="plan") as ex:
            _skill().handle("migrate folio 752 stage so")
        assert ex.call_args.kwargs["execute"] is False

    def test_bang_prefix_executes(self, frappe_mock):
        with patch("raven_ai_agent.skills.migration_fixer.executor.execute_stage",
                   return_value="done") as ex:
            _skill().handle("!migrate folio 752 stage so date-policy=historical")
        assert ex.call_args.kwargs["execute"] is True
        assert ex.call_args.kwargs["date_policy"] == "historical"

    def test_plan_creates_nothing(self, frappe_mock, executor_env):
        from raven_ai_agent.skills.migration_fixer.executor import execute_stage
        executor_env.return_value = _census()
        frappe_mock.new_doc = MagicMock()
        frappe_mock.db.get_value = MagicMock(return_value="LEGOSAN AB")
        frappe_mock.db.exists = MagicMock(return_value=True)
        body = execute_stage(752, "so", execute=False)
        frappe_mock.new_doc.assert_not_called()
        assert "Plan only" in body or "Solo plan" in body


class TestDM1Gate:
    def test_execute_without_date_policy_refuses(self, frappe_mock, executor_env):
        from raven_ai_agent.skills.migration_fixer.executor import execute_stage
        executor_env.return_value = _census()
        frappe_mock.new_doc = MagicMock()
        body = execute_stage(752, "so", execute=True, date_policy=None)
        frappe_mock.new_doc.assert_not_called()
        assert "REFUSED" in body and "D-M1" in body and "RECHAZADO" in body


class TestHonestyLayer:
    def _run_create(self, frappe_mock, executor_env, row_exists_after):
        from raven_ai_agent.skills.migration_fixer.executor import execute_stage
        executor_env.return_value = _census()
        frappe_mock.db.get_value = MagicMock(return_value="LEGOSAN AB")
        frappe_mock.db.exists = MagicMock(
            side_effect=lambda dt, name=None: dt == "Item" or
            (dt == "Sales Order" and row_exists_after))
        doc = MagicMock()
        doc.name = "SO-TEST-DRAFT"
        frappe_mock.new_doc = MagicMock(return_value=doc)
        return execute_stage(752, "so", execute=True, date_policy="historical"), doc

    def test_phantom_create_reported_not_created(self, frappe_mock, executor_env):
        body, doc = self._run_create(frappe_mock, executor_env, row_exists_after=False)
        doc.insert.assert_called_once()
        assert "NOT CREATED" in body and "NO SE CREÓ" in body
        assert '"verified": false' in body

    def test_real_create_verified_with_dod(self, frappe_mock, executor_env):
        body, doc = self._run_create(frappe_mock, executor_env, row_exists_after=True)
        doc.insert.assert_called_once()
        doc.submit.assert_not_called()  # draft-only, always
        assert "VERIFIED" in body and "SO-TEST-DRAFT" in body
        assert '"verified": true' in body and '"date_policy": "historical"' in body

    def test_existing_so_is_noop_not_duplicate(self, frappe_mock, executor_env):
        from raven_ai_agent.skills.migration_fixer.executor import execute_stage
        executor_env.return_value = _census(so_refs=["SO-00752-LEGOSAN AB"])
        frappe_mock.new_doc = MagicMock()
        frappe_mock.db.exists = MagicMock(return_value=True)
        body = execute_stage(752, "so", execute=True, date_policy="historical")
        frappe_mock.new_doc.assert_not_called()
        assert "already exists" in body and "noop_so_exists" in body

    def test_missing_json_refuses(self, frappe_mock):
        from raven_ai_agent.skills.migration_fixer.executor import execute_stage
        src = MagicMock()
        src.load_folio_json = MagicMock(return_value=None)
        with patch("raven_ai_agent.skills.migration_fixer.executor.get_sources",
                   return_value=src):
            body = execute_stage(999999, "so", execute=True, date_policy="historical")
        assert "REFUSED" in body and "RECHAZADO" in body


class TestUnautomatedStagesRefuse:
    @pytest.mark.parametrize("stage", ["dn", "si", "payment", "se"])
    def test_honest_refusal(self, frappe_mock, executor_env, stage):
        from raven_ai_agent.skills.migration_fixer.executor import execute_stage
        executor_env.return_value = _census()
        body = execute_stage(752, stage, execute=True)
        assert "not automated" in body and "refuse_unautomated_stage" in body


class TestCSources:
    def _src(self, trazab=None, env2=None):
        from raven_ai_agent.skills.migration_fixer.sources import FolioSources
        s = FolioSources(json_dir="/x", xlsx_path="/x.xlsx", dbf_dir="/x",
                         census_dir="/x")
        s._trazab_index = trazab if trazab is not None else {}
        s._env2_rows = env2 if env2 is not None else []
        return s

    def test_priority_a_trazab(self):
        s = self._src(trazab={"0612185231": {"1": ["1", "2", "3"]}})
        r = s.resolve_containers("0612185231", qty_kg=150)
        assert r["source"] == "extracted-trazab" and r["count"] == 3

    def test_priority_b_env2_proven_lote(self):
        s = self._src(env2=[{"LOTE": "0612185231", "FACTURA": "",
                             "C_INICIAL": "  1", "C_FINAL": "  6"}])
        r = s.resolve_containers("0612185231", factura="F2227", qty_kg=150)
        assert r["source"] == "extracted-env2" and r["count"] == 6

    def test_priority_c_regenerated_pack_standard(self):
        s = self._src()
        r = s.resolve_containers("0612185231", factura="F2227", qty_kg=150)
        assert r["source"] == "regenerated" and r["count"] == 6  # 150 / 25 kg

    def test_factura_alone_is_not_proven_for_containers(self):
        """env2 rows matched only on FACTURA must not mint container ranges —
        the LOTE key is what proves the packing rows belong to this lot."""
        s = self._src(env2=[{"LOTE": "9999999999", "FACTURA": "F2227",
                             "C_INICIAL": "  1", "C_FINAL": " 99"}])
        r = s.resolve_containers("0612185231", factura="F2227", qty_kg=150)
        assert r["source"] == "regenerated"

    def test_lote_variants_leading_zeros(self):
        from raven_ai_agent.skills.migration_fixer.sources import lote_variants
        assert "612185231" in lote_variants("0612185231")
        assert "0612185231" in lote_variants("612185231")


class TestBilingualAndHelp:
    def test_help_card(self, frappe_mock):
        r = _skill().handle("migrate help")
        body = r["response"]
        assert "census" in body.lower() and "censo" in body.lower()
        assert "Never" in body and "det_trazab" in body

    def test_ayuda_migracion(self, frappe_mock):
        r = _skill().handle("ayuda migración")
        assert r is not None and "migration-fixer v2" in r["response"]

    def test_every_own_v2_match_is_handled(self, frappe_mock):
        """Any phrase this skill claims at >=0.9 must be handled, never None."""
        with patch("raven_ai_agent.skills.migration_fixer.census.census_folio",
                   return_value=_census()), \
             patch("raven_ai_agent.skills.migration_fixer.census.census_section",
                   return_value={"year": 2024, "folios_censused": 0,
                                 "stage_matrix": {s: {"OK": 0, "PARTIAL": 0,
                                                      "MISSING": 0, "UNKNOWN": 0}
                                                  for s in __import__(
                                     "raven_ai_agent.skills.migration_fixer.census",
                                     fromlist=["STAGES"]).STAGES},
                                 "c_sources_lots": {}, "top_gap_patterns": [],
                                 "undated_folios": [], "details": []}), \
             patch("raven_ai_agent.skills.migration_fixer.executor.execute_stage",
                   return_value="x"), \
             patch("raven_ai_agent.skills.migration_fixer.sources.get_sources") as gs:
            gs.return_value.folios_for_year = MagicMock(return_value=[])
            gs.return_value.census_dir = "/x"
            s = _skill()
            for q in ["migrate scan folio 752", "migrate folio 752",
                      "migrate folio 752 stage so", "!migrate folio 752 stage batch",
                      "migrar folio 752", "migrate help", "migrate scan 2024"]:
                can, conf = s.can_handle(q)
                if can and conf >= 0.9:
                    assert s.handle(q) is not None, f"claimed but unhandled: {q!r}"
