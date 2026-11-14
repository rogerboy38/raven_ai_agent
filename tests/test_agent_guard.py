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
                return "previewed"
            return "done"
        with mock.patch.object(g, "is_writer", return_value=writer), mock.patch.object(g, "_first_pass", first_pass):
            return g.run_turn(user, "c1", text, runner, lambda c, t: self.replies.append(t))

    R = [{"ident": ["create", "Thing", "fp"], "what": "create Thing (x=1)"},
         {"ident": ["submit", "Thing", "T-1"], "what": "submit Thing T-1"}]

    def test_every_message_with_text_reaches_the_guarded_runner_not_only_triggers(self):
        self.assertTrue(self.go("a", "please run the manufacturing plan"))
        self.assertEqual(self.ran, ["please run the manufacturing plan"])

    def test_a_second_request_of_the_same_author_and_channel_waits_for_the_first(self):
        self.cache.d[g._run_lock_key("a", "c1")] = 1            # a run of this author in this channel is in progress
        self.assertEqual(self.go("a", "@ai do one more thing"), "refused")
        self.assertEqual(self.ran, [])
        self.assertIn("previous request", self.replies[-1])

    def test_another_author_or_channel_is_not_held_up(self):
        self.cache.d[g._run_lock_key("a", "c1")] = 1
        self.assertTrue(self.go("b", "@ai do it"))

    def test_the_lock_is_released_when_the_run_ends(self):
        self.go("a", "@ai do it")
        self.assertNotIn(g._run_lock_key("a", "c1"), self.cache.d)

    def test_the_kill_switch_is_read_again_inside_the_run(self):
        with mock.patch.object(g, "agent_enabled", return_value=False):
            self.assertEqual(self.go("a", "@ai do it"), "refused")
        self.assertEqual(self.ran, [])
        self.assertIn("off", self.replies[-1])

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


class TestAddressedAndPreview(unittest.TestCase):
    """TASKS-344 rulings 83 and 85: only `@ai` (any capitalisation) addresses the agent; the preview shows the weight."""

    def test_only_the_handle_at_the_start_addresses_the_agent(self):
        for ok in ("@ai create x", "@AI create x", "  @Ai create x", "@ai", "@ai\ncreate"):
            self.assertTrue(g._addressed(ok), ok)
        for bad in ("please @ai create x", "@aix create x", "@ai.x create", "ai create x", "@mfg create wo",
                    "executive summary", ""):
            self.assertFalse(g._addressed(bad), bad)

    def test_preview_lists_deletes_cancels_and_submits_before_creates_and_never_cuts_them(self):
        recs = [{"ident": ["create", "Row", "", "h%d" % i], "what": "create Row %d" % i} for i in range(40)]
        recs += [{"ident": ["delete", "Thing", "T-1", "h"], "what": "delete Thing T-1"},
                 {"ident": ["submit", "Thing", "T-2", "h"], "what": "submit Thing T-2"},
                 {"ident": ["sendmail", "", "", ""], "what": "send an e-mail"}]
        text = g._preview(recs, {("create", "Stock Ledger Entry", ""): {"n": 4, "qty": 0.0, "debit": 0.0, "credit": 0.0}})
        lines = text.split("\n")
        order = [ln for ln in lines if ln[:1].isdigit()]
        self.assertTrue(order[0].endswith("delete Thing T-1"))
        self.assertTrue(any("submit Thing T-2" in ln for ln in order[:3]))
        self.assertTrue(any("send an e-mail" in ln for ln in order[:3]))
        self.assertIn("1× delete Thing", text)
        self.assertIn("40× create Row", text)                    # a count per operation
        self.assertIn("4× create Stock Ledger Entry", text)      # what ERPNext will also post
        self.assertLess(len(set(order)), 25)                         # the low-weight tail is summarised, not listed

    def test_a_save_is_matched_on_what_changes_not_only_on_the_name(self):
        class D:
            doctype = "Thing"
            name = "T-1"
            meta = None
        self.assertEqual(g._ident(_Doc(qty=5), "submit")[:3], ["submit", "Thing", "T-1"])
        self.assertNotEqual(g._ident(_Doc(qty=5), "submit")[3], g._ident(_Doc(qty=6), "submit")[3])


