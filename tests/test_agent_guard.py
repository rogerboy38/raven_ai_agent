"""TASKS-337 slice 1, zero-DB (conftest mock frappe): the pure decisions of the agent guard.
The DB-backed scenarios (real fence, real permissions, real workflow) run on a scratch site; see the design letter."""

import copy
import time
import unittest
from unittest import mock

from raven_ai_agent.api import agent_guard as g


class FakeCache:
    def __init__(self):
        self.d = {}

    def set_value(self, k, v, expires_in_sec=None):
        self.d[k] = copy.deepcopy(v)

    def get_value(self, k):
        return copy.deepcopy(self.d.get(k))

    def delete_value(self, k):
        self.d.pop(k, None)


class TestText(unittest.TestCase):
    def test_split_trigger_and_bang(self):
        self.assertEqual(g.split_trigger("@ai !submit x"), ("@ai", "!", "submit x"))
        self.assertEqual(g.split_trigger("@ai   submit x"), ("@ai", "", "submit x"))
        self.assertEqual(g.split_trigger("hello"), (None, "", "hello"))

    def test_exact_confirm_only(self):
        for ok in ("confirm", " Confirm ", "CONFIRMAR", "@ai confirm", "@ai  confirmar"):
            self.assertTrue(g.is_exact_confirm(ok), ok)
        for bad in ("yes", "proceed", "do it", "execute", "confirm please", "please confirm",
                "confirm and submit", "@ai !confirm", "no confirm", ""):
            self.assertFalse(g.is_exact_confirm(bad), bad)

    def test_cancel_words(self):
        self.assertTrue(g.is_cancel("cancel"))
        self.assertTrue(g.is_cancel("@ai cancelar"))
        self.assertFalse(g.is_cancel("cancel the order"))


class TestPending(unittest.TestCase):
    def setUp(self):
        self.cache = FakeCache()
        fr = mock.MagicMock()
        fr.cache.return_value = self.cache
        self.p = mock.patch.object(g, "frappe", fr)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_bound_to_author_and_channel(self):
        g.store_pending("a", "c1", "@ai create x", "create X")
        self.assertIsNone(g.take_pending("b", "c1"))          # another author
        g.store_pending("a", "c1", "@ai create x", "create X")
        self.assertIsNone(g.take_pending("a", "c2"))          # another channel
        g.store_pending("a", "c1", "@ai create x", "create X")
        self.assertEqual(g.take_pending("a", "c1")["text"], "@ai create x")
        self.assertIsNone(g.take_pending("a", "c1"))          # consumed once

    def test_tampered_text_does_not_match_its_digest(self):
        g.store_pending("a", "c1", "@ai create x", "create X")
        k = g._pending_key("a", "c1")
        self.cache.d[k]["text"] = "@ai delete everything"
        self.assertIsNone(g.take_pending("a", "c1"))

    def test_expiry(self):
        g.store_pending("a", "c1", "@ai create x", "create X")
        with mock.patch.object(g.time, "time", return_value=time.time() + g.PENDING_TTL_SEC + 1):
            self.assertIsNone(g.take_pending("a", "c1"))


class TestRunTurn(unittest.TestCase):
    def setUp(self):
        self.cache = FakeCache()
        fr = mock.MagicMock()
        fr.cache.return_value = self.cache
        self.p = mock.patch.object(g, "frappe", fr)
        self.p.start()
        self.replies, self.ran = [], []

        def fenced(user, mode):
            import contextlib

            return contextlib.nullcontext({"mode": mode, "user": user, "blocked": None})

        self.p2 = mock.patch.object(g, "guarded_turn", fenced)
        self.p2.start()

    def tearDown(self):
        self.p.stop()
        self.p2.stop()

    def runner(self, writes):
        def _r(text):
            self.ran.append(text)
            if writes and "!" not in text:
                raise g.AgentWriteBlocked("fenced", "create Thing")
        return _r

    def go(self, user, text, writes=True, writer=True):
        with mock.patch.object(g, "is_writer", return_value=writer):
            return g.run_turn(user, "c1", text, self.runner(writes), lambda c, t: self.replies.append(t))

    def test_non_writer_gets_a_read_only_answer_and_no_pending(self):
        self.go("a", "@ai create thing", writer=False)
        self.assertIn("create Thing", self.replies[-1])
        self.assertFalse(g.has_pending("a", "c1"))

    def test_writer_first_message_previews_and_stores_without_the_bang(self):
        self.go("a", "@ai !create thing")
        self.assertEqual(self.ran, ["@ai create thing"])      # the ! never reached the path
        self.assertTrue(g.has_pending("a", "c1"))
        self.assertIn("confirm", self.replies[-1])

    def test_exact_confirm_replays_armed_with_the_bang_restored(self):
        self.go("a", "@ai create thing")
        self.go("a", "confirm")
        self.assertEqual(self.ran[-1], "@ai !create thing")
        self.assertFalse(g.has_pending("a", "c1"))

    def test_another_authors_confirm_is_not_handled(self):
        self.go("a", "@ai create thing")
        self.assertFalse(self.go("b", "confirm"))
        self.assertTrue(g.has_pending("a", "c1"))

    def test_any_other_message_from_the_author_cancels(self):
        self.go("a", "@ai create thing")
        self.go("a", "confirm please")
        self.assertFalse(g.has_pending("a", "c1"))
        self.assertEqual(len([r for r in self.ran if r.startswith("@ai !")]), 0)

    def test_bare_confirm_with_nothing_pending_is_chat(self):
        self.assertFalse(self.go("a", "confirm"))
        self.assertEqual(self.ran, [])


if __name__ == "__main__":
    unittest.main()
