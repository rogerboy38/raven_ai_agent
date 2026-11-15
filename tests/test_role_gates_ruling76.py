"""TASKS-342 ruling 76, zero-DB: the ten whitelisted functions that write with an ignore flag (or raw SQL) for any
logged-in account are System Manager only. Each test fails if the `frappe.only_for` line is removed."""

import ast
import os
import unittest
from unittest import mock

import frappe

ROOT = os.path.join(os.path.dirname(__file__), "..", "raven_ai_agent")

TEN = [
    ("api/bom_fixer.py", "api_force_fix_bom"),
    ("api/account_utils.py", "fix_invoice_debit_to"),
    ("api/bom_helpers.py", "validate_and_fix_bom"),
    ("api/bom_helpers.py", "create_work_order_from_bom"),
    ("api/po_extractor.py", "extract_po_from_attachment"),
    ("api/raven_v2_functions.py", "store_memory"),
    ("api/sales_invoice_upload.py", "upload_pedimento"),
    ("api/sales_order_upload.py", "upload_customer_po"),
    ("raven_ai_agent/api.py", "submit_sensor_reading"),
    ("raven_ai_agent/doctype/raven_agent_bug/raven_agent_bug.py", "acknowledge"),
]


# ruling 81(4): the IoT sensor intake has its own narrow role instead of System Manager
ROLE_OF = {"submit_sensor_reading": "IoT Sensor Intake"}


def _func(rel, name):
    tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf8").read())
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


class TestGateIsTheFirstStatement(unittest.TestCase):
    def test_each_of_the_ten_calls_only_for_before_anything_else(self):
        for rel, name in TEN:
            fn = _func(rel, name)
            body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant))]
            first_calls = [ast.unparse(s) for s in body[:3]]
            self.assertTrue(
                any(c.startswith("frappe.only_for(") and ROLE_OF.get(name, "System Manager") in c for c in first_calls),
                f"{rel}:{name} does not gate on {ROLE_OF.get(name, 'System Manager')} first: {first_calls}",
            )
            self.assertTrue(any("whitelist" in ast.unparse(d) for d in fn.decorator_list), f"{name} is not whitelisted")


class TestBehaviour(unittest.TestCase):
    def _deny(self):
        return mock.patch.object(frappe, "only_for", side_effect=frappe.PermissionError("System Manager"), create=True)

    def test_whitelisted_wrappers_refuse_and_do_not_reach_the_implementation(self):
        from raven_ai_agent.api import bom_helpers, po_extractor

        with self._deny():
            with mock.patch.object(bom_helpers, "_validate_and_fix_bom") as impl1:
                with self.assertRaises(frappe.PermissionError):
                    bom_helpers.validate_and_fix_bom("BOM-1")
                impl1.assert_not_called()
            with mock.patch.object(bom_helpers, "_create_work_order_from_bom") as impl2:
                with self.assertRaises(frappe.PermissionError):
                    bom_helpers.create_work_order_from_bom("BOM-1", 1)
                impl2.assert_not_called()
            with mock.patch.object(po_extractor, "_extract_po_from_attachment") as impl3:
                with self.assertRaises(frappe.PermissionError):
                    po_extractor.extract_po_from_attachment("F", "SO")
                impl3.assert_not_called()

    def test_internal_callers_use_the_ungated_implementation(self):
        from raven_ai_agent.api import bom_helpers, po_extractor

        self.assertTrue(callable(bom_helpers._validate_and_fix_bom))
        self.assertTrue(callable(bom_helpers._create_work_order_from_bom))
        self.assertTrue(callable(po_extractor._extract_po_from_attachment))
        # the doc-event / button enqueue and the task validator must not name the gated door
        src = open(os.path.join(ROOT, "api/po_extractor.py"), encoding="utf8").read()
        self.assertNotIn('po_extractor.extract_po_from_attachment"', src)
        self.assertEqual(src.count("po_extractor._extract_po_from_attachment"), 2)
        tv = open(os.path.join(ROOT, "agents/task_validator.py"), encoding="utf8").read()
        self.assertNotIn("import validate_and_fix_bom\n", tv)
        self.assertEqual(tv.count("_validate_and_fix_bom as validate_and_fix_bom"), 2)

    def test_api_wrappers_in_workflows_reach_the_gate(self):
        src = open(os.path.join(ROOT, "api/workflows.py"), encoding="utf8").read()
        self.assertIn("return json.dumps(validate_and_fix_bom(bom_name, auto_fix))", src)   # the gated public name
        self.assertIn("return json.dumps(create_work_order_from_bom(bom_name, quantity))", src)


if __name__ == "__main__":
    unittest.main()
