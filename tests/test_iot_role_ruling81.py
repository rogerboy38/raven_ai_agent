"""TASKS-344 ruling 81(4), zero-DB: the IoT sensor intake has its own narrow role; store_memory and the desk button
stay System Manager only. Each test fails if the matching change is reverted."""

import ast
import os
import unittest
from unittest import mock

import frappe

ROOT = os.path.join(os.path.dirname(__file__), "..", "raven_ai_agent")


def _first_gate(rel, name):
    tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf8").read())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant))]
    return ast.unparse(body[0])


class TestSensorIntakeRole(unittest.TestCase):
    def test_submit_sensor_reading_needs_the_narrow_role_not_system_manager(self):
        gate = _first_gate("raven_ai_agent/api.py", "submit_sensor_reading")
        self.assertIn("IoT Sensor Intake", gate)
        self.assertNotIn("System Manager", gate)

    def test_memory_tool_and_desk_button_stay_system_manager_only(self):
        self.assertIn("System Manager", _first_gate("api/raven_v2_functions.py", "store_memory"))
        self.assertIn("System Manager", _first_gate("raven_ai_agent/doctype/raven_agent_bug/raven_agent_bug.py", "acknowledge"))

    def test_the_patch_is_listed_and_is_idempotent(self):
        txt = open(os.path.join(ROOT, "patches.txt"), encoding="utf8").read()
        self.assertIn("raven_ai_agent.patches.v13_8.create_iot_sensor_intake_role", txt)
        from raven_ai_agent.patches.v13_8 import create_iot_sensor_intake_role as P

        fr = mock.MagicMock()
        fr.db.exists.return_value = False
        with mock.patch.object(P, "frappe", fr):
            P.execute()
            fr.get_doc.assert_called_once()
            doc = fr.get_doc.call_args.args[0]
            self.assertEqual(doc["role_name"], "IoT Sensor Intake")
            self.assertEqual(doc["desk_access"], 0)
        fr2 = mock.MagicMock()
        fr2.db.exists.return_value = True
        with mock.patch.object(P, "frappe", fr2):
            P.execute()
            fr2.get_doc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
