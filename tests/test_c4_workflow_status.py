"""
RAVEN-C4-001 regression tests — get_workflow_status, the ghost import, and the
bare-"track" trigger de-fang (vm3 PATCHSPEC 5265d93f).

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
    """frappe._dict lookalike: attribute access via dict.get."""
    __getattr__ = dict.get


class TestGetWorkflowStatus(unittest.TestCase):
    """C4-A: the method exists and walks Quotation -> SO -> WO/DN -> SI."""

    def _executor(self, get_all_map, get_value_map):
        import frappe
        frappe.session = MagicMock(user="Administrator")
        frappe.local = MagicMock(site="test")
        frappe.log_error = MagicMock()

        def get_all(doctype, *args, **kwargs):
            return get_all_map.get(doctype, [])

        def get_value(doctype, name, fieldname, *args, **kwargs):
            return get_value_map.get((doctype, name))

        frappe.get_all = MagicMock(side_effect=get_all)
        frappe.db = MagicMock()
        frappe.db.get_value = MagicMock(side_effect=get_value)
        from raven_ai_agent.api.workflows import WorkflowExecutor
        return WorkflowExecutor(user="Administrator")

    def test_c4_01_method_exists(self):
        """C4-01: the AttributeError crash class is dead."""
        ex = self._executor({}, {})
        self.assertTrue(hasattr(ex, "get_workflow_status"))

    def test_c4_02_full_chain_from_so(self):
        """C4-02: SO walk emits Quotation, SO, WO, DN, SI stages with a summary."""
        get_all_map = {
            "Sales Order Item": [_row(prevdoc_docname="SAL-QTN-2026-00001")],
            "Work Order": [_row(name="MFG-WO-01", status="In Process")],
            "Delivery Note Item": [_row(parent="MAT-DN-01")],
            "Sales Invoice Item": [_row(parent="ACC-SINV-01")],
        }
        get_value_map = {
            ("Quotation", "SAL-QTN-2026-00001"): "Ordered",
            ("Sales Order", "SO-TEST"): _row(name="SO-TEST", status="To Deliver",
                                             customer="ACME", grand_total=100.0),
            ("Delivery Note", "MAT-DN-01"): "To Bill",
            ("Sales Invoice", "ACC-SINV-01"): "Unpaid",
        }
        ex = self._executor(get_all_map, get_value_map)
        out = ex.get_workflow_status(so_name="SO-TEST")
        self.assertTrue(out["success"])
        stages = [s["stage"] for s in out["stages"]]
        self.assertEqual(stages, ["Quotation", "Sales Order", "Work Order",
                                  "Delivery Note", "Sales Invoice"])
        self.assertIn("SO-TEST", out["message"])

    def test_c4_03_no_so_found(self):
        """C4-03: unresolvable quotation returns success=False, no crash."""
        ex = self._executor({}, {})
        out = ex.get_workflow_status(quotation_name="SAL-QTN-NONE")
        self.assertFalse(out["success"])
        self.assertIn("No Sales Order found", out["message"])


class TestGhostImportPin(unittest.TestCase):
    """C4-B: queue_handlers must import WorkflowExecutor from api.workflows."""

    def test_c4_04_no_ghost_module(self):
        src = _read("api/queue_handlers.py")
        self.assertNotIn("api.workflow_executor import", src)
        self.assertIn("from raven_ai_agent.api.workflows import WorkflowExecutor", src)


class TestTrackDefangPins(unittest.TestCase):
    """C4-C: the bare "track" substring must not route to workflow-status."""

    def _assert_defanged(self, rel):
        src = _read(rel)
        self.assertNotIn('or "track" in query_lower', src,
                         f"{rel}: bare 'track' trigger is back")
        self.assertIn('"track order" in query_lower', src)
        self.assertIn('"track workflow" in query_lower', src)

    def test_c4_05_command_router_defanged(self):
        self._assert_defanged("api/command_router.py")

    def test_c4_06_handlers_base_defanged(self):
        self._assert_defanged("api/handlers/base.py")


if __name__ == "__main__":
    unittest.main()
