"""Agent-level proof that `default_provider` is honoured on the mention path.

Needs a Frappe site (it imports the agent, which pulls the mixin stack):
    cd ~/frappe-bench
    env/bin/python -c "import sys; sys.path.insert(0,'<worktree>'); \
        import frappe; frappe.init(site='<site>'); frappe.connect(); \
        import unittest, raven_ai_agent.providers.tests.test_agent_provider_selection as t; \
        unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(t))"

`_get_settings` is patched per case: the point is the SELECTION, and binding the
test to the doctype would make it a settings-loader test instead. No network --
no provider's chat() is called.
"""
from __future__ import annotations

import unittest

import frappe

from raven_ai_agent.api.agent import RaymondLucyAgent
from raven_ai_agent.providers.minimax import MiniMaxProvider
from raven_ai_agent.providers.openai_provider import OpenAIProvider


class TestAgentProviderSelection(unittest.TestCase):
    def setUp(self):
        self._orig = RaymondLucyAgent._get_settings

    def tearDown(self):
        RaymondLucyAgent._get_settings = self._orig

    def agent_with(self, settings):
        RaymondLucyAgent._get_settings = lambda self, _s=settings: _s
        return RaymondLucyAgent("Administrator")

    def test_minimax_is_selected_when_default_provider_says_so(self):
        a = self.agent_with({"default_provider": "MiniMax",
                             "minimax_api_key": "sk-cp-abc", "minimax_group_id": "1"})
        self.assertIsInstance(a.provider, MiniMaxProvider)
        # and the key-derived model, not a stored one
        self.assertEqual(a.provider.default_model, "MiniMax-M2.1")

    def test_openai_is_selected_when_named(self):
        a = self.agent_with({"default_provider": "OpenAI", "openai_api_key": "sk-test"})
        self.assertIsInstance(a.provider, OpenAIProvider)

    def test_unset_provider_falls_back_to_openai(self):
        # Explicitly asserted: the fallback is deliberate, not incidental.
        a = self.agent_with({"openai_api_key": "sk-test"})
        self.assertIsInstance(a.provider, OpenAIProvider)

    def test_no_provider_and_no_key_yields_no_provider(self):
        # Must be None rather than a half-built client, so the mention path
        # returns "not configured" instead of raising on a None attribute.
        a = self.agent_with({})
        self.assertIsNone(a.provider)
        self.assertIsNone(a.client)

    def test_minimax_selection_does_not_require_an_openai_key(self):
        # The original loader returned {} unless an OpenAI key existed, which is
        # why a MiniMax-only site could not be configured at all.
        a = self.agent_with({"default_provider": "MiniMax",
                             "minimax_api_key": "abc", "minimax_group_id": "1"})
        self.assertIsInstance(a.provider, MiniMaxProvider)

    def test_openai_model_setting_does_not_override_a_non_openai_provider(self):
        """Blocker 3. `model` is the OpenAI model name; every provider's chat()
        does `model = model or self.default_model`, so passing it through made
        an OpenAI name beat the provider's own default -- MiniMax was being
        asked for "gpt-4o-mini". Both directions are asserted: suppressed for
        MiniMax, still honoured for OpenAI."""
        mm = self.agent_with({"default_provider": "MiniMax", "minimax_api_key": "sk-cp-abc",
                              "minimax_group_id": "1", "model": "gpt-4o-mini"})
        self.assertIsNone(mm.model, "an OpenAI model name must not reach MiniMax")
        self.assertEqual(mm.provider.default_model, "MiniMax-M2.1")

        oa = self.agent_with({"default_provider": "OpenAI", "openai_api_key": "sk-test",
                              "model": "gpt-4o"})
        self.assertEqual(oa.model, "gpt-4o", "OpenAI must still receive its configured model")


class TestSettingsSurviveAnUndecryptableSecret(unittest.TestCase):
    """Blocker 1: one undecryptable ciphertext must not hide default_provider.

    This is the regression Node A found on VPT by surgical intervention --
    repairing decryption for `openai_api_key` alone moved the settings dict from
    4 keys to 15 with default_provider='MiniMax'. Here the failure is injected
    instead of repaired, which is the same experiment run from the other end.
    """

    class _Stub:
        """An AI Agent Settings whose secrets all fail to decrypt."""
        model = "gpt-4o-mini"
        max_tokens = 2000
        confidence_threshold = 0.7

        def __init__(self, provider):
            self._provider = provider

        def get_password(self, fieldname):
            raise Exception("Failed to decrypt key AI Agent Settings." + fieldname)

        def get(self, fieldname, default=None):
            return {"default_provider": self._provider}.get(fieldname, default)

    def setUp(self):
        self._orig = frappe.get_single

    def tearDown(self):
        frappe.get_single = self._orig

    def settings_with(self, provider):
        # Stub EVERY source, not just Try 1. Without this the "nothing usable"
        # case falls through to Try 2 (Raven Settings) and Try 3 (site_config)
        # and picks up whatever real credential the host happens to hold -- the
        # test then asserts against live secrets, which is both a false failure
        # and a way to print a production key into a log.
        frappe.get_single = lambda dt, _p=provider: self._Stub(_p)
        self._orig_conf = frappe.conf
        frappe.conf = {}
        try:
            return RaymondLucyAgent._get_settings(
                RaymondLucyAgent.__new__(RaymondLucyAgent))
        finally:
            frappe.conf = self._orig_conf

    def test_default_provider_survives_an_undecryptable_openai_key(self):
        out = self.settings_with("MiniMax")
        self.assertEqual(out.get("default_provider"), "MiniMax",
                         "a failed secret read must not hide the plain field beside it")
        self.assertIsNone(out.get("openai_api_key"))

    def test_dict_is_not_the_four_key_fallback_shape(self):
        # The observable symptom was the dict's SHAPE: 4 keys and no provider.
        out = self.settings_with("MiniMax")
        self.assertGreater(len(out), 4, f"fell back to the degraded shape: {sorted(out)}")

    def test_no_provider_and_no_readable_secret_still_yields_nothing_usable(self):
        # Both directions: the guard must not invent a configuration either.
        out = self.settings_with("")
        self.assertFalse(out.get("default_provider"))
        self.assertIsNone(out.get("openai_api_key"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
