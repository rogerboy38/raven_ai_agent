"""TASKS-344 ruling 79, zero-DB, no network: the MiniMax model is a real setting with a working default, a retired
name is never sent, and a fallback provider is tried once when the primary fails (stubs only)."""
import json
import os
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..", "raven_ai_agent")


def load():
    """conftest drops every raven_ai_agent module before each test: import fresh, per test."""
    from raven_ai_agent import providers
    from raven_ai_agent.providers import minimax as mm

    mm.frappe.logger = mock.MagicMock()          # the mocked frappe has no logger
    return providers, mm


def make_minimax(settings):
    providers, mm = load()
    with mock.patch.object(mm, "resolve_secret", return_value=settings.get("minimax_api_key", "k")):
        return mm.MiniMaxProvider(settings)


class FakeHttp:
    """httpx.Client stand-in: records the payload, never opens a socket."""

    sent = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None):
        FakeHttp.sent.append(json)
        r = mock.MagicMock()
        r.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        return r


class TestModelIsASetting(unittest.TestCase):
    def setUp(self):
        self.providers, self.mm = load()

    def test_the_stored_setting_is_the_model_used(self):
        self.assertEqual(make_minimax({"minimax_model": "MiniMax-M2-Stable"}).default_model, "MiniMax-M2-Stable")
        self.assertEqual(make_minimax({"minimax_model": "some-new-name"}).default_model, "some-new-name")

    def test_changing_the_setting_changes_what_is_sent(self):
        FakeHttp.sent.clear()
        with mock.patch.object(self.mm.httpx, "Client", FakeHttp):
            make_minimax({"minimax_model": "name-a"}).chat([{"role": "user", "content": "hi"}])
            make_minimax({"minimax_model": "name-b"}).chat([{"role": "user", "content": "hi"}])
        self.assertEqual([p["model"] for p in FakeHttp.sent], ["name-a", "name-b"])

    def test_a_coding_plan_key_no_longer_chooses_the_model(self):
        p = make_minimax({"minimax_api_key": "sk-cp-whatever", "minimax_model": ""})
        self.assertEqual(p.default_model, self.mm.MiniMaxProvider.DEFAULT_MODEL)
        self.assertNotIn(p.default_model.lower(), self.mm.MiniMaxProvider.RETIRED_MODELS)
        p2 = make_minimax({"minimax_api_key": "sk-cp-whatever", "minimax_model": "MiniMax-M2-Stable"})
        self.assertEqual(p2.default_model, "MiniMax-M2-Stable")

    def test_empty_setting_gives_the_working_default_and_it_is_not_retired(self):
        d = make_minimax({}).default_model
        self.assertEqual(d, "MiniMax-M2")
        self.assertIn(d, self.mm.MiniMaxProvider.MODELS)
        self.assertNotIn(d.lower(), self.mm.MiniMaxProvider.RETIRED_MODELS)

    def test_a_retired_stored_value_is_never_sent(self):
        for stored in ("MiniMax-M2.1", "minimax-m2.1", " MiniMax-M2.1 ", "abab6.5-chat"):
            self.assertEqual(make_minimax({"minimax_model": stored}).default_model, "MiniMax-M2", stored)
        FakeHttp.sent.clear()
        with mock.patch.object(self.mm.httpx, "Client", FakeHttp):
            make_minimax({"minimax_model": "MiniMax-M2.1"}).chat([{"role": "user", "content": "hi"}])
        self.assertEqual(FakeHttp.sent[-1]["model"], "MiniMax-M2")

    def test_setting_beats_constructor_argument_beats_default(self):
        self.assertEqual(self.mm.MiniMaxProvider.resolve_model({"minimax_model": "s"}, "c"), "s")
        self.assertEqual(self.mm.MiniMaxProvider.resolve_model({}, "c"), "c")
        self.assertEqual(self.mm.MiniMaxProvider.resolve_model({}, "MiniMax-M2.1"), "MiniMax-M2")

    def test_the_settings_field_is_a_free_text_field_with_a_working_default(self):
        d = json.load(open(os.path.join(ROOT, "raven_ai_agent", "doctype", "ai_agent_settings", "ai_agent_settings.json")))
        f = next(x for x in d["fields"] if x["fieldname"] == "minimax_model")
        self.assertEqual(f["fieldtype"], "Data")
        self.assertEqual(f["default"], "MiniMax-M2")
        self.assertNotIn("options", f)

    def test_the_v2_settings_loader_passes_the_setting_to_the_provider(self):
        src = open(os.path.join(ROOT, "api", "agent_v2.py"), encoding="utf8").read()
        self.assertIn('"minimax_model": getattr(settings, "minimax_model", None)', src)


