"""
RAVEN-UX-001 regression tests — the four annotation fixes.

UX-01 is THE STING TEST (Hugh's bundle ruling): a no-quantity 0307 query can
never silently demand 307 kg against 39 on hand.

Zero-DB by construction (conftest mock frappe ModuleType; no site).
"""

import os
import unittest
from unittest.mock import MagicMock

APP_ROOT = os.path.join(os.path.dirname(__file__), "..", "raven_ai_agent")


def _read(rel):
    with open(os.path.join(APP_ROOT, rel)) as f:
        return f.read()


class _row(dict):
    __getattr__ = dict.get


def _parse(query, item_exists=True):
    """Run the real _parse_request with a mocked frappe."""
    import frappe
    frappe.db = MagicMock()
    frappe.db.exists = MagicMock(return_value=item_exists)
    frappe.log_error = MagicMock()
    from raven_ai_agent.skills.formulation_orchestrator.skill import (
        FormulationOrchestratorSkill,
    )
    sk = FormulationOrchestratorSkill.__new__(FormulationOrchestratorSkill)
    return sk._parse_request(query, {})


class TestPhantomQtySting(unittest.TestCase):
    """Fix 1: the unit suffix is required; product digits are never a quantity."""

    def test_ux_01_sting_no_qty_0307_never_demands_307(self):
        """STING: 'run formulation of product 0307' -> NO quantity_required.
        The selection math can therefore never see a phantom 307 vs 39 on hand."""
        req = _parse("run formulation of product 0307")
        self.assertIsNotNone(req)
        self.assertNotIn("quantity_required", req)
        self.assertEqual(req["product_code"], "0307")

    def test_ux_02_explicit_qty_still_parses(self):
        req = _parse("run formulation of 500 kg product 0307")
        self.assertEqual(req["quantity_required"], 500.0)
        self.assertEqual(req["product_code"], "0307")

    def test_ux_03_unit_forms_and_bare_numbers(self):
        self.assertEqual(_parse("formulate 1404 units of product 0616")["quantity_required"], 1404.0)
        self.assertEqual(_parse("formulacion de 25 kilos product 0301")["quantity_required"], 25.0)
        self.assertNotIn("quantity_required", _parse("run formulation of 500 product 0616"))

    def test_ux_04_phantom_0616_dead(self):
        """The exact live repro: 'product 0616' must not become Quantity 616."""
        req = _parse("run formulation of product 0616")
        self.assertNotIn("quantity_required", req)


class TestItemResolution(unittest.TestCase):
    """Fix 2: bare product codes resolve to their Item for the report line."""

    def test_ux_05_product_resolves_to_item(self):
        req = _parse("run formulation of 500 kg product 0307", item_exists=True)
        self.assertEqual(req["item_code"], "0307")

    def test_ux_06_nonexistent_item_stays_unresolved(self):
        req = _parse("run formulation of 500 kg product 9999", item_exists=False)
        self.assertNotIn("item_code", req)
        self.assertEqual(req["product_code"], "9999")

    def test_ux_07_golden_item_code_still_wins(self):
        req = _parse("run formulation of 500 kg ITEM_0616075231 product 0616")
        self.assertEqual(req["item_code"], "ITEM_0616075231")


class TestSelectOptimalTwin(unittest.TestCase):
    """Fix 3: _select_optimal falls back to payload product_code (AB-001 twin)."""

    def test_ux_08_payload_product_code_drives_optimal(self):
        from unittest.mock import patch
        with patch("raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe"), \
             patch("raven_ai_agent.skills.formulation_orchestrator.agents.batch_selector.parse_golden_number") as mock_parse, \
             patch("raven_ai_agent.skills.formulation_orchestrator.agents.batch_selector.get_available_batches") as mock_get:
            mock_parse.return_value = None
            mock_get.return_value = []
            from raven_ai_agent.skills.formulation_orchestrator.agents import BatchSelectorAgent
            from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage
            agent = BatchSelectorAgent()
            msg = AgentMessage(source_agent="orchestrator", target_agent="batch_selector",
                               action="select_optimal",
                               payload={"item_code": None, "product_code": "0307"})
            agent.handle_message(msg)
            self.assertEqual(mock_get.call_args.args[0], "0307")


class TestMigrationFixerPartyName(unittest.TestCase):
    """Fix 4 (F-CER-1): Quotation has no customer column; reads use party_name."""

    def test_ux_09_no_customer_in_quotation_field_lists(self):
        src = _read("skills/migration_fixer/fixer.py")
        self.assertNotIn('"customer", "transaction_date", "grand_total", "status", \n'
                         '                   "custom_invoice_folio"', src,
                         "Quotation get_all still selects the phantom customer column")
        self.assertEqual(src.count('"party_name", "transaction_date"'), 2,
                         "both Quotation field lists should use party_name")

    def test_ux_10_no_quotation_customer_attr_reads(self):
        for rel in ("skills/migration_fixer/fixer.py", "skills/migration_fixer/api.py"):
            self.assertNotIn("quotation.customer", _read(rel),
                             f"{rel}: quotation.customer attr read survives")

    def test_ux_11_sales_order_customer_untouched(self):
        src = _read("skills/migration_fixer/fixer.py")
        self.assertIn('fields=["name", "customer", "transaction_date", "grand_total", "status"]',
                      src, "the Sales Order field list must keep customer")

    def test_ux_12_fix_plan_targets_party_name(self):
        src = _read("skills/migration_fixer/fixer.py")
        self.assertIn('"field": "party_name"', src)


if __name__ == "__main__":
    unittest.main()
