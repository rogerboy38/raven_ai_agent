"""TASKS-337 / TASKS-342, zero-DB (conftest mock frappe): the pure decisions of the agent guard.
The DB-backed behaviour (real doc events, savepoints, permissions, workflow, enqueue/mail/realtime, the real
door) is exercised on a scratch site: see `scn3.py` and its mutation table in the design letter."""

import contextlib
import copy
import time
import unittest
from unittest import mock

from raven_ai_agent.api import agent_guard as g


class FakeCache:
    def __init__(self, claim_free=True):
        self.d = {}
        self.claim_free = claim_free

    def set_value(self, k, v, expires_in_sec=None):
        self.d[k] = copy.deepcopy(v)

    def get_value(self, k):
        return copy.deepcopy(self.d.get(k))

    def delete_value(self, k):
        self.d.pop(k, None)

    def make_key(self, k):
        return k

    def set(self, k, v, nx=False, ex=None):
        if nx and (k in self.d or not self.claim_free):
            return False
        self.d[k] = v
        return True

    def delete(self, k):
        self.d.pop(k, None)


class TestText(unittest.TestCase):
    def test_split_trigger_and_bang(self):
        self.assertEqual(g.split_trigger("@ai !submit x"), ("@ai", "!", "submit x"))
        self.assertEqual(g.split_trigger("@ai   submit x"), ("@ai", "", "submit x"))
        self.assertEqual(g.split_trigger("hello"), (None, "", "hello"))

    def test_exact_confirm_only(self):
        for ok in ("confirm", " Confirm ", "CONFIRMAR", "@ai confirm", "@AI  confirmar"):
            self.assertTrue(g.is_exact_confirm(ok), ok)
        for bad in ("yes", "proceed", "do it", "execute", "confirm please", "please confirm",
                    "confirm and submit", "@ai !confirm", "no confirm", "", "@colleague confirm", "@mfg confirm"):
            self.assertFalse(g.is_exact_confirm(bad), bad)

    def test_cancel_words_only_for_the_agents_own_handle(self):
        self.assertTrue(g.is_cancel("cancel"))
        self.assertTrue(g.is_cancel("@ai cancelar"))
        self.assertFalse(g.is_cancel("cancel the order"))
        self.assertFalse(g.is_cancel("@colleague cancel"))


class TestPending(unittest.TestCase):
    def setUp(self):
        self.cache = FakeCache()
        fr = mock.MagicMock()
        fr.cache.return_value = self.cache
        self.p = mock.patch.object(g, "frappe", fr)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    W = [{"ident": ["create", "Thing", "fp1"], "what": "create Thing"}]

    def test_bound_to_author_and_channel(self):
        g.store_pending("a", "c1", "@ai create x", self.W)
        self.assertIsNone(g.take_pending("b", "c1"))
        g.store_pending("a", "c1", "@ai create x", self.W)
        self.assertIsNone(g.take_pending("a", "c2"))
        g.store_pending("a", "c1", "@ai create x", self.W)
        self.assertEqual(g.take_pending("a", "c1")["text"], "@ai create x")
        self.assertIsNone(g.take_pending("a", "c1"))

    def test_tampered_text_or_list_does_not_match_its_digest(self):
        for field, value in (("text", "@ai delete everything"), ("writes", [])):
            g.store_pending("a", "c1", "@ai create x", self.W)
            self.cache.d[g._pending_key("a", "c1")][field] = value
            self.assertIsNone(g.take_pending("a", "c1"), field)

    def test_expiry(self):
        g.store_pending("a", "c1", "@ai create x", self.W)
        with mock.patch.object(g.time, "time", return_value=time.time() + g.PENDING_TTL_SEC + 1):
            self.assertIsNone(g.take_pending("a", "c1"))

    def test_second_worker_that_loses_the_claim_gets_nothing(self):
        g.store_pending("a", "c1", "@ai create x", self.W)
        self.cache.claim_free = False
        self.assertIsNone(g.take_pending("a", "c1"))
        self.assertTrue(g.has_pending("a", "c1"))          # the winner still owns it

    def test_claim_is_released_after_a_successful_take(self):
        g.store_pending("a", "c1", "@ai create x", self.W)
        self.assertIsNotNone(g.take_pending("a", "c1"))
        g.store_pending("a", "c1", "@ai create y", self.W)
        self.assertIsNotNone(g.take_pending("a", "c1"))     # not blocked by a stale claim