def make_stub_class(providers):
    class Stub(providers.LLMProvider):
        def __init__(self, name, answer=None, error=None):
            super().__init__({})
            self.name = name
            self.answer, self.error, self.calls = answer, error, []

        def chat(self, messages, model=None, temperature=0.3, max_tokens=2000, stream=False):
            self.calls.append(model)
            if self.error:
                raise self.error
            return self.answer

        def chat_stream(self, messages, model=None, temperature=0.3, max_tokens=2000):
            self.calls.append(model)
            if self.error:
                raise self.error
            yield from self.answer
    return Stub


class TestFallback(unittest.TestCase):
    M = [{"role": "user", "content": "hi"}]

    def setUp(self):
        from raven_ai_agent.providers import failover

        self.providers, _mm = load()
        self.failover = failover
        self.Stub = make_stub_class(self.providers)

    def fo(self, primary, fallback):
        return self.failover.FailoverProvider(primary, fallback.name, lambda: fallback)

    def test_primary_ok_never_touches_the_fallback(self):
        p, f = self.Stub("minimax", "A"), self.Stub("openai", "B")
        self.assertEqual(self.fo(p, f).chat(self.M), "A")
        self.assertEqual(f.calls, [])

    def test_primary_fails_fallback_answers_once_without_the_primary_model_name(self):
        for err in (RuntimeError("404 model retired"), TimeoutError("timeout"), ValueError("429")):
            p, f = self.Stub("minimax", error=err), self.Stub("openai", "B")
            fo = self.fo(p, f)
            self.assertEqual(fo.chat(self.M, model="MiniMax-M2.1"), "B")
            self.assertEqual(p.calls, ["MiniMax-M2.1"])
            self.assertEqual(f.calls, [None])          # the primary's model name is not sent to another vendor
            self.assertTrue(fo.used_fallback)

    def test_both_fail_is_one_clear_exception_tried_once(self):
        p, f = self.Stub("minimax", error=RuntimeError("a")), self.Stub("openai", error=RuntimeError("b"))
        with self.assertRaises(self.failover.ProviderFailure) as cm:
            self.fo(p, f).chat(self.M)
        self.assertTrue(cm.exception.fallback_tried)
        self.assertEqual((len(p.calls), len(f.calls)), (1, 1))

    def test_a_fallback_that_cannot_be_built_is_a_clear_failure_not_a_crash(self):
        p = self.Stub("minimax", error=RuntimeError("a"))

        def boom():
            raise ValueError("no key")
        with self.assertRaises(self.failover.ProviderFailure):
            self.failover.FailoverProvider(p, "openai", boom).chat(self.M)

    def test_stream_falls_back_only_before_the_first_chunk(self):
        p, f = self.Stub("minimax", error=RuntimeError("a")), self.Stub("openai", ["x", "y"])
        self.assertEqual(list(self.fo(p, f).chat_stream(self.M)), ["x", "y"])

        def half():
            yield "a"
            raise RuntimeError("cut")
        p2 = self.Stub("minimax", ["x"])
        p2.chat_stream = lambda *a, **k: half()
        with self.assertRaises(RuntimeError):
            list(self.fo(p2, self.Stub("openai", ["z"])).chat_stream(self.M))

    def test_name_and_other_attributes_stay_the_primarys(self):
        p = self.Stub("minimax", "A")
        p.speak = lambda: "voice"
        fo = self.fo(p, self.Stub("openai", "B"))
        self.assertEqual(fo.name, "minimax")
        self.assertEqual(fo.speak(), "voice")

    def test_get_provider_wraps_only_when_a_different_fallback_is_named(self):
        built = []

        def fake_build(name, settings):
            built.append(name)
            return self.Stub(name, "x")
        with mock.patch.object(self.providers, "_build", fake_build):
            self.assertNotIsInstance(self.providers.get_provider("minimax", {}), self.failover.FailoverProvider)
            self.assertNotIsInstance(self.providers.get_provider("minimax", {"fallback_provider": ""}), self.failover.FailoverProvider)
            self.assertNotIsInstance(self.providers.get_provider("openai", {"fallback_provider": "OpenAI"}), self.failover.FailoverProvider)
            del built[:]
            w = self.providers.get_provider("minimax", {"fallback_provider": "OpenAI"})
            self.assertIsInstance(w, self.failover.FailoverProvider)
            self.assertEqual(built.count("openai"), 0)       # the fallback is built lazily, on the first failure

    def test_v2_does_not_retry_the_fallback_a_second_time(self):
        src = open(os.path.join(ROOT, "api", "agent_v2.py"), encoding="utf8").read()
        self.assertIn('not getattr(e, "fallback_tried", False)', src)


if __name__ == "__main__":
    unittest.main()
