"""
raven_ai_agent/patterns/tests/conftest.py
═══════════════════════════════════════════════════════════════════════════════
Pytest configuration + shared fixtures for the patterns test suite.

Provides a frappe stub so tests can run standalone (no Frappe site required).
Mirrors the pattern used by crm_agent/tests/run_smoke.py.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock


def _install_frappe_stub() -> MagicMock:
    """
    Install a MagicMock-backed `frappe` module into sys.modules.

    Returns the mock so tests can adjust its behaviour (`table_exists`,
    `get_value`, etc.) per test. Idempotent — installing twice returns
    the same mock.
    """
    if "frappe" in sys.modules and isinstance(sys.modules["frappe"], MagicMock):
        return sys.modules["frappe"]

    frappe_stub = MagicMock(name="frappe")
    frappe_stub.db.table_exists.return_value = False
    frappe_stub.db.get_value.return_value = None
    frappe_stub.session.user = "Administrator"
    frappe_stub.log_error = MagicMock()
    frappe_stub.get_doc = MagicMock(return_value=MagicMock(insert=MagicMock()))

    sys.modules["frappe"] = frappe_stub

    # `from frappe import _` style imports — make `_` an identity
    sys.modules["frappe"]._ = lambda s: s

    return frappe_stub


# Install on import so test modules can `from frappe import ...` at module level.
# This MUST run before any `from raven_ai_agent.patterns import ...` because
# guardrails.py does `import frappe` at module-load time.
_FRAPPE = _install_frappe_stub()


def reset_frappe_mock() -> MagicMock:
    """Reset all the mock's call records + reset behavior to defaults."""
    # Reload the reference in case a test replaced sys.modules['frappe']
    global _FRAPPE
    _FRAPPE = sys.modules.get("frappe")
    if _FRAPPE is None or not isinstance(_FRAPPE, MagicMock):
        _FRAPPE = _install_frappe_stub()
    _FRAPPE.reset_mock()
    _FRAPPE.db.table_exists.return_value = False
    _FRAPPE.db.table_exists.side_effect = None
    _FRAPPE.db.get_value.return_value = None
    _FRAPPE.db.get_value.side_effect = None
    _FRAPPE.session.user = "Administrator"
    _FRAPPE.log_error = MagicMock()
    _FRAPPE.get_doc = MagicMock(return_value=MagicMock(insert=MagicMock()))
    return _FRAPPE


# Ensure the `raven_ai_agent` package is importable as a namespace
# when tests run from inside the patterns/ directory tree
if "raven_ai_agent" not in sys.modules:
    raven_pkg = types.ModuleType("raven_ai_agent")
    raven_pkg.__path__ = []  # mark as namespace package
    sys.modules["raven_ai_agent"] = raven_pkg
