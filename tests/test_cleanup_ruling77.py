"""TASKS-342 ruling 77, zero-DB: dead code removed, no agent batch creation, guest webhooks refuse an unset secret.
Each test fails if the matching fix is reverted."""

import os
import re
import unittest
from unittest import mock

import frappe

ROOT = os.path.join(os.path.dirname(__file__), "..", "raven_ai_agent")


def _py_sources():
    for dp, _dn, fn in os.walk(ROOT):
        for f in fn:
            if f.endswith(".py"):
                yield os.path.join(dp, f)


class TestRemovals(unittest.TestCase):
    def test_unused_handlers_base_is_gone_and_nothing_imports_it(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, "api/handlers/base.py")))
        for p in _py_sources():
            src = open(p, encoding="utf8").read()
            self.assertNotIn("handlers.base", src, p)
            self.assertNotIn("BaseMixin", src, p)

    def test_alexa_endpoint_module_is_gone_and_nothing_imports_it(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, "api/alexa_to_raven.py")))
        tests_dir = os.path.dirname(__file__)
        for p in list(_py_sources()) + [os.path.join(tests_dir, f) for f in os.listdir(tests_dir) if f.endswith(".py")]:
            if p.endswith("test_cleanup_ruling77.py"):
                continue
            src = open(p, encoding="utf8").read()
            self.assertNotIn("api.alexa_to_raven", src, p)

    def test_the_agent_no_longer_creates_batches_at_all(self):
        for p in _py_sources():
            src = open(p, encoding="utf8").read()
            self.assertIsNone(re.search(r"def create_named_batch|\.create_named_batch\(", src), p)
        plan = open(os.path.join(ROOT, "agents/manufacturing_agent.py"), encoding="utf8").read()
        self.assertIn("the agent does not create batches", plan)


class _Throw(Exception):
    pass


class TestGuestWebhooksRefuseAnUnsetSecret(unittest.TestCase):
    def setUp(self):
        self.p = [
            mock.patch.object(frappe, "throw", side_effect=_Throw, create=True),
            mock.patch.object(frappe, "AuthenticationError", _Throw, create=True),
        ]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def _handle(self, conf, header):
        from raven_ai_agent.api import raven_webhook_handler as m

        with mock.patch.object(frappe, "conf", conf, create=True), \
                mock.patch.object(frappe, "get_request_header", return_value=header, create=True), \
                mock.patch.object(frappe, "request", mock.MagicMock(), create=True):
            return m.handle()

    def test_raven_handle_unset_secret_and_no_header_refuses(self):
        with self.assertRaises(_Throw):
            self._handle({}, None)          # None == None used to pass

    def test_raven_handle_unset_secret_with_any_header_refuses(self):
        with self.assertRaises(_Throw):
            self._handle({}, "anything")

    def test_raven_handle_wrong_or_missing_header_refuses(self):
        with self.assertRaises(_Throw):
            self._handle({"raven_webhook_secret": "s3cret"}, "nope")
        with self.assertRaises(_Throw):
            self._handle({"raven_webhook_secret": "s3cret"}, None)

    def test_raven_handle_right_secret_passes(self):
        self.assertEqual(self._handle({"raven_webhook_secret": "s3cret"}, "s3cret"), {"status": "success"})

    def test_sales_order_handler_unset_secret_or_missing_signature_refuses(self):
        from raven_ai_agent.api import sales_order_webhook as m

        cfg = mock.MagicMock()
        cfg.so_webhook_secret = None
        with mock.patch.object(frappe, "get_site_config", return_value=cfg, create=True), \
                mock.patch.object(frappe, "get_request_header", return_value="sig", create=True), \
                mock.patch.object(frappe, "request", mock.MagicMock(), create=True):
            with self.assertRaises(_Throw):
                m.handler()
        cfg.so_webhook_secret = "k"
        with mock.patch.object(frappe, "get_site_config", return_value=cfg, create=True), \
                mock.patch.object(frappe, "get_request_header", return_value=None, create=True), \
                mock.patch.object(frappe, "request", mock.MagicMock(), create=True):
            with self.assertRaises(_Throw):
                m.handler()

    def test_openai_handler_unset_secret_or_missing_signature_refuses(self):
        from raven_ai_agent.api import openai_webhook as m

        for conf, header in (({}, "sig"), ({"webhook_secret": "k"}, None)):
            with mock.patch.object(frappe, "get_conf", return_value=conf, create=True), \
                    mock.patch.object(frappe, "get_request_header", return_value=header, create=True), \
                    mock.patch.object(frappe, "request", mock.MagicMock(), create=True):
                with self.assertRaises(_Throw):
                    m.handler()


if __name__ == "__main__":
    unittest.main()
