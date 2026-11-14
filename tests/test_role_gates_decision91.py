"""TASKS-349 decision 91, zero-DB: the 12 whitelisted functions that bypass the caller's permissions and the 5 BOM-creator
wrappers refuse any caller who is not System Manager (decision 76's rule and refusal: `frappe.only_for` first). One
exception: `submit_weight_reading` also accepts the IoT device role of decision 81. Each refusal test fails if the
`only_for` line of THAT function is removed. The stand-in for `frappe.only_for` below checks real role sets."""

import importlib
import inspect
import unittest
from unittest import mock

import frappe
import sys

SM = "System Manager"
IOT = "IoT Sensor Intake"

# (module, function)  -- the 17 of decision 91
SEVENTEEN = [
    ("raven_ai_agent.skills.crm_agent.tools.activities", "add_note"),
    ("raven_ai_agent.skills.crm_agent.tools.communications", "send_email"),
    ("raven_ai_agent.utils.bom_migration", "import_bom"),
    ("raven_ai_agent.api.bom_fixer", "api_check_and_fix_item"),
    ("raven_ai_agent.api.bom_fixer", "api_fix_multiple_items"),
    ("raven_ai_agent.api.tds_resolver", "api_create_work_order_from_tds"),
    ("raven_ai_agent.api.tds_resolver", "api_create_work_orders_from_so_with_tds"),
    ("raven_ai_agent.api.po_extractor", "manual_extract"),
    ("raven_ai_agent.api.weight_api", "submit_weight_reading"),
    ("raven_ai_agent.api.deploy", "deploy_raven"),
    ("raven_ai_agent.agents.bom_creator_agent", "create_bom_from_template"),
    ("raven_ai_agent.agents.bom_creator_agent", "create_bom_for_batch"),
    ("raven_ai_agent.agents.bom_creator_agent", "create_bom_from_tds"),
    ("raven_ai_agent.agents.bom_creator_agent", "validate_bom_creator"),
    ("raven_ai_agent.agents.bom_creator_agent", "submit_bom_creator"),
    ("raven_ai_agent.agents.bom_creator_agent", "handle_bom_request"),
    ("raven_ai_agent.api.raven_v2_functions", "submit_bom_creator"),
]
GATE = "ROLE-GATE"


def _only_for(roles_held):
    def only_for(roles, message=False):
        need = {roles} if isinstance(roles, str) else set(roles)
        if not need & set(roles_held):
            raise frappe.PermissionError(GATE)
    return only_for


def _args(fn):
    return [f"x{i}" for i, p in enumerate(inspect.signature(fn).parameters.values()) if p.default is inspect._empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]


def _fn(mod, name):
    fu = sys.modules.get("frappe.utils")
    if fu is not None and not hasattr(fu, "now"):   # the conftest stub of frappe.utils lacks it (weight_api imports it)
        fu.now = lambda: "2026-03-21 12:00:00"
    return getattr(importlib.import_module(mod), name)


def _call(mod, name, roles):
    fn = _fn(mod, name)
    args = _args(fn)
    if name == "submit_weight_reading":
        args = ["JAR1", 10.0, "SCALE-L01"]
    with mock.patch.object(frappe, "only_for", _only_for(roles), create=True):
        return fn(*args)


class TestOrdinaryUserIsRefused(unittest.TestCase):
    pass


def _make(mod, name):
    def refused(self):
        for roles in (["Sales User"], ["Stock User", "Quality User"], ["Manufacturing User", "Quality Manager"]):
            with self.assertRaises(frappe.PermissionError) as cm:
                _call(mod, name, roles)
            self.assertEqual(str(cm.exception), GATE, f"{mod}.{name}: refused by something other than the role gate")

    def allowed(self):
        try:
            _call(mod, name, [SM])
        except BaseException as e:   # the body may fail on the mock frappe: it only matters that the gate let it in
            self.assertNotEqual(str(e), GATE, f"{mod}.{name} refused System Manager")
    return refused, allowed


