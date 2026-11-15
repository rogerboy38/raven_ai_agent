"""TASKS-350 decision 101, zero-DB: the agent sends a prompt only to a model server on the named list in the code
(`providers/model_hosts.py`), in a chat turn AND outside one (a job, a direct call), redirects included. Every check below
fails when its piece is taken out (the mutations are in the reply)."""

import ast
import importlib
import os
import time
import unittest
from unittest import mock

import frappe
import httpx

from raven_ai_agent.api import agent_guard as g
from raven_ai_agent.providers import model_hosts as mh

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "raven_ai_agent"))
UNLISTED = "https://models.example.org/v1"
PUBLIC = ("api.openai.com", "api.deepseek.com", "api.anthropic.com", "api.minimax.io", "api.minimaxi.chat", "api.minimax.chat")
LOOPBACK = ("localhost", "127.0.0.1", "::1")


class TestTheList(unittest.TestCase):
    def test_the_list_is_exactly_the_six_public_provider_hosts(self):
        self.assertEqual(mh.MODEL_SERVER_HOSTS, frozenset(PUBLIC))

    def test_the_loopback_names_are_not_on_it(self):
        for h in LOOPBACK:                                   # decision 104 (TASKS-351)
            self.assertNotIn(h, mh.MODEL_SERVER_HOSTS)
            with self.assertRaises(mh.ModelHostRefused):
                mh.check_model_url(f"http://{'[::1]' if h == '::1' else h}:11434/v1", "a test")

    def test_the_programmes_own_model_host_is_not_on_it(self):
        from raven_ai_agent.providers.ollama import OllamaProvider

        self.assertNotIn(mh.host_of(OllamaProvider.DEFAULT_BASE_URL), mh.MODEL_SERVER_HOSTS)

    def test_every_public_provider_constant_in_the_code_is_on_it(self):
        want = set()
        for mod in ("minimax", "deepseek"):
            m = importlib.import_module(f"raven_ai_agent.providers.{mod}")
            for obj in vars(m).values():
                u = getattr(obj, "BASE_URL", None) if isinstance(obj, type) else None
                if isinstance(u, str) and u.startswith("http"):
                    want.add(mh.host_of(u))
        self.assertTrue(want)
        self.assertTrue(want <= mh.MODEL_SERVER_HOSTS, want - mh.MODEL_SERVER_HOSTS)

    def test_the_guard_uses_this_list_and_nothing_else(self):
        self.assertEqual(g._provider_hosts(), mh.MODEL_SERVER_HOSTS)


class TestSettingsDoNotAddHosts(unittest.TestCase):
    """In a chat turn, through the guard: a host from the settings, the site config or the former allow list is refused."""

    def _turn(self):
        return {"mode": "dry", "blocked": None, "t0": time.monotonic(), "budget": 90, "hold": 30}

    def test_a_settings_ollama_host_is_refused_in_a_chat_turn(self):
        with mock.patch.object(g, "_state", return_value=self._turn()), \
                mock.patch.object(frappe.db, "get_single_value", return_value="https://own-model.example.org/v1", create=True):
            with self.assertRaises(g.AgentWriteBlocked):
                g._check_outbound("https://own-model.example.org/v1/chat/completions", "POST")

    def test_the_former_site_config_allow_list_adds_nothing(self):
        conf = mock.MagicMock()
        conf.get.side_effect = lambda k, d=None: ["own-model.example.org"] if k == "raven_agent_outbound_allow" else d
        with mock.patch.object(g, "_state", return_value=self._turn()), mock.patch.object(frappe, "conf", conf, create=True):
            with self.assertRaises(g.AgentWriteBlocked):
                g._check_outbound("https://own-model.example.org/v1/chat/completions", "POST")

    def test_a_listed_public_provider_still_works_in_a_chat_turn(self):
        with mock.patch.object(g, "_state", return_value=self._turn()):
            for h in PUBLIC:
                g._check_outbound(f"https://{h}/v1/chat/completions", "POST")


