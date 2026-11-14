"""TASKS-342: the agent's kill switch (AI Agent Settings `enabled`) also covers the two scheduled jobs and the three
document hooks of the CRM agent. Zero-DB, by source structure (these modules need a real frappe to import): the
first statement of each door is `if not agent_enabled(): return`."""
import ast
import os
import unittest

BASE = os.path.join(os.path.dirname(__file__), "..", "raven_ai_agent", "skills", "crm_agent", "agents")
DOORS = {
    "opportunity_mover.py": ("scan_stalled_opportunities", "on_opportunity_update"),
    "pipeline_summarizer.py": ("run_daily_digest",),
    "lead_enricher.py": ("on_lead_after_insert",),
    "meeting_capturer.py": ("on_communication_after_insert",),
}


def _first_real_statements(fn):
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]                                  # docstring
    return body


class TestKillSwitchDoors(unittest.TestCase):
    def test_each_door_starts_with_the_kill_switch(self):
        for fname, fns in DOORS.items():
            tree = ast.parse(open(os.path.join(BASE, fname), encoding="utf8").read())
            funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
            for name in fns:
                body = _first_real_statements(funcs[name])
                self.assertIsInstance(body[0], ast.ImportFrom, f"{fname}:{name}")
                self.assertEqual(body[0].module, "raven_ai_agent.api.agent_guard")
                guard = body[1]
                self.assertIsInstance(guard, ast.If, f"{fname}:{name}")
                self.assertIn("agent_enabled", ast.unparse(guard.test))
                self.assertIsInstance(guard.body[0], ast.Return)


if __name__ == "__main__":
    unittest.main()
