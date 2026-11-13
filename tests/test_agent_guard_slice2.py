"""TASKS-339 slice 2, zero-DB: regression locks on the chat code (no direct submit/cancel, no raw-SQL writes outside the
named exceptions), the kill switch, the workflow-aware submit helper's choice of step, and the endpoint decorator's
text rules. The DB-backed scenarios run on a scratch site (see the design letter)."""

import ast
import os
import re
import unittest
from types import SimpleNamespace as NS
from unittest import mock

from raven_ai_agent.api import agent_guard as g

ROOT = os.path.join(os.path.dirname(__file__), "..", "raven_ai_agent")
# raw-SQL writers that are NOT reachable from chat and are left as they are (named in the design letter):
# the patch is a one-time migration; the two whitelisted account/BOM utilities are called by no chat path.
RAW_SQL_ALLOWED = {"patches/v0_2/register_crm_agent.py", "api/bom_fixer.py", "api/account_utils.py"}


def _py_files():
    for dp, _dn, fn in os.walk(ROOT):
        if "/tests" in dp.replace("\\", "/") or "__pycache__" in dp:
            continue
        for f in fn:
            if f.endswith(".py"):
                yield os.path.join(dp, f)


class TestChatCodeLocks(unittest.TestCase):
    def test_no_direct_submit_or_cancel_calls_remain(self):
        bad = []
        for p in _py_files():
            for n in ast.walk(ast.parse(open(p, encoding="utf8").read())):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr in ("submit", "cancel") and not n.args and not n.keywords):
                    bad.append(f"{os.path.relpath(p, ROOT)}:{n.lineno}")
        self.assertEqual(bad, [])

    def test_raw_sql_writes_only_where_named(self):
        bad = []
        for p in _py_files():
            rel = os.path.relpath(p, ROOT).replace("\\", "/")
            if rel in RAW_SQL_ALLOWED:
                continue
            for n in ast.walk(ast.parse(open(p, encoding="utf8").read())):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "sql"
                        and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
                        and re.match(r"\s*(update|delete|insert|replace)\b", n.args[0].value, re.I)):
                    bad.append(f"{rel}:{n.lineno}")
        self.assertEqual(bad, [])

    def test_the_two_role_test_copies_are_gone(self):
        for rel in ("api/command_router.py", "api/handlers/base.py"):
            self.assertNotIn("privileged_roles", open(os.path.join(ROOT, rel), encoding="utf8").read(), rel)

    def test_create_batch_command_only_refuses(self):
        src = open(os.path.join(ROOT, "agents/manufacturing_agent.py"), encoding="utf8").read()
        i = src.index('if "create batch" in message_lower:')
        self.assertIn("does not create batches", src[i:i + 300])


class TestKillSwitch(unittest.TestCase):
    def _enabled(self, **vals):
        fr = mock.MagicMock()
        fr.db.get_single_value.side_effect = lambda dt, f: vals.get(f)
        with mock.patch.object(g, "frappe", fr):
            return g.agent_enabled(raven=True)

    def test_unset_is_on(self):
        self.assertTrue(self._enabled())

    def test_one_is_on(self):
        self.assertTrue(self._enabled(enabled="1", raven_enabled=1))

    def test_either_zero_is_off(self):
        self.assertFalse(self._enabled(enabled="0", raven_enabled="1"))
        self.assertFalse(self._enabled(enabled="1", raven_enabled=0))

    def test_endpoint_switch_ignores_raven_enabled(self):
        fr = mock.MagicMock()
        fr.db.get_single_value.side_effect = lambda dt, f: {"enabled": 1, "raven_enabled": 0}.get(f)
        with mock.patch.object(g, "frappe", fr):
            self.assertTrue(g.agent_enabled())


class TestMoveDocChoosesTheStep(unittest.TestCase):
    """_move_doc: the transition that leaves the current state for a state of the wanted docstatus and is allowed
    to the author; refuse (never bypass) otherwise."""

    def wf(self):
        return NS(workflow_state_field="workflow_state",
            states=[NS(state="Draft", doc_status="0"), NS(state="Approved", doc_status="1"), NS(state="Cancelled", doc_status="2")],
            transitions=[NS(state="Draft", action="Approve", next_state="Approved", allowed="Operador"),
                         NS(state="Approved", action="Cancel", next_state="Cancelled", allowed="Nadie")])

    def run_move(self, roles, target=1, state="Draft", counts=None):
        doc = NS(doctype="T", workflow_state=state, submit=mock.Mock(), cancel=mock.Mock(),
            get=lambda k: state)
        fr = mock.MagicMock()
        fr.db.count.side_effect = lambda *a, **k: (counts or {}).get(a[1]["role"], 1)
        fr.throw.side_effect = lambda msg, exc=Exception: (_ for _ in ()).throw(exc(msg))
        fr.get_roles.return_value = roles
        import sys, types
        wfmod = types.ModuleType("frappe.model.workflow")
        class _Perm(Exception): ...
        wfmod.WorkflowPermissionError = _Perm
        wfmod.WorkflowTransitionError = Exception
        with mock.patch.object(g, "frappe", fr), \
             mock.patch.object(g, "_state", return_value={"mode": "armed", "user": "u", "blocked": None}), \
             mock.patch.object(g, "_active_workflow", return_value=self.wf()), \
             mock.patch.object(g, "apply_workflow_action") as aw, \
             mock.patch.dict(sys.modules, {"frappe.model.workflow": wfmod}):
            try:
                g._move_doc(doc, target)
                return "ok", aw, doc
            except _Perm as e:
                return str(e), aw, doc

    def test_holder_applies_the_action_once_and_never_calls_submit(self):
        res, aw, doc = self.run_move(["Operador"])
        self.assertEqual(res, "ok")
        aw.assert_called_once()
        self.assertEqual(aw.call_args.args[1], "Approve")
        doc.submit.assert_not_called()

    def test_non_holder_is_refused_naming_the_role(self):
        res, aw, doc = self.run_move(["Otro"])
        self.assertIn("Operador", res)
        aw.assert_not_called()
        doc.submit.assert_not_called()

    def test_role_with_no_users_is_reported(self):
        res, aw, _ = self.run_move(["Otro"], target=2, state="Approved", counts={"Nadie": 0})
        self.assertIn("nobody holds: Nadie", res)
        aw.assert_not_called()

    def test_no_single_step_is_refused(self):
        res, aw, _ = self.run_move(["Operador"], target=2, state="Draft")
        self.assertIn("does not walk a workflow", res)
        aw.assert_not_called()

    def test_outside_a_turn_it_is_the_plain_call(self):
        doc = NS(doctype="T", submit=mock.Mock(), cancel=mock.Mock())
        with mock.patch.object(g, "_state", return_value=None):
            g.submit_doc(doc)
            g.cancel_doc(doc)
        doc.submit.assert_called_once()
        doc.cancel.assert_called_once()


if __name__ == "__main__":
    unittest.main()