for _m, _n in SEVENTEEN:
    _r, _a = _make(_m, _n)
    setattr(TestOrdinaryUserIsRefused, f"test_{_m.split('.')[-1]}_{_n}_refuses_an_ordinary_user", _r)
    setattr(TestOrdinaryUserIsRefused, f"test_{_m.split('.')[-1]}_{_n}_lets_system_manager_in", _a)


class TestWeightReadingException(unittest.TestCase):
    def test_the_iot_role_passes_the_gate_but_the_device_list_still_applies(self):
        mod = "raven_ai_agent.api.weight_api"
        fn = _fn(mod, "submit_weight_reading")
        with mock.patch.object(frappe, "only_for", _only_for([IOT]), create=True):
            try:
                fn("JAR1", 10.0, "NOT-A-DEVICE")
            except BaseException as e:
                self.assertNotEqual(str(e), GATE)          # past the role gate...
            # ...and the hard-coded device list is still checked beside it (the call above did not succeed)
        self.assertIn("SCALE-L01", _fn(mod, "ALLOWED_DEVICES"))

    def test_stock_user_is_refused_by_the_role_gate_even_with_a_listed_device(self):
        with self.assertRaises(frappe.PermissionError) as cm:
            _call("raven_ai_agent.api.weight_api", "submit_weight_reading", ["Stock User"])
        self.assertEqual(str(cm.exception), GATE)

    def test_the_iot_role_does_not_open_any_other_function(self):
        for mod, name in SEVENTEEN:
            if name == "submit_weight_reading":
                continue
            with self.assertRaises(frappe.PermissionError) as cm:
                _call(mod, name, [IOT])
            self.assertEqual(str(cm.exception), GATE, f"{name}")


class TestAgentPathsAreNotBroken(unittest.TestCase):
    """The chat command and the Raven v2 function reach the BOM creator through the ungated implementations, so an
    ordinary user's chat command is not refused by the new gate (it runs under the guard, as before)."""

    def test_the_ungated_implementations_do_not_check_the_role(self):
        from raven_ai_agent.agents import bom_creator_agent as b

        agent = mock.MagicMock()
        agent.submit_bom_creator.return_value = {"success": True}
        agent.create_bom_for_batch.return_value = {"success": True}
        with mock.patch.object(frappe, "only_for", _only_for(["Sales User"]), create=True), mock.patch.object(b, "BOMCreatorAgent", return_value=agent):
            self.assertEqual(b._submit_bom_creator("BC-1"), {"success": True})
            self.assertEqual(b._create_bom_for_batch("LOTE-1"), {"success": True})

    def test_the_chat_command_and_the_v2_function_import_the_ungated_names(self):
        import os

        root = os.path.join(os.path.dirname(__file__), "..", "raven_ai_agent", "api")
        cr = open(os.path.join(root, "command_router.py"), encoding="utf8").read()
        v2 = open(os.path.join(root, "raven_v2_functions.py"), encoding="utf8").read()
        self.assertIn("import _submit_bom_creator as submit_bom_creator", cr)
        self.assertIn("import _create_bom_for_batch as create_bom_for_batch", cr)
        self.assertIn("import _submit_bom_creator as submit_func", v2)
        self.assertNotIn("import submit_bom_creator", cr + v2)
        self.assertNotIn("import create_bom_for_batch", cr)


class TestGateIsFirst(unittest.TestCase):
    def test_only_for_is_the_first_statement_after_the_docstring(self):
        import ast
        import textwrap

        for mod, name in SEVENTEEN:
            fn = _fn(mod, name)
            tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
            body = tree.body[0].body
            body = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant))]
            self.assertTrue(ast.unparse(body[0]).startswith("frappe.only_for("), f"{mod}.{name}: {ast.unparse(body[0])[:60]}")


if __name__ == "__main__":
    unittest.main()
