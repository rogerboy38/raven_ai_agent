"""
Standalone smoke-test runner for crm_agent (no Frappe site required).

Usage from repo root:
    python raven_ai_agent/skills/crm_agent/tests/run_smoke.py

This script installs a `frappe` stub BEFORE any raven_ai_agent imports,
then runs the unit tests in test_intent_routing.
"""
from __future__ import annotations

import sys
import types
import os
import unittest


# ---------------------------------------------------------------------
# 1. Install a `frappe` stub before anything else imports it.
# ---------------------------------------------------------------------
def _install_frappe_stub():
    fake = types.ModuleType("frappe")

    def _noop(*args, **kwargs):
        return None

    fake.log_error = _noop
    fake.get_traceback = lambda: ""
    fake.as_json = lambda x: str(x)
    fake.session = types.SimpleNamespace(user="Administrator")
    fake.defaults = types.SimpleNamespace(get_user_default=lambda *_: None)
    fake.db = types.SimpleNamespace(
        get_single_value=lambda *_a, **_k: 1,
        exists=lambda *_a, **_k: True,
        get_value=lambda *_a, **_k: None,
        sql=lambda *_a, **_k: [],
        commit=_noop,
    )
    fake.get_all = lambda *_a, **_k: []
    fake.get_doc = lambda *_a, **_k: types.SimpleNamespace(
        name="STUB", insert=_noop, save=_noop, set=_noop, add_comment=_noop
    )
    fake.get_single = lambda *_a, **_k: types.SimpleNamespace(default_provider="OpenAI")
    fake.enqueue = _noop
    fake.sendmail = _noop

    def _whitelist(*_a, **_k):
        if _a and callable(_a[0]):
            return _a[0]
        return lambda fn: fn

    fake.whitelist = _whitelist
    fake.DoesNotExistError = type("DoesNotExistError", (Exception,), {})

    logger = types.SimpleNamespace(
        info=_noop, warning=_noop, error=_noop, debug=_noop
    )
    fake.logger = lambda *_a, **_k: logger
    sys.modules["frappe"] = fake


_install_frappe_stub()


# ---------------------------------------------------------------------
# 2. Stub the skills package framework so __init__ side-effects don't
#    pull in browser/Frappe-specific submodules during plain pytest runs.
# ---------------------------------------------------------------------
def _stub_framework():
    # Pre-register an empty raven_ai_agent.skills package that does NOT
    # eagerly import siblings like browser.py
    pkg_names = (
        "raven_ai_agent",
        "raven_ai_agent.skills",
    )
    for name in pkg_names:
        if name in sys.modules:
            continue
        mod = types.ModuleType(name)
        mod.__path__ = []  # mark as package
        sys.modules[name] = mod

    # Stub the framework module with a minimal SkillBase
    if "raven_ai_agent.skills.framework" in sys.modules:
        return
    fw = types.ModuleType("raven_ai_agent.skills.framework")

    class SkillBase:
        name = "base"
        description = "Base"
        emoji = "🔧"
        version = "0.0.0"
        triggers = []
        patterns = []
        priority = 50

        def __init__(self, agent=None):
            self.agent = agent
            self._usage_count = 0
            self._success_count = 0

        def handle(self, query, context=None):
            raise NotImplementedError

        def record_usage(self, success=True):
            self._usage_count += 1
            if success:
                self._success_count += 1

    fw.SkillBase = SkillBase
    sys.modules["raven_ai_agent.skills.framework"] = fw


_stub_framework()


# ---------------------------------------------------------------------
# 3. Add repo root to sys.path so `import raven_ai_agent.skills.crm_agent`
#    resolves to the on-disk package.
# ---------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Now set the on-disk crm_agent package as a child of our stubbed parent
import importlib
import importlib.util

crm_agent_init = os.path.join(REPO_ROOT, "raven_ai_agent", "skills",
                               "crm_agent", "__init__.py")
spec = importlib.util.spec_from_file_location(
    "raven_ai_agent.skills.crm_agent",
    crm_agent_init,
    submodule_search_locations=[os.path.dirname(crm_agent_init)],
)
crm_agent_pkg = importlib.util.module_from_spec(spec)
sys.modules["raven_ai_agent.skills.crm_agent"] = crm_agent_pkg
spec.loader.exec_module(crm_agent_pkg)


# ---------------------------------------------------------------------
# 4. Now load the test module and run.
# ---------------------------------------------------------------------
if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Original intent routing tests
    test_path = os.path.join(HERE, "test_intent_routing.py")
    spec = importlib.util.spec_from_file_location(
        "test_intent_routing_smoke", test_path
    )
    tmod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tmod)
    for cls_name in ("IntentRoutingTests", "SkillHandleTests", "ParsingTests"):
        cls = getattr(tmod, cls_name, None)
        if cls:
            suite.addTests(loader.loadTestsFromTestCase(cls))

    # New B/M/S/N cleanup tests
    cleanup_path = os.path.join(HERE, "test_cleanup_fixes.py")
    if os.path.exists(cleanup_path):
        cspec = importlib.util.spec_from_file_location(
            "test_cleanup_fixes_smoke", cleanup_path
        )
        cmod = importlib.util.module_from_spec(cspec)
        cspec.loader.exec_module(cmod)
        for cls_name in (
            "TestSkillNameKebabCase",
            "TestMeetingCapturerScalarFix",
            "TestParsingCurrencyAndNameFallback",
            "TestDealCoachWithoutPreposition",
            "TestStageMovePolitenessStrip",
            "TestAutonomyEnforcement",
            "TestAuditLogWrites",
            "TestHookEntrypoints",
            "TestMoveStageAliases",
            "TestBilingualIntents",
        ):
            cls = getattr(cmod, cls_name, None)
            if cls:
                suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