class _Meta:
    class F:
        def __init__(self, fieldname, fieldtype="Float"):
            self.fieldname, self.fieldtype = fieldname, fieldtype
    fields = [F("qty"), F("item_code", "Link")]

    def get_table_fields(self):
        return []


class _Doc:
    doctype = "Thing"
    name = "T-1"
    meta = _Meta()

    def __init__(self, qty):
        self._v = {"qty": qty, "item_code": "I-1"}

    def get(self, k):
        return self._v.get(k)

    def get_doc_before_save(self):
        return None


class TestProviderHosts(unittest.TestCase):
    def test_every_provider_base_url_in_the_code_is_an_allowed_outbound_host(self):
        import importlib

        want = set()
        for mod in ("minimax", "deepseek", "ollama"):
            m = importlib.import_module(f"raven_ai_agent.providers.{mod}")
            for obj in vars(m).values():
                for attr in ("BASE_URL", "DEFAULT_BASE_URL"):
                    u = getattr(obj, attr, None) if isinstance(obj, type) else None
                    if isinstance(u, str) and u.startswith("http"):
                        want.add(g._host_of(u))
        self.assertTrue(want, "no provider base URL found")
        self.assertTrue(want <= set(g._provider_hosts()), want - set(g._provider_hosts()))

    def test_a_random_host_is_not_allowed(self):
        self.assertNotIn("example.org", g._provider_hosts())


# ------------------------------------------------------------------------------------ TASKS-347 (fourth round)
import sys as _sys


def _mod(name, src):
    d = {"__name__": name}
    exec(src, d)
    return d


_DOC = _mod("frappe.model.document", """
def save(f): return _save(f)
def _save(f): return f()
def submit(f): return _submit(f)
def _submit(f): return save(f)
def insert(f): return f()
def run_method(f): return f()
""")
_AGENT = _mod("raven_ai_agent.skills.thing", "def go(f): return f()\n")
_ERP = _mod("erpnext.stock.stock_entry", "def hook(f): return f()\n")
_RND = _mod("rnd_warehouse_management.qi_automation", "def hook(f): return f()\ndef helper(f): return f()\n")


def _probe(own_op):
    return g._issuer(_sys._getframe(1), own_op=own_op)


class TestIssuer(unittest.TestCase):
    """C-2/C-3: one rule from the stack, whatever app the code lives in."""

    def test_the_agents_own_document_operation_is_the_agents(self):
        r = _AGENT["go"](lambda: _DOC["save"](lambda: _probe(True)))
        self.assertEqual(r, "agent")

    def test_a_hook_of_our_own_app_under_a_submit_is_a_consequence(self):
        # agent -> submit -> (erpnext on_submit) -> (rnd hook) -> insert of the inspection
        r = _AGENT["go"](lambda: _DOC["submit"](lambda: _ERP["hook"](lambda: _RND["hook"](lambda: _DOC["insert"](lambda: _probe(True))))))
        self.assertEqual(r, "consequence")

    def test_a_controller_method_run_through_the_event_runner_by_the_agent_is_the_agents(self):
        r = _AGENT["go"](lambda: _DOC["run_method"](lambda: _ERP["hook"](lambda: _probe(False))))
        self.assertEqual(r, "agent")

    def test_a_helper_in_another_app_called_by_the_agent_is_the_agents(self):
        r = _AGENT["go"](lambda: _RND["helper"](lambda: _DOC["insert"](lambda: _probe(True))))
        self.assertEqual(r, "agent")

    def test_a_framework_function_called_straight_from_the_agent_is_the_agents(self):
        r = _AGENT["go"](lambda: _ERP["hook"](lambda: _probe(False)))
        self.assertEqual(r, "agent")

    def test_a_direct_write_under_a_submit_is_a_consequence(self):
        r = _AGENT["go"](lambda: _DOC["submit"](lambda: _ERP["hook"](lambda: _probe(False))))
        self.assertEqual(r, "consequence")

    def test_nothing_met_is_judged_as_the_agents(self):
        self.assertEqual(_probe(False), "agent")


