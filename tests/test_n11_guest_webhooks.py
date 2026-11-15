"""TASKS-344 N-11, zero-DB. Each test fails if the matching fix is reverted."""

import ast
import os
import unittest
from unittest import mock

import frappe

API = os.path.join(os.path.dirname(__file__), "..", "raven_ai_agent", "api")


class _Throw(Exception):
    pass


def _src(name):
    return open(os.path.join(API, name), "rb").read().decode("utf8")


def _funcs(name):
    return {n.name: n for n in ast.walk(ast.parse(_src(name))) if isinstance(n, ast.FunctionDef)}


def _is_guest(fn):
    return any("allow_guest=True" in ast.unparse(d) for d in fn.decorator_list)


class TestGuestFunctions(unittest.TestCase):
    def setUp(self):
        self.p = [mock.patch.object(frappe, "throw", side_effect=_Throw, create=True),
                  mock.patch.object(frappe, "AuthenticationError", _Throw, create=True)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def _call(self, fn, conf, header):
        from raven_ai_agent.api import raven_webhook_handler as m

        with mock.patch.object(frappe, "conf", conf, create=True), \
                mock.patch.object(frappe, "get_request_header", return_value=header, create=True), \
                mock.patch.object(frappe, "request", mock.MagicMock(), create=True):
            return getattr(m, fn)()

    def test_handle_webhook_refuses_without_secret_configured_or_sent(self):
        for conf, header in (({}, None), ({}, "x"), ({"raven_webhook_secret": "s"}, None), ({"raven_webhook_secret": "s"}, "bad")):
            with self.assertRaises(_Throw):
                self._call("handle_webhook", conf, header)

    def test_handle_webhook_with_the_right_secret_still_answers(self):
        r = self._call("handle_webhook", {"raven_webhook_secret": "s"}, "s")
        self.assertTrue(r["success"])

    def test_dead_and_broken_guest_functions_are_gone(self):
        names = _funcs("raven_webhook_handler.py")
        self.assertNotIn("handle_sales_order_webhook", names)       # called the undefined verify_webhook()
        self.assertNotIn("create_installation_project", names)      # a guest-callable insert of a Project

    def test_every_guest_function_in_the_file_checks_the_secret_first(self):
        for name, fn in _funcs("raven_webhook_handler.py").items():
            if _is_guest(fn):
                first = [n for n in fn.body if not (isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant))][0]
                self.assertIn("_require_secret", ast.unparse(first), name)


class TestLineEndingsKept(unittest.TestCase):
    """The three files had CRLF lines; slice 2 rewrote them whole. A reviewer must see only the real lines."""

    def test_crlf_lines_are_still_there(self):
        for name, minimum in (("openai_webhook.py", 30), ("raven_webhook_handler.py", 60), ("sales_order_webhook.py", 70)):
            raw = open(os.path.join(API, name), "rb").read()
            self.assertGreaterEqual(raw.count(b"\r\n"), minimum, name)


if __name__ == "__main__":
    unittest.main()
