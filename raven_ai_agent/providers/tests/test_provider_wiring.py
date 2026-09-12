"""Tests for the 429 provider-wiring fix.

Run with (no Frappe runtime, no API keys, no network):
    cd ~/frappe-bench/apps/raven_ai_agent
    PYTHONPATH=. python3 raven_ai_agent/providers/tests/test_provider_wiring.py

Run the file directly, not via ``python -m`` -- providers/__init__.py has
side-effect imports that must happen AFTER the stubs install, which is the same
constraint test_secrets.py documents.
"""
from __future__ import annotations

import sys
import types
import unittest


# --- stubs first, before any provider import (see module docstring) ---
def _install_stubs():
    if "frappe" not in sys.modules:
        fake = types.ModuleType("frappe")
        fake.conf = {}
        fake.logger = lambda: types.SimpleNamespace(debug=lambda *a, **kw: None)
        fake.log_error = lambda *a, **kw: None
        pw = types.ModuleType("frappe.utils.password")
        pw.get_decrypted_password = lambda *a, **kw: None
        utils = types.ModuleType("frappe.utils")
        utils.password = pw
        fake.utils = utils
        sys.modules.update({"frappe": fake, "frappe.utils": utils,
                            "frappe.utils.password": pw})
    for opt in ("openai", "anthropic", "httpx"):
        if opt not in sys.modules:
            stub = types.ModuleType(opt)
            if opt == "openai":
                # a recognisable sentinel so tests can assert the OpenAI path
                stub.OpenAI = lambda **kw: types.SimpleNamespace(_openai=True, **kw)
            if opt == "anthropic":
                stub.Anthropic = lambda **kw: None
            sys.modules[opt] = stub


_install_stubs()

from raven_ai_agent.providers import get_provider                    # noqa: E402
from raven_ai_agent.providers.minimax import MiniMaxProvider         # noqa: E402
from raven_ai_agent.providers.openai_provider import OpenAIProvider  # noqa: E402


class TestProviderSelection(unittest.TestCase):
    """`default_provider` must decide the provider -- the bug was that nothing read it."""

    def test_openai_selected(self):
        p = get_provider("openai", {"openai_api_key": "sk-test"})
        self.assertIsInstance(p, OpenAIProvider)

    def test_minimax_selected(self):
        p = get_provider("minimax", {"minimax_api_key": "abc", "minimax_group_id": "1"})
        self.assertIsInstance(p, MiniMaxProvider)

    def test_selection_is_case_insensitive(self):
        # The doctype stores "MiniMax"/"OpenAI" with capitals; the factory keys
        # are lowercase. A case-sensitive lookup would silently raise and the
        # agent would fall back to OpenAI -- i.e. the original bug, again.
        self.assertIsInstance(get_provider("MiniMax", {"minimax_api_key": "a"}),
                              MiniMaxProvider)
        self.assertIsInstance(get_provider("OpenAI", {"openai_api_key": "sk-t"}),
                              OpenAIProvider)

    def test_unknown_provider_raises_and_names_the_options(self):
        with self.assertRaises(ValueError) as cm:
            get_provider("not-a-provider", {})
        self.assertIn("minimax", str(cm.exception))

    def test_unset_provider_is_not_silently_openai_at_the_factory(self):
        # The FALLBACK to OpenAI belongs to the caller, not the factory: a
        # factory that quietly returns OpenAI for "" is how a mis-set field
        # becomes an invisible OpenAI bill.
        with self.assertRaises((ValueError, AttributeError)):
            get_provider("", {"openai_api_key": "sk-test"})


class TestMiniMaxModelFallback(unittest.TestCase):
    """The key implies the model; a stale stored value must not outrank it."""

    def mm(self, **settings):
        settings.setdefault("minimax_group_id", "1")
        return MiniMaxProvider(settings)

    def test_coding_plan_key_chooses_m21(self):
        self.assertEqual(self.mm(minimax_api_key="sk-cp-abc123").default_model,
                         "MiniMax-M2.1")

    def test_regular_key_chooses_m2(self):
        self.assertEqual(self.mm(minimax_api_key="abc123").default_model,
                         "MiniMax-M2")

    def test_stale_stored_model_does_not_beat_the_cp_key(self):
        # This is the regression: the shipped Select options were
        # "abab6.5-chat/abab5.5-chat", so a saved value was guaranteed stale
        # and used to win.
        self.assertEqual(
            self.mm(minimax_api_key="sk-cp-abc", minimax_model="abab6.5-chat").default_model,
            "MiniMax-M2.1")

    def test_stale_stored_model_does_not_beat_a_regular_key(self):
        self.assertEqual(
            self.mm(minimax_api_key="abc", minimax_model="abab5.5-chat").default_model,
            "MiniMax-M2")

    def test_model_equals_default_model_on_construction(self):
        p = self.mm(minimax_api_key="sk-cp-x")
        self.assertEqual(p.model, p.default_model)


if __name__ == "__main__":
    unittest.main(verbosity=2)