class TestConsequences(unittest.TestCase):
    def _s(self):
        return {"conseq": {}, "t0": time.monotonic(), "budget": 90, "hold": 30}

    def test_ledger_consequences_name_where_they_post_and_how_much(self):
        s = self._s()
        g._consequence(s, "create", "Stock Ledger Entry", "Stores - X", -5.0)
        g._consequence(s, "create", "Stock Ledger Entry", "Stores - X", -2.0)
        g._consequence(s, "create", "GL Entry", "Stock In Hand", 0, 100.0, 0)
        text = g._conseq_text(s["conseq"])
        self.assertIn("2× create Stock Ledger Entry (Stores - X, qty -7)", text)
        self.assertIn("1× create GL Entry (Stock In Hand, debit 100)", text)

    def test_the_armed_run_must_post_what_the_dry_run_counted(self):
        a, b = self._s(), self._s()
        for s, q in ((a, -5.0), (b, -5.0)):
            g._consequence(s, "create", "Stock Ledger Entry", "W1", q)
        stored = g._conseq_list(a["conseq"])
        self.assertEqual(g._conseq_diff(stored, b["conseq"]), "")
        c = self._s()
        g._consequence(c, "create", "Stock Ledger Entry", "W1", -6.0)           # another quantity
        self.assertIn("qty -5", g._conseq_diff(stored, c["conseq"]))
        d = self._s()
        g._consequence(d, "create", "Stock Ledger Entry", "W2", -5.0)           # another warehouse
        self.assertTrue(g._conseq_diff(stored, d["conseq"]))
        self.assertTrue(g._conseq_diff(stored, {}))                              # fewer rows

    def test_the_stored_list_survives_json(self):
        s = self._s()
        g._consequence(s, "create", "GL Entry", "Debtors", 0, 10.5, 0)
        import json

        again = json.loads(json.dumps(g._conseq_list(s["conseq"])))
        self.assertEqual(g._conseq_diff(again, s["conseq"]), "")

    def test_the_pending_digest_binds_the_consequences(self):
        a = g._digest("u", "c", "t", [], [["create", "GL Entry", "A", 1, 0, 1, 0]])
        b = g._digest("u", "c", "t", [], [["create", "GL Entry", "A", 1, 0, 2, 0]])
        self.assertNotEqual(a, b)

    def test_sql_consequences_show_the_verb_and_the_table(self):
        self.assertEqual(g._sql_signature("update `tabBin` set actual_qty = 3 where name = 'x'"), "update Bin")
        self.assertTrue(g._HARD_SQL_RE.match("alter table `tabBin` add x int"))
        self.assertFalse(g._HARD_SQL_RE.match("delete from `tabGL Entry` where voucher_no = 'x'"))