class TestWhereTheAddressIsTaken(unittest.TestCase):
    """Outside a chat turn (no guard state at all): the check sits where the address is taken."""

    def setUp(self):
        p = mock.patch.object(g, "_state", return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def assertRefused(self, fn, needle=""):
        # the conftest reloads the package between tests, so the exception class is compared by name
        with self.assertRaises(Exception) as cm:
            fn()
        self.assertEqual(type(cm.exception).__name__, "ModelHostRefused", repr(cm.exception))
        self.assertIn(needle, str(cm.exception))

    def test_the_ollama_provider_refuses_a_setting_host_a_conf_host_and_its_own_default(self):
        from raven_ai_agent.providers.ollama import OllamaProvider

        conf = mock.MagicMock()
        conf.get.return_value = None
        with mock.patch.object(frappe, "conf", conf, create=True):
            self.assertRefused(lambda: OllamaProvider({"ollama_base_url": UNLISTED}))
            self.assertRefused(lambda: OllamaProvider({}), "built-in default")      # the programme's own host
            self.assertRefused(lambda: OllamaProvider({"ollama_base_url": "http://localhost:11434/v1"}))   # decision 104
            OllamaProvider({"ollama_base_url": "https://api.openai.com/v1"})        # a listed host constructs
        conf.get.side_effect = lambda k, d=None: UNLISTED if k == "ollama_base_url" else d
        with mock.patch.object(frappe, "conf", conf, create=True):
            self.assertRefused(lambda: OllamaProvider({}), "Ollama base URL setting")

    def _client_of(self, mod, cls, base_url, env=None):
        m = importlib.import_module(f"raven_ai_agent.api.{mod}")
        settings = mock.MagicMock()
        settings.get.side_effect = lambda k, d=None: base_url if k == "base_url" else None
        settings.get_password.return_value = "k"
        with mock.patch.object(frappe, "get_doc", return_value=settings, create=True), mock.patch.object(frappe, "logger", create=True), \
                mock.patch.dict(os.environ, env or {}, clear=False):
            return getattr(m, cls)()

    def test_the_three_modules_that_read_base_url_refuse_an_unlisted_host_and_accept_a_listed_one(self):
        for mod, cls in (("consolidation_agent", "ConsolidationAgent"), ("enhanced_search", "EnhancedSearch"),
                         ("multimodal_ingest", "MultimodalIngest")):
            self.assertIsNone(self._client_of(mod, cls, UNLISTED).client, mod)
            self.assertIsNotNone(self._client_of(mod, cls, "https://api.openai.com/v1").client, mod)

    def test_multimodal_ingest_does_not_fall_back_to_the_environment_when_the_setting_is_refused(self):
        obj = self._client_of("multimodal_ingest", "MultimodalIngest", UNLISTED, env={"OPENAI_API_KEY": "k"})
        self.assertIsNone(obj.client)

    def test_multimodal_ingest_refuses_an_unlisted_environment_address_too(self):
        m = importlib.import_module("raven_ai_agent.api.multimodal_ingest")
        with mock.patch.object(frappe, "get_doc", side_effect=Exception("no settings"), create=True), mock.patch.object(frappe, "logger", create=True), \
                mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k", "OPENAI_BASE_URL": UNLISTED}):
            self.assertIsNone(m.MultimodalIngest().client)

    def test_the_iot_agent_refuses_an_unlisted_ollama_url_and_sends_nothing(self):
        from raven_ai_agent.agents import iot_agent

        def agent(url):
            cfg = {"enabled": True, "ollama_url": url, "default_model": "m", "request_timeout": 5}
            with mock.patch.object(iot_agent, "get_ollama_config", return_value=cfg):
                return iot_agent.IoTAgent(user="u")
        with mock.patch.object(iot_agent.requests, "post") as post, mock.patch.object(iot_agent.requests, "get") as get:
            for url in ("https://own-model.example.org", "http://10.0.0.7:11434", "http://127.0.0.1:11434"):
                a = agent(url)
                for r in (a._ask_ollama("hi"), a._ollama_status(), a._pull_model("m")):
                    self.assertFalse(r["success"])
                    self.assertIn("approved list", r["error"])
            # decision 104: the IoT bot's own default address is refused too
            r = agent("http://localhost:11434")._ask_ollama("hi")
            self.assertFalse(r["success"])
            self.assertIn("approved list", r["error"])
            post.assert_not_called()
            get.assert_not_called()
            # with a host that IS on the list the call goes out, once, with redirects off
            import sys

            live = sys.modules["raven_ai_agent.providers.model_hosts"]
            post.return_value.json.return_value = {"response": "ok"}
            with mock.patch.object(live, "MODEL_SERVER_HOSTS", frozenset({"iot-model.example.org"})):
                self.assertTrue(agent("https://iot-model.example.org")._ask_ollama("hi")["success"])
            post.assert_called_once()
            self.assertIs(post.call_args.kwargs["allow_redirects"], False)


class TestEveryRequestOfAModelClient(unittest.TestCase):
    """A job or a direct call: no guard state. The hook sees each request and each redirect hop."""

    def setUp(self):
        # outside a chat turn: no guard at all. An earlier test may have left the guard's wrapper on httpx.Client.send
        # (the package is reloaded between tests); put the plain method back for these tests
        import inspect

        p = mock.patch.object(httpx.Client, "send", inspect.unwrap(httpx.Client.send))
        p.start()
        self.addCleanup(p.stop)

    def _client(self, handler):
        calls = []

        def h(request):
            calls.append(str(request.url))
            return handler(request)
        return mh.model_http_client(transport=httpx.MockTransport(h)), calls

    def test_an_unlisted_host_is_refused_before_a_byte_is_sent(self):
        c, calls = self._client(lambda r: httpx.Response(200))
        with self.assertRaises(mh.ModelHostRefused):
            c.post("https://own-model.example.org/v1/chat/completions", json={})
        self.assertEqual(calls, [])

    def test_a_listed_host_passes_with_any_method(self):
        c, calls = self._client(lambda r: httpx.Response(200))
        for h in PUBLIC:
            self.assertEqual(c.post(f"https://{h}/v1/x", json={}).status_code, 200)
        self.assertEqual(len(calls), len(PUBLIC))

    def test_a_redirect_from_a_listed_host_to_an_unlisted_one_is_refused_at_the_second_hop(self):
        def handler(r):
            if r.url.host == "api.openai.com":
                return httpx.Response(307, headers={"Location": "https://own-model.example.org/v1/x"})
            return httpx.Response(200)
        c, calls = self._client(handler)
        with self.assertRaises(mh.ModelHostRefused):
            c.post("https://api.openai.com/v1/x", json={"prompt": "secret"})
        self.assertEqual(calls, ["https://api.openai.com/v1/x"])

    def test_a_redirect_between_two_listed_hosts_is_followed(self):
        def handler(r):
            if r.url.host == "api.openai.com":
                return httpx.Response(307, headers={"Location": "https://api.deepseek.com/v1/x"})
            return httpx.Response(200)
        c, calls = self._client(handler)
        self.assertEqual(c.post("https://api.openai.com/v1/x", json={}).status_code, 200)
        self.assertEqual(len(calls), 2)

    def test_an_sdk_client_whose_address_comes_from_the_environment_is_refused(self):
        import openai

        c, calls = self._client(lambda r: httpx.Response(200, json={}))
        with mock.patch.dict(os.environ, {"OPENAI_BASE_URL": UNLISTED}):
            sdk = openai.OpenAI(api_key="k", http_client=c, max_retries=0)
            with self.assertRaises(openai.APIConnectionError) as cm:
                sdk.chat.completions.create(model="m", messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(calls, [])
        cause = cm.exception.__cause__
        self.assertTrue(isinstance(cause, mh.ModelHostRefused), repr(cause))

    def test_a_provider_that_passes_its_own_client_is_checked_too(self):
        from raven_ai_agent.providers.minimax import MiniMaxProvider  # noqa: F401  (imports model_http_client)


class TestEverySiteGoesThroughTheHelper(unittest.TestCase):
    """A new model client added later that skips the helper fails here (an AST scan of the package)."""

    def _calls(self):
        for dp, dn, fn in os.walk(ROOT):
            if os.sep + "tests" in dp or "__pycache__" in dp:
                continue
            for f in fn:
                if f.endswith(".py"):
                    p = os.path.join(dp, f)
                    try:
                        tree = ast.parse(open(p, encoding="utf8").read())
                    except SyntaxError:
                        continue
                    for n in ast.walk(tree):
                        if isinstance(n, ast.Call):
                            yield os.path.relpath(p, ROOT), n

    def test_every_openai_and_anthropic_client_gets_the_checked_http_client(self):
        sites = []
        for rel, n in self._calls():
            name = getattr(n.func, "id", getattr(n.func, "attr", ""))
            if name in ("OpenAI", "Anthropic", "AsyncOpenAI", "AsyncAnthropic"):
                sites.append(rel)
                kw = {k.arg: ast.unparse(k.value) for k in n.keywords}
                self.assertIn("model_http_client()", kw.get("http_client", ""), f"{rel}:{n.lineno} builds {name} without the checked client")
        self.assertGreaterEqual(len(sites), 8, sites)   # 9 in the first slice; the second slice deletes the unused handlers/base.py

    def test_no_bare_httpx_client_outside_the_helper(self):
        for rel, n in self._calls():
            if isinstance(n.func, ast.Attribute) and n.func.attr in ("Client", "AsyncClient", "stream") and getattr(n.func.value, "id", "") == "httpx":
                self.assertEqual(rel, os.path.join("providers", "model_hosts.py"), f"{rel}:{n.lineno}")

    def test_the_legacy_module_level_openai_call_checks_its_address(self):
        src = open(os.path.join(ROOT, "api", "intent_resolver.py"), encoding="utf8").read()
        self.assertLess(src.index("check_model_url("), src.index("openai.ChatCompletion.create"))


if __name__ == "__main__":
    unittest.main()