class TestRunTurn(unittest.TestCase):
    """run_turn with the guarded turn replaced by a recorder: it checks the DECISIONS (who is fenced, who gets a
    dry run, what is stored, what the replay text is), not the database effects."""

    def setUp(self):
        self.cache = FakeCache()
        fr = mock.MagicMock()
        fr.cache.return_value = self.cache
        self.patches = [mock.patch.object(g, "frappe", fr)]
        self.modes, self.replies, self.ran = [], [], []
        self.writes_to_record = []
        self.block = None

        @contextlib.contextmanager
        def fake_turn(user, mode, expected=None):
            self.modes.append(mode)
            st = {"mode": mode, "user": user, "blocked": None, "records": [], "rt": [], "cb": (0, 0),
                  "expected": [], "done": []}
            yield st

        self.patches.append(mock.patch.object(g, "guarded_turn", fake_turn))
        self.patches.append(mock.patch.object(g, "_undo", lambda st, sp: None))
        self.patches.append(mock.patch.object(g, "_flush_realtime", lambda st: None))
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def go(self, user, text, writer=True, records=None, block=None):
        def runner(t):
            self.ran.append(t)
            if block:
                raise block
            # the fake turn dict is created per call; surface records through the preview path instead
        # emulate the turn: a dry run that recorded writes
        def first_pass(u, ch, clean, r, rep, w, mn="", via="legacy", rf=False):
            r(clean)
            if records and w:
                g.store_pending(u, ch, clean, records, what=records[0]["what"], message_name=mn)
                rep(ch, g._preview(records))
            return "previewed" if records and w else "done"
        with mock.patch.object(g, "is_writer", return_value=writer), mock.patch.object(g, "_first_pass", first_pass):
            return g.run_turn(user, "c1", text, runner, lambda c, t: self.replies.append(t))

    R = [{"ident": ["create", "Thing", "fp"], "what": "create Thing (x=1)"},
         {"ident": ["submit", "Thing", "T-1"], "what": "submit Thing T-1"}]

    def test_every_message_with_text_reaches_the_guarded_runner_not_only_triggers(self):
        self.assertTrue(self.go("a", "please run the manufacturing plan"))
        self.assertEqual(self.ran, ["please run the manufacturing plan"])

    def test_empty_text_is_not_handled(self):
        self.assertFalse(self.go("a", "   "))

    def test_bang_is_removed_from_the_first_message(self):
        self.go("a", "@ai !create thing")
        self.go("a", "!create thing")
        self.assertEqual(self.ran, ["@ai create thing", "create thing"])

    def test_preview_lists_every_recorded_write(self):
        self.go("a", "@ai do it", records=self.R)
        self.assertIn("create Thing (x=1)", self.replies[-1])
        self.assertIn("submit Thing T-1", self.replies[-1])
        self.assertTrue(g.has_pending("a", "c1"))
        self.assertEqual(g.take_pending("a", "c1")["writes"], self.R)

    def test_replay_text_restores_the_bang_for_triggered_and_untriggered_messages(self):
        self.assertEqual(g._armed_text("@ai create thing"), "@ai !create thing")
        self.assertEqual(g._armed_text("run the manufacturing plan"), "!run the manufacturing plan")

    def test_another_authors_confirm_is_a_normal_turn_and_does_not_replay(self):
        self.go("a", "@ai do it", records=self.R)
        self.ran.clear()
        self.go("b", "confirm")
        self.assertEqual(self.ran, ["confirm"])               # a plain guarded turn for b
        self.assertTrue(g.has_pending("a", "c1"))

    def test_any_other_message_from_the_author_cancels_the_pending_request(self):
        self.go("a", "@ai do it", records=self.R)
        self.go("a", "confirm please")
        self.assertFalse(g.has_pending("a", "c1"))

    def test_other_handle_confirm_does_not_confirm_and_cancels(self):
        self.go("a", "@ai do it", records=self.R)
        with mock.patch.object(g, "_replay") as rp:
            self.go("a", "@colleague confirm")
            rp.assert_not_called()
        self.assertFalse(g.has_pending("a", "c1"))


class TestReasons(unittest.TestCase):
    def test_every_block_reason_has_a_text(self):
        for r in ("fenced", "no_permission", "needs_workflow_action", "refused_raw_sql", "refused_bulk_delete",
                  "cannot_dry_run", "not_announced"):
            self.assertTrue(g._refusal(g.AgentWriteBlocked(r, "X"), True))
            self.assertTrue(g._refusal(g.AgentWriteBlocked(r, "X"), False))

    def test_a_blocked_write_is_not_an_exception_subclass(self):
        self.assertTrue(issubclass(g.AgentWriteBlocked, BaseException))
        self.assertFalse(issubclass(g.AgentWriteBlocked, Exception))


if __name__ == "__main__":
    unittest.main()