class TestContentMatch(unittest.TestCase):
    class _M:
        class F:
            def __init__(self, n, t):
                self.fieldname, self.fieldtype = n, t

        def __init__(self):
            self.fields = [self.F("posting_time", "Time"), self.F("code", "Data"), self.F("ref", "Link")]

    class _D:
        def __init__(self, meta, **v):
            self.meta, self._v = meta, v

        def get(self, k):
            return self._v.get(k)

    def test_a_posting_time_the_author_typed_is_part_of_the_match(self):
        m = self._M()
        typed = g._row_values(self._D(m, set_posting_time=1, posting_time="10:00:00"), m)
        later = g._row_values(self._D(m, set_posting_time=1, posting_time="23:59:00"), m)
        self.assertNotEqual(typed, later)

    def test_a_posting_time_the_system_stamps_is_not(self):
        m = self._M()
        a = g._row_values(self._D(m, set_posting_time=0, posting_time="10:00:00"), m)
        b = g._row_values(self._D(m, set_posting_time=0, posting_time="10:00:07"), m)
        self.assertEqual(a, b)
        c = g._row_values(self._D(m, posting_time="10:00:00"), m)          # a document without the switch: system time
        self.assertNotIn("posting_time", c)

    def test_only_an_id_generated_in_this_pass_is_normalised(self):
        m = self._M()
        st = {"gen": {"a1b2c3d4e5"}}
        with mock.patch.object(g, "_state", return_value=st):
            # an id Frappe generated in this pass (in any field type) is the same id in the other pass
            self.assertEqual(g._row_values(self._D(m, code="a1b2c3d4e5"), m), g._row_values(self._D(m, code="a1b2c3d4e5"), m))
            self.assertEqual(g._norm("a1b2c3d4e5"), "<generated id>")
            # a code the user typed, even of the same shape, is never mistaken for one
            a = g._row_values(self._D(m, code="z9y8x7w6v5"), m)
            b = g._row_values(self._D(m, code="q1q2q3q4q5"), m)
            self.assertNotEqual(a, b)
        with mock.patch.object(g, "_state", return_value=None):
            self.assertEqual(g._norm("a1b2c3d4e5"), "a1b2c3d4e5")


class TestOutbound(unittest.TestCase):
    def _turn(self, mode="dry"):
        return {"mode": mode, "blocked": None, "t0": time.monotonic(), "budget": 90, "hold": 30}

    def test_the_read_only_list_is_empty_until_the_owner_approves_it(self):
        self.assertEqual(g.READONLY_HOSTS, frozenset())

    def test_an_unlisted_host_is_refused_in_every_pass(self):
        for mode in ("fenced", "dry", "armed"):
            with mock.patch.object(g, "_state", return_value=self._turn(mode)):
                with self.assertRaises(g.AgentWriteBlocked):
                    g._check_outbound("https://rates.example.org/x", "GET")

    def test_a_listed_host_is_read_only(self):
        with mock.patch.object(g, "_state", return_value=self._turn()), mock.patch.object(g, "READONLY_HOSTS", frozenset({"rates.example.org"})):
            g._check_outbound("https://rates.example.org/x", "GET")
            g._check_outbound("https://rates.example.org/x", "head")
            with self.assertRaises(g.AgentWriteBlocked):
                g._check_outbound("https://rates.example.org/x", "POST")

    def test_a_model_provider_may_be_posted_to(self):
        with mock.patch.object(g, "_state", return_value=self._turn()):
            g._check_outbound("https://api.openai.com/v1/chat", "POST")

    def test_a_call_after_a_write_is_capped_by_the_time_left(self):
        s = self._turn()
        s["t_write"] = time.monotonic() - 10
        with mock.patch.object(g, "_state", return_value=s):
            cap = g._check_outbound("https://api.openai.com/v1/chat", "POST")
        self.assertTrue(1.0 <= cap <= 20.5, cap)

    def test_a_call_with_no_write_yet_is_not_capped(self):
        with mock.patch.object(g, "_state", return_value=self._turn()):
            self.assertIsNone(g._check_outbound("https://api.openai.com/v1/chat", "POST"))


class TestLockHold(unittest.TestCase):
    def test_a_run_that_has_held_locks_too_long_is_stopped(self):
        s = {"t0": time.monotonic(), "budget": 90, "hold": 30, "t_write": time.monotonic() - 31}
        with self.assertRaises(g.AgentWriteBlocked):
            g._tick(s, "x")

    def test_a_long_run_before_its_first_write_holds_no_locks(self):
        s = {"t0": time.monotonic() - 60, "budget": 90, "hold": 30}
        g._tick(s, "x")                                         # 60 s of thinking, no write yet: fine
        s["t_write"] = time.monotonic()
        g._tick(s, "x")

    def test_the_whole_run_budget_still_applies(self):
        s = {"t0": time.monotonic() - 91, "budget": 90, "hold": 30}
        with self.assertRaises(g.AgentWriteBlocked):
            g._tick(s, "x")
