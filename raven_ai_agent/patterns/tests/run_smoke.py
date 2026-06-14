"""
raven_ai_agent/patterns/tests/run_smoke.py
═══════════════════════════════════════════════════════════════════════════════
Standalone smoke runner — no pytest, no Frappe site required.

Run with:
    cd apps/raven_ai_agent && python raven_ai_agent/patterns/tests/run_smoke.py

Mirrors the runner pattern from skills/crm_agent/tests/run_smoke.py so CI
can sanity-check the patterns module without a full bench environment.
"""
from __future__ import annotations

import os
import sys
import traceback

# Ensure the package root is on sys.path so `from raven_ai_agent...` works
# when this script is executed directly (no installed app context).
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", ".."))
if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

# CRITICAL: install the frappe stub BEFORE any raven_ai_agent.patterns import.
# guardrails.py does `import frappe` at module load, so the stub must be in
# sys.modules first or the import will fail with ModuleNotFoundError.
import types
from unittest.mock import MagicMock

_frappe_stub = MagicMock(name="frappe")
_frappe_stub.db.table_exists.return_value = False
_frappe_stub.db.get_value.return_value = None
_frappe_stub.session.user = "Administrator"
_frappe_stub._ = lambda s: s
sys.modules["frappe"] = _frappe_stub

# Now safe to import
from raven_ai_agent.patterns.tests.conftest import reset_frappe_mock


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def _run_module(module_name: str) -> tuple[int, int]:
    """Import a test module and run all test_* methods on all Test* classes."""
    print(f"\n── {module_name} ──")
    reset_frappe_mock()

    mod = __import__(module_name, fromlist=["*"])
    passed = failed = 0

    for attr_name in dir(mod):
        cls = getattr(mod, attr_name)
        if not (isinstance(cls, type) and attr_name.startswith("Test")):
            continue
        for method_name in dir(cls):
            if not method_name.startswith("test_"):
                continue
            instance = cls()
            if hasattr(instance, "setup_method"):
                try:
                    instance.setup_method()
                except Exception:
                    pass
            try:
                getattr(instance, method_name)()
                print(f"  {_green('✓')} {attr_name}.{method_name}")
                passed += 1
            except Exception:
                print(f"  {_red('✗')} {attr_name}.{method_name}")
                print(traceback.format_exc())
                failed += 1
    return passed, failed


def main() -> int:
    total_pass = total_fail = 0
    for mod in [
        "raven_ai_agent.patterns.tests.test_guardrails",
        "raven_ai_agent.patterns.tests.test_planner",
    ]:
        p, f = _run_module(mod)
        total_pass += p
        total_fail += f

    print(
        f"\n══════════════════════════════════════════════════════\n"
        f"  {_green(str(total_pass) + ' passed')}, "
        f"{_red(str(total_fail) + ' failed') if total_fail else '0 failed'}\n"
        f"══════════════════════════════════════════════════════"
    )
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
