"""Agent guard (TASKS-337 / TASKS-342, Hugh's decisions 55-58, 74): who may make the agent WRITE, and how.

One door, one rule. EVERY message with text (not only the ones that start with an `@trigger`) runs under the guard.

* A user WITHOUT the role (WRITER_ROLE) runs FENCED: the first write the agent attempts stops the turn
  (`AgentWriteBlocked`, a BaseException so the `except Exception:` blocks of the handlers cannot swallow it), the
  turn is rolled back to a savepoint, the author gets a read-only answer.
* A user WITH the role runs a DRY RUN: the path is allowed to write, so that later steps see earlier ones, and every
  judged write (and every enqueue / e-mail it would send) is RECORDED; at the end everything is rolled back to the
  savepoint (database rows, after-commit callbacks, buffered realtime events) and the author is shown the whole list.
  Only a separate later message from the same author that is exactly a confirm word replays the request ARMED:
  the armed run may do exactly the recorded writes and is stopped at anything else, and the author's OWN ERPNext
  permission is checked on every write whatever `ignore_permissions` the call site passes.
* Things that cannot be dry-run safely (an outbound call to a host that is not a model provider, a File write,
  raw SQL, bulk delete, DDL) stop the turn: the agent refuses rather than guesses.
* `frappe.db.commit` is inert for the length of a turn: the turn owns the transaction.

Slices 2-3 (V2 job, whitelisted endpoints, submit/cancel helper...) build on this module.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import html
import json
import re
import sys
import time
from contextlib import contextmanager

import frappe

WRITER_ROLE = "AI Agent Operator"

# A confirm is a whole message that is exactly one of these (case and surrounding spaces ignored); a leading
# trigger is accepted only when it is the agent's own handle (OWN_HANDLES), a `!` is never accepted.
CONFIRM_WORDS = frozenset({"confirm", "confirmar"})
CANCEL_WORDS = frozenset({"cancel", "cancelar"})
OWN_HANDLES = frozenset({"@ai"})
PENDING_TTL_SEC = 300
MAX_PREVIEW_LINES = 15

# Inserts the agent always may make (replies, its memory, logs): INSERTS ONLY, never update or delete.
INFRA_INSERT_DOCTYPES = frozenset({
    "Raven Message", "AI Memory", "Error Log", "Access Log", "View Log", "Route History", "Bug Report",
    # what Frappe itself inserts as a consequence of a judged write (track changes, deletions, notifications)
    "Version", "Deleted Document", "Activity Log", "Notification Log", "Email Queue", "Email Queue Recipient",
    "Comment", "Workflow Action",
})
# Side effects Frappe itself writes while a workflow transition runs (any operation, only inside
# `apply_workflow_action`).
WORKFLOW_SIDE_EFFECT_DOCTYPES = frozenset({
    "Workflow Action", "Version", "Comment", "Notification Log", "Email Queue", "Email Queue Recipient",
    "Deleted Document",
})
# enqueue() targets that are framework plumbing: dropped during a dry run, run normally when armed.
SILENT_ENQUEUE_PREFIXES = ("frappe.", "raven.", "raven_ai_agent.bug_reporter.")
# Hosts a dry run may still call (the model providers and the local model server).
PROVIDER_HOSTS = frozenset({
    "api.openai.com", "api.deepseek.com", "api.anthropic.com", "api.minimax.io", "api.minimaxi.chat",
    "api.minimax.chat", "localhost", "127.0.0.1", "::1",
})

# Hosts the agent may READ from (GET/HEAD only), by ruling 89. EMPTY until Hugh approves a named list; the default is
# refusal. The model providers are not in this list (they need POST): see `_provider_hosts`.
READONLY_HOSTS = frozenset()
# Code of these apps is "the agent": a write with an agent frame between it and the document operation that caused it is
# the agent's own act. Everything else running under a document operation (ERPNext's controllers, the hooks of our own
# apps, a Server Script) is a CONSEQUENCE of that operation: recorded and compared, never tested against the author.
AGENT_APPS = frozenset({"raven_ai_agent"})
_PASS_THROUGH_MODULES = frozenset({"contextlib", "functools", "typing", "abc", "pypika", "werkzeug"})
# Changing these alters the database structure: MariaDB commits DDL implicitly, so the turn could not be undone.
DDL_DOCTYPES = frozenset({"DocType", "Custom Field", "Customize Form", "Property Setter", "DocField", "DocPerm"})
DRY_RUN_BUDGET_SEC = 90          # wall-clock bound of one dry or armed run
LOCK_HOLD_SEC = 30               # bound of the time the run holds row locks: from its FIRST write to its end
LOCK_WAIT_SEC = 15               # innodb_lock_wait_timeout the background job sets for its session
_WRITE_SQL_RE = re.compile(
    r"^\s*(insert|update|delete|replace|truncate|alter|drop|create|rename|load|call|lock|unlock|start|begin|commit|set\s+autocommit)\b",
    re.I,
)
_HEAVY = {"delete": 0, "cancel": 1, "submit": 2, "sendmail": 3, "enqueue": 4, "rename": 5}


class AgentWriteBlocked(BaseException):
    """Raised from inside a guarded turn. BaseException on purpose: handler code wraps its work in
    `except Exception:` and would otherwise turn a stopped write into a quiet "error" reply."""

    def __init__(self, reason: str, what: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.what = what


# --------------------------------------------------------------------------------------------- state
def _state():
    return getattr(frappe.local, "raven_agent_guard", None)


def _block(reason: str, what: str):
    """Record the stop on the turn (so a path that swallowed it with a bare `except:` is still caught by the
    door) and raise it."""
    exc = AgentWriteBlocked(reason, what)
    s = _state()
    if s is not None and s.get("blocked") is None:
        s["blocked"] = exc
    raise exc


def confirmed() -> bool:
    """True only while an armed replay is running."""
    s = _state()
    return bool(s and s["mode"] == "armed")


def is_writer(user: str) -> bool:
    return WRITER_ROLE in frappe.get_roles(user)


# ------------------------------------------------------------------------------------ text helpers
def split_trigger(text: str):
    """('@ai', '!' or '', 'rest') for '@ai !rest'; (None, '', text) when there is no trigger."""
    m = re.match(r"^\s*(@[\w.-]+)\s*(!?)\s*(.*)$", text or "", re.S)
    if not m:
        return None, "", (text or "").strip()
    return m.group(1), m.group(2), m.group(3).strip()


def is_exact_confirm(text: str) -> bool:
    """The whole message is a confirm word; an optional leading trigger must be the agent's own handle."""
    trig, bang, rest = split_trigger(text)
    if bang:
        return False
    if trig is not None and trig.lower() not in OWN_HANDLES:
        return False
    return (rest or "").strip().lower() in CONFIRM_WORDS


def is_cancel(text: str) -> bool:
    trig, _bang, rest = split_trigger(text)
    if trig is not None and trig.lower() not in OWN_HANDLES:
        return False
    return (rest or "").strip().lower() in CANCEL_WORDS


# ------------------------------------------------------------------------------------ pending store
def _pending_key(user: str, channel_id: str) -> str:
    return f"raven_agent_pending:{user}:{channel_id}"


def _digest(user: str, channel_id: str, text: str, writes=None, conseq=None) -> str:
    blob = f"{user}\x1f{channel_id}\x1f{text}\x1f{json.dumps(writes or [], sort_keys=True)}\x1f{json.dumps(conseq or [], sort_keys=True)}"
    return hashlib.sha256(blob.encode()).hexdigest()


def store_pending(user: str, channel_id: str, text: str, writes=None, what: str = "", message_name: str = "",
                  via: str = "legacy", payload=None, conseq=None):
    """`writes` = the list recorded by the dry run: [{"ident": [...], "what": "..."}]; `conseq` = what the framework
    posted as a consequence (`_conseq_list`): compared with the armed run."""
    writes = list(writes or [])
    conseq = list(conseq or [])
    frappe.cache().set_value(
        _pending_key(user, channel_id),
        {"user": user, "channel": channel_id, "text": text, "writes": writes, "what": what, "via": via,
         "payload": payload, "message": message_name, "conseq": conseq,
         "digest": _digest(user, channel_id, text, writes, conseq), "at": time.time()},
        expires_in_sec=PENDING_TTL_SEC,
    )


def take_pending(user: str, channel_id: str):
    """The pending request for exactly this author and channel, or None. Consumed ATOMICALLY: of two workers
    handling two confirm messages at once, only the one that wins the claim key gets the record."""
    c = frappe.cache()
    key = _pending_key(user, channel_id)
    p = c.get_value(key)
    if not p:
        return None
    try:
        won = c.set(c.make_key(f"{key}:claim"), 1, nx=True, ex=30)
    except AttributeError:       # a cache without raw redis commands (unit-test fake)
        won = True
    if not won:
        return None
    try:
        c.delete_value(key)
    finally:
        try:
            c.delete(c.make_key(f"{key}:claim"))      # the claim only serialises the take; the record is gone
        except AttributeError:
            pass
    if p.get("user") != user or p.get("channel") != channel_id:
        return None
    if p.get("digest") != _digest(user, channel_id, p.get("text", ""), p.get("writes"), p.get("conseq")):
        return None
    if time.time() - float(p.get("at") or 0) > PENDING_TTL_SEC:
        return None
    return p


def peek_pending(user: str, channel_id: str):
    """The pending request without consuming it (None when absent)."""
    p = frappe.cache().get_value(_pending_key(user, channel_id))
    return p if isinstance(p, dict) else None


def has_pending(user: str, channel_id: str) -> bool:
    return bool(frappe.cache().get_value(_pending_key(user, channel_id)))


def clear_pending(user: str, channel_id: str):
    frappe.cache().delete_value(_pending_key(user, channel_id))


# ------------------------------------------------------------------------------- what a write is
_OP_FOR_EVENT = {"before_insert": "create", "on_trash": "delete", "on_cancel": "cancel",
                 "on_update_after_submit": "update_after_submit"}
_PTYPE = {"create": "create", "save": "write", "submit": "submit", "cancel": "cancel", "delete": "delete",
          "update_after_submit": "write", "set_value": "write", "db_set": "write", "set_single_value": "write",
          "db_insert": "create", "db_update": "write", "rename": "write"}
_SYSTEM_FIELDS = frozenset({
    "name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "parent", "parentfield",
    "parenttype", "doctype", "naming_series", "amended_from", "_user_tags", "_comments", "_assign", "_liked_by",
    "__islocal", "__unsaved",
})
_NO_VALUE_TYPES = frozenset({"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Image",
                             "Fold", "Table", "Table MultiSelect"})

_PARTY_FIELDS = ("customer", "supplier", "party", "employee", "lead", "party_name")
_DATE_FIELDS = ("posting_date", "transaction_date", "schedule_date", "delivery_date", "due_date", "planned_start_date")
_TOTAL_FIELDS = ("grand_total", "rounded_total", "total", "net_total", "total_qty", "paid_amount", "qty")


# Frappe's auto-generated ids (child row names, hash-named documents) differ between two runs of the same request. A
# value is treated as "a generated id" only when THIS pass generated it (recorded when Frappe made it): a field that
# merely points at a row or document created earlier in the same pass must not make two runs "differ", and a code the
# user typed can never be mistaken for one.
def _norm(v):
    if v is None or v == "":
        return None
    if isinstance(v, str):
        st = _state()
        if st is not None and v in st.get("gen", ()):
            return "<generated id>"
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, float) or v.__class__.__name__ == "Decimal":
        return round(float(v), 6)
    if hasattr(v, "isoformat"):
        if v.__class__.__name__ == "datetime" and _near_now(v):
            return "<now>"                       # stamped by the system when the pass ran: differs between the two passes
        return v.isoformat()
    return v


def _near_now(v) -> bool:
    try:
        import datetime as _dt

        return abs((_dt.datetime.now(v.tzinfo) - v).total_seconds()) < 120
    except Exception:
        return False


def _row_values(d, meta=None) -> dict:
    """The user-meaningful values of a document or child row (system fields and layout left out). A Time field is
    included only when the author chose the posting time (`set_posting_time` on): that time changes what posts
    (valuation order); a time the system stamps (`now`) differs between two runs."""
    meta = meta or d.meta
    out = {}
    system_time = not d.get("set_posting_time")
    for f in meta.fields:
        if f.fieldname in _SYSTEM_FIELDS or f.fieldtype in _NO_VALUE_TYPES:
            continue
        if f.fieldtype == "Time" and system_time:
            continue
        v = _norm(d.get(f.fieldname))
        if v is not None:
            out[f.fieldname] = v
    return out


def _table_rows(doc) -> dict:
    rows = {}
    try:
        for tf in doc.meta.get_table_fields():
            child_meta = frappe.get_meta(tf.options)
            rows[tf.fieldname] = [_row_values(r, child_meta) for r in (doc.get(tf.fieldname) or [])]
    except Exception:
        pass
    return rows


def _content(doc, op: str) -> dict:
    """What the write is: the values that matter, in a form that is the same in two passes of the same request.
    A save is the CHANGE (fields and rows that differ from the stored document, with their new values)."""
    full = {"values": _row_values(doc), "rows": _table_rows(doc)}
    if op != "save":
        return full
    try:
        before = doc.get_doc_before_save()
    except Exception:
        before = None
    if not before:
        return full
    old = {"values": _row_values(before), "rows": _table_rows(before)}
    changed = {k: v for k, v in full["values"].items() if old["values"].get(k) != v}
    for k in old["values"]:
        if k not in full["values"]:
            changed[k] = None
    rows = {t: r for t, r in full["rows"].items() if old["rows"].get(t) != r}
    return {"values": changed, "rows": rows}


def _content_hash(doc, op: str) -> str:
    return hashlib.sha1(json.dumps(_content(doc, op), sort_keys=True, default=str).encode()).hexdigest()[:12]


def _item_lines(doc, limit=6) -> str:
    try:
        for tf in doc.meta.get_table_fields():
            rows = doc.get(tf.fieldname) or []
            if rows and rows[0].get("item_code") is not None and (rows[0].get("qty") is not None):
                parts = []
                for r in rows[:limit]:
                    wh = r.get("s_warehouse") or r.get("t_warehouse") or r.get("warehouse") or ""
                    parts.append(f"{r.get('item_code')} x {_norm(r.get('qty'))}" + (f" ({wh})" if wh else ""))
                more = f" +{len(rows) - limit} more rows" if len(rows) > limit else ""
                return "; ".join(parts) + more
    except Exception:
        pass
    return ""


def _what(doc, op: str) -> str:
    """One line the author can read: the operation, the document, and the facts the match is made on."""
    name = getattr(doc, "name", "") or ""
    facts = []
    try:
        vals = _row_values(doc)
        for f in _PARTY_FIELDS:
            if vals.get(f):
                facts.append(f"{f}={vals[f]}")
                break
        for f in ("stock_entry_type", "purpose", "company"):
            if vals.get(f):
                facts.append(f"{f}={vals[f]}")
        for f in _DATE_FIELDS:
            if vals.get(f):
                facts.append(f"{f}={vals[f]}")
                break
        for f in _TOTAL_FIELDS:
            if vals.get(f) is not None:
                facts.append(f"{f}={vals[f]}")
                break
        items = _item_lines(doc)
        if items:
            facts.append(f"items: {items}")
        if op == "save":
            c = _content(doc, op)
            ch = [f"{k}={v}" for k, v in list(c["values"].items())[:8]]
            if c["rows"]:
                ch.append("rows changed: " + ", ".join(f"{t} ({len(r)})" for t, r in c["rows"].items()))
            facts = [f"changes: {'; '.join(ch)}"] if ch else facts
    except Exception:
        pass
    text = f"{op} {doc.doctype} {name}".strip() + (f" [{' | '.join(facts)}]" if facts else "")
    return text[:600]


def _ident(doc, op: str) -> list:
    name = getattr(doc, "name", "") or ""
    return [op, doc.doctype, "" if op == "create" else name, _content_hash(doc, op)]


def _author_may(doc, ptype: str, user: str) -> bool:
    try:
        return bool(frappe.has_permission(doc.doctype, ptype, doc=doc, user=user, throw=False))
    except Exception:
        return False


def _has_active_workflow(doctype: str) -> bool:
    try:
        return bool(frappe.db.exists("Workflow", {"document_type": doctype, "is_active": 1}))
    except Exception:
        return False


def _hold_limit() -> float:
    try:
        return float(frappe.conf.get("raven_agent_lock_hold_seconds") or LOCK_HOLD_SEC)
    except Exception:
        return LOCK_HOLD_SEC


def _remaining(s) -> float:
    """Seconds this run may still take: the whole-run budget, and (once it has written, so holds row locks that other
    users wait on) the lock-hold bound counted from its FIRST write."""
    now = time.monotonic()
    left = s.get("budget", DRY_RUN_BUDGET_SEC) - (now - s.get("t0", now))
    tw = s.get("t_write")
    if tw is not None:
        left = min(left, s.get("hold", LOCK_HOLD_SEC) - (now - tw))
    return left


def _tick(s, what=""):
    """Bound a dry or armed run in time. It holds row locks (documents saved, series, bins) from its first write until
    it ends; another user waits on them for up to THEIR OWN lock wait. Checked at every write and every outside call."""
    if s.get("t0") is not None and _remaining(s) < 0:
        _block("too_slow", what or "the run took too long")


def _wrote(s):
    s.setdefault("t_write", time.monotonic())


def _record(s, ident: list, what: str):
    _wrote(s)
    s["records"].append({"ident": ident, "what": what})


def _consume(s, ident: list, what: str):
    """Armed: the write must be one the dry run announced, with the same content (each announced write is used once)."""
    _wrote(s)
    for i, e in enumerate(s["expected"]):
        if e["ident"] == ident:
            s["expected"].pop(i)
            s["done"].append(what)
            return
    _block("not_announced", what)


def _exempt(doctype: str, op: str) -> bool:
    if op == "create" and doctype in INFRA_INSERT_DOCTYPES:
        return True
    return doctype in WORKFLOW_SIDE_EFFECT_DOCTYPES and bool(frappe.flags.get("raven_agent_via_workflow"))


# ---- who issued a write (one decision, used for documents and for direct writes)
def _agent_apps() -> frozenset:
    try:
        extra = frappe.conf.get("raven_agent_agent_apps") or []
    except Exception:
        extra = []
    return AGENT_APPS | frozenset(str(x) for x in extra)


def _root(frame) -> str:
    return (frame.f_globals.get("__name__") or "").split(".", 1)[0]


# the frames that ARE a document operation (the caller of one of these asked for the operation; every hook, controller
# method and validation that runs under it runs as a consequence of it)
_DOC_OPS = {("frappe.model.document", n) for n in
            ("insert", "save", "_save", "submit", "_submit", "cancel", "_cancel")} | {("frappe.model.delete_doc", "delete_doc")}


def _is_doc_op(f) -> bool:
    return ((f.f_globals.get("__name__") or ""), f.f_code.co_name) in _DOC_OPS


def _issuer(frame, own_op: bool = False) -> str:
    """Who is behind the write whose hook/wrapper is running: "agent" or "consequence". One rule, from the stack.

    Walk up from `frame` (with `own_op`, first leave the operation of the judged document itself). The first thing met
    decides:
      an AGENT frame (raven_ai_agent code)                   -> "agent"   the agent asked for this write, directly or
                                                                          through a helper or a framework function it called;
      a DOCUMENT OPERATION of another document (insert, save, submit, cancel, delete) with no agent frame between
                                                              -> "consequence": a controller's on_submit creating ledger
                                                                 entries, a hook of one of our own apps creating an
                                                                 inspection... whatever app the code lives in.
    Nothing met -> "agent" (the stricter answer). A controller method run through `doc.run_method(...)` straight from
    agent code has no operation frame under the agent, so it is the agent's own act."""
    agents = _agent_apps()
    f = frame
    n = 0
    if own_op:
        while f is not None and n < 400 and not _is_doc_op(f):
            f = f.f_back
            n += 1
        if f is None:                         # the hook was not run under an operation frame: judge from the start
            f = frame
        else:                                 # leave ALL frames of the judged document's own operation (submit calls
            mod0 = f.f_globals.get("__name__") or ""          # _submit calls save calls _save...)
            while f is not None and n < 400:
                m = f.f_globals.get("__name__") or ""
                if m != mod0 and m != "frappe.model.document" and m.split(".", 1)[0] not in _PASS_THROUGH_MODULES:
                    break
                f = f.f_back
                n += 1
    n = 0
    while f is not None and n < 400:
        mod = f.f_globals.get("__name__") or ""
        if mod != __name__ and mod.split(".", 1)[0] in agents:
            return "agent"
        if _is_doc_op(f):
            return "consequence"
        f = f.f_back
        n += 1
    return "agent"


def _conseq_detail(doc) -> tuple:
    """(where, quantity, debit, credit) of a ledger-like consequence, so the preview can say where it posts."""
    try:
        dt = doc.doctype
        g = doc.get
        if dt == "Stock Ledger Entry":
            return (g("warehouse") or "", round(float(g("actual_qty") or 0), 4), 0.0, 0.0)
        if dt == "GL Entry":
            return (g("account") or "", 0.0, round(float(g("debit") or 0), 2), round(float(g("credit") or 0), 2))
        if dt == "Payment Ledger Entry":
            return (g("account") or "", round(float(g("amount") or 0), 2), 0.0, 0.0)
        if dt == "Stock Reservation Entry":
            return (g("warehouse") or "", round(float(g("reserved_qty") or 0), 4), 0.0, 0.0)
        if dt == "Serial and Batch Bundle":
            return (g("warehouse") or "", round(float(g("total_qty") or 0), 4), 0.0, 0.0)
    except Exception:
        pass
    return ("", 0.0, 0.0, 0.0)


def _consequence(s, op: str, doctype: str, where: str = "", qty: float = 0.0, debit: float = 0.0, credit: float = 0.0):
    _wrote(s)
    c = s["conseq"]
    e = c.setdefault((op, doctype, where), {"n": 0, "qty": 0.0, "debit": 0.0, "credit": 0.0})
    e["n"] += 1
    e["qty"] = round(e["qty"] + qty, 4)
    e["debit"] = round(e["debit"] + debit, 2)
    e["credit"] = round(e["credit"] + credit, 2)


def _conseq_list(conseq) -> list:
    """The consequences in a form that is stored with the pending request and compared after the armed run."""
    return [[op, dt, where, v["n"], v["qty"], v["debit"], v["credit"]]
            for (op, dt, where), v in sorted(conseq.items(), key=lambda kv: tuple(str(x) for x in kv[0]))]


def _conseq_diff(expected, actual) -> str:
    """"" when the armed run posted what the dry run counted; otherwise a sentence naming the first differences."""
    exp = {(r[0], r[1], r[2]): [r[3], r[4], r[5], r[6]] for r in (expected or [])}
    act = {k: [v["n"], v["qty"], v["debit"], v["credit"]] for k, v in actual.items()}
    out = []
    for k in sorted(set(exp) | set(act), key=lambda x: tuple(str(i) for i in x)):
        a, b = exp.get(k, [0, 0.0, 0.0, 0.0]), act.get(k, [0, 0.0, 0.0, 0.0])
        if a[0] != b[0] or any(abs(x - y) > 0.005 for x, y in zip(a[1:], b[1:])):
            out.append(f"{k[0]} {k[1]}{(' ' + k[2]) if k[2] else ''}: shown {_conseq_fig(a)}, now {_conseq_fig(b)}")
    return "; ".join(out[:5]) + (f" (+{len(out) - 5} more)" if len(out) > 5 else "")


def _conseq_fig(v) -> str:
    bits = [f"{v[0]}×"]
    if v[1]:
        bits.append(f"qty {v[1]:g}")
    if v[2]:
        bits.append(f"debit {v[2]:g}")
    if v[3]:
        bits.append(f"credit {v[3]:g}")
    return " ".join(bits)


def _judge_doc(s, op: str, doc, issuer: str):
    what = _what(doc, op)
    mode = s["mode"]
    _tick(s, what)
    if issuer == "consequence" and mode != "fenced":
        if doc.doctype in DDL_DOCTYPES:
            _block("cannot_dry_run", f"{what} (changes the database structure)")
        w, q, dr, cr = _conseq_detail(doc)       # recorded and compared, not tested against the author's rights
        _consequence(s, op, doc.doctype, w, q, dr, cr)
        return
    if mode == "fenced":
        _block("fenced", what)
    if doc.doctype in DDL_DOCTYPES:
        _block("cannot_dry_run", f"{what} (changes the database structure)")
    if doc.doctype == "File" and op == "create":
        _block("cannot_dry_run", what)                       # a file's content is written to disk
    if not _author_may(doc, _PTYPE[op], s["user"]):
        _block("no_permission", what)
    if op in ("submit", "cancel") and _has_active_workflow(doc.doctype) and not frappe.flags.get("raven_agent_via_workflow"):
        _block("needs_workflow_action", what)
    key = (id(doc), op)
    if key in s["seen"]:
        return
    s["seen"].add(key)
    s["keep"].append(doc)                                   # keeps id() unique for the length of the turn
    ident = _ident(doc, op)
    if mode == "dry":
        _record(s, ident, what)
        return
    _consume(s, ident, what)


def on_write_event(doc, method=None):
    """doc_events["*"] hook: before_validate (save and submit; it runs BEFORE Frappe's `ignore_validate` return),
    before_insert, on_trash, on_cancel, on_update_after_submit (post events, never skipped). Costs one attribute
    read when no agent turn is running."""
    s = _state()
    if not s:
        return
    if method == "before_validate":
        action = getattr(doc, "_action", None)
        if doc.is_new() or action not in ("save", "submit"):
            return
        op = action
    else:
        op = _OP_FOR_EVENT.get(method)
        if op is None:
            return
    if _exempt(doc.doctype, op):
        return
    _judge_doc(s, op, doc, _issuer(sys._getframe(1), own_op=True))


# --------------------------------------------------------------------- direct writes (no doc event)
def _inner(orig, *a, **kw):
    """Run the original of a wrapper that has just been judged: what Frappe itself issues inside it (a `db_set` runs
    an UPDATE, a `set_value` several statements) is part of that one judged write, not new writes."""
    s = _state()
    if not s:
        return orig(*a, **kw)
    s["inner"] = s.get("inner", 0) + 1
    try:
        return orig(*a, **kw)
    finally:
        s["inner"] -= 1


_HARD_SQL_RE = re.compile(r"^\s*(alter|drop|create|rename|truncate|load|call|lock|unlock|start|begin|commit|set\s+autocommit)\b", re.I)


def _sql_signature(text: str) -> str:
    """What a raw statement is, for the preview: its verb and the table it names (never its values)."""
    m = re.match(r"^\s*(\w+)", text or "")
    verb = (m.group(1).lower() if m else "sql")
    t = re.search(r"`tab([^`]+)`", text or "")
    return f"{verb} {t.group(1)}" if t else verb


def _direct(kind: str, doctype: str, name: str, always_refuse: str = "", detail: str = "", hard: bool = True):
    """Judge a write that no doc event sees. Called from a wrapper: the frame two levels up is the wrapper's caller.
    `always_refuse` is refused for the agent; for a CONSEQUENCE only when `hard` (structure changes, implicit commits)."""
    s = _state()
    if not s or s.get("inner"):
        return
    imm = sys._getframe(2)                    # the wrapper's caller, the query builder looked through
    while imm is not None and ((imm.f_globals.get("__name__") or "").startswith("frappe.query_builder")
                               or _root(imm) in _PASS_THROUGH_MODULES):
        imm = imm.f_back
    issuer = _issuer(sys._getframe(2))
    if issuer == "consequence" and imm is not None and _root(imm) == "frappe":
        return                                # Frappe's own ORM calling its own database layer under a document operation:
                                              # judged by that operation's events. A framework utility called straight from
                                              # agent code (no operation frame under the agent) is NOT this case.
    if kind == "db_insert" and doctype in INFRA_INSERT_DOCTYPES:
        return
    what = f"{kind} {doctype} {name or ''}".strip() + (f" ({detail})" if detail else "")
    mode = s["mode"]
    _tick(s, what)
    if issuer == "consequence" and mode != "fenced":
        if always_refuse and hard:
            _block(always_refuse, what)
        _consequence(s, kind + (f": {detail}" if detail else ""), doctype)   # shown with its statement or table
        return
    if always_refuse:
        _block(always_refuse, what)
    if mode == "fenced":
        _block("fenced", what)
    ptype = _PTYPE.get(kind, "write")
    try:
        if kind in ("db_insert", "set_single_value", "rename") or not name:
            ok = bool(frappe.has_permission(doctype, ptype, user=s["user"], throw=False))
        else:
            ok = bool(frappe.has_permission(doctype, ptype, doc=name, user=s["user"], throw=False))
    except Exception:
        ok = False
    if not ok:
        _block("no_permission", what)
    ident = [kind, doctype, name or "", ""]
    if mode == "dry":
        _record(s, ident, what)
    else:
        _consume(s, ident, what)


def _w_set_value(orig):
    @functools.wraps(orig)
    def wrapper(self, dt, dn=None, field=None, val=None, *a, **kw):
        _direct("set_value", dt, dn if isinstance(dn, str) else "")
        return _inner(orig, self, dt, dn, field, val, *a, **kw)
    return wrapper


def _w_set_single(orig):
    @functools.wraps(orig)
    def wrapper(self, doctype, fieldname, value=None, *a, **kw):
        _direct("set_single_value", doctype, fieldname if isinstance(fieldname, str) else "")
        return _inner(orig, self, doctype, fieldname, value, *a, **kw)
    return wrapper


def _w_delete(orig):
    @functools.wraps(orig)
    def wrapper(self, doctype, *a, **kw):
        _direct("db.delete", doctype, "", always_refuse="refused_bulk_delete", hard=False)
        return _inner(orig, self, doctype, *a, **kw)
    return wrapper


def _w_refuse(kind, hard=True):
    def maker(orig):
        @functools.wraps(orig)
        def wrapper(self, *a, **kw):
            _direct(kind, str(a[0]) if a and isinstance(a[0], str) else "", "", always_refuse="refused_raw_sql", hard=hard)
            return orig(self, *a, **kw)
        return wrapper
    return maker


def _w_sql(orig):
    @functools.wraps(orig)
    def wrapper(self, query, *a, **kw):
        if _state() is not None:
            text = query if isinstance(query, str) else str(query)       # a query-builder object
            if _WRITE_SQL_RE.match(text):
                _direct("raw SQL write", "", "", always_refuse="refused_raw_sql", detail=_sql_signature(text),
                        hard=bool(_HARD_SQL_RE.match(text)))
        return orig(self, query, *a, **kw)
    return wrapper


def _w_doc_db_set(orig):
    @functools.wraps(orig)
    def wrapper(self, *a, **kw):
        _direct("db_set", self.doctype, getattr(self, "name", "") or "")
        return _inner(orig, self, *a, **kw)
    return wrapper


def _w_base_db(kind):
    def maker(orig):
        @functools.wraps(orig)
        def wrapper(self, *a, **kw):
            _direct(kind, self.doctype, getattr(self, "name", "") or "")
            return _inner(orig, self, *a, **kw)
        return wrapper
    return maker


def _w_rename(orig):
    @functools.wraps(orig)
    def wrapper(*a, **kw):
        dt = a[0] if a and isinstance(a[0], str) else kw.get("doctype", "")
        old = a[1] if len(a) > 1 else kw.get("old", "")
        _direct("rename", dt, old if isinstance(old, str) else "")
        return _inner(orig, *a, **kw)
    return wrapper


# ----------------------------------------------------------- effects that leave the database: enqueue, mail...
def _enqueue_name(a, kw) -> str:
    m = kw.get("method") if "method" in kw else (a[0] if a else None)
    if isinstance(m, str):
        return m
    return f"{getattr(m, '__module__', '')}.{getattr(m, '__qualname__', '?')}"


def _w_enqueue(orig):
    @functools.wraps(orig)
    def wrapper(*a, **kw):
        s = _state()
        if not s:
            return orig(*a, **kw)
        name = _enqueue_name(a, kw)
        if name.startswith(SILENT_ENQUEUE_PREFIXES):
            return None if s["mode"] in ("dry", "fenced") else orig(*a, **kw)
        what = f"enqueue {name}"
        if s["mode"] == "fenced":
            _block("fenced", what)
        ident = ["enqueue", name, ""]
        if s["mode"] == "dry":
            _record(s, ident, what)
            return None
        _consume(s, ident, what)
        return orig(*a, **kw)
    return wrapper


def _w_sendmail(orig):
    @functools.wraps(orig)
    def wrapper(*a, **kw):
        s = _state()
        if not s:
            return orig(*a, **kw)
        what = "send an e-mail"
        if s["mode"] == "fenced":
            _block("fenced", what)
        ident = ["sendmail", "", ""]
        if s["mode"] == "dry":
            _record(s, ident, what)
            return None
        _consume(s, ident, what)
        return orig(*a, **kw)
    return wrapper


_ORIG: dict = {}


def _w_realtime(orig):
    _ORIG["publish_realtime"] = orig

    @functools.wraps(orig)
    def wrapper(*a, **kw):
        s = _state()
        if s and s["mode"] in ("dry", "fenced"):
            s["rt"].append((a, kw))            # delivered only if the pass leaves the database as it is
            return None
        return orig(*a, **kw)
    return wrapper


def _host_of(url) -> str:
    from urllib.parse import urlparse

    try:
        return (urlparse(str(url)).hostname or "").lower()
    except Exception:
        return ""


_PROVIDER_HOSTS_CACHE = {}


def _provider_hosts() -> frozenset:
    """The model providers' own hosts: the fixed list, the base URLs written in the provider classes, the Ollama URL
    in the settings, and a site-config list `raven_agent_outbound_allow`."""
    hosts = set(PROVIDER_HOSTS)
    if "classes" not in _PROVIDER_HOSTS_CACHE:
        found = set()
        try:
            import importlib

            for mod in ("minimax", "deepseek", "ollama", "openai_provider", "claude"):
                m = importlib.import_module(f"raven_ai_agent.providers.{mod}")
                for attr in ("BASE_URL", "DEFAULT_BASE_URL"):
                    for obj in vars(m).values():
                        u = getattr(obj, attr, None) if isinstance(obj, type) else None
                        if isinstance(u, str) and u.startswith("http"):
                            found.add(_host_of(u))
        except Exception:
            pass
        _PROVIDER_HOSTS_CACHE["classes"] = {h for h in found if h}
    hosts |= _PROVIDER_HOSTS_CACHE["classes"]
    try:
        u = frappe.db.get_single_value("AI Agent Settings", "ollama_base_url")
        if u:
            hosts.add(_host_of(u))
    except Exception:
        pass
    try:
        hosts |= {str(h).lower() for h in (frappe.conf.get("raven_agent_outbound_allow") or [])}
    except Exception:
        pass
    return frozenset(hosts)


def _check_outbound(url, method="GET"):
    """Ruling 89: a model provider (any method), or a NAMED read-only host (GET/HEAD only); everything else is refused
    in every pass. The time left to the run caps the call (a model call must not keep locks held beyond the bound)."""
    s = _state()
    if not s:
        return None
    host = _host_of(url)
    m = str(method or "GET").upper()
    ok = host in _provider_hosts() or (host in READONLY_HOSTS and m in ("GET", "HEAD"))
    if not ok:
        what = f"outbound {m} to {host or 'an outside host'}"
        if s["mode"] == "armed":
            _block("not_announced", what)        # a dry run cannot have shown it: it would have been refused
        _block("cannot_dry_run", what)
    _tick(s, f"outbound {m} to {host}")
    return max(1.0, _remaining(s)) if s.get("t_write") is not None else None


def _w_requests(orig):
    @functools.wraps(orig)
    def wrapper(self, method, url, *a, **kw):
        cap = _check_outbound(url, method)
        if cap is not None:
            t = kw.get("timeout")
            kw["timeout"] = cap if t is None else (min(cap, t) if isinstance(t, (int, float)) else cap)
        return orig(self, method, url, *a, **kw)
    return wrapper


def _w_httpx_send(orig):
    @functools.wraps(orig)
    def wrapper(self, request, *a, **kw):
        cap = _check_outbound(getattr(request, "url", ""), getattr(request, "method", "GET"))
        if cap is not None:
            try:
                ext = request.extensions.setdefault("timeout", {})
                for k in ("connect", "read", "write", "pool"):
                    cur = ext.get(k)
                    ext[k] = cap if cur is None else min(cap, cur)
            except Exception:
                pass
        return orig(self, request, *a, **kw)
    return wrapper


def _w_genid(orig):
    @functools.wraps(orig)
    def wrapper(*a, **kw):
        v = orig(*a, **kw)
        s = _state()
        if s is not None and isinstance(v, str):
            s.setdefault("gen", set()).add(v)
        return v
    return wrapper


def _w_genid_name(orig):
    """`make_autoname("hash")` is how Frappe names child rows and hash-named documents."""
    @functools.wraps(orig)
    def wrapper(*a, **kw):
        v = orig(*a, **kw)
        s = _state()
        key = a[0] if a else kw.get("key", "")
        if s is not None and key == "hash" and isinstance(v, str):
            s.setdefault("gen", set()).add(v)
        return v
    return wrapper


def _w_rollback(orig):
    """An unqualified rollback inside a turn is a handler cleaning up after a failed step; it must not leave the
    earlier steps behind, and it cannot (the turn owns the transaction): the whole turn is undone instead."""
    @functools.wraps(orig)
    def wrapper(self, *a, **kw):
        s = _state()
        if s and not kw.get("save_point") and not a:
            _block("handler_rolled_back", "a step failed and its handler rolled back")
        return orig(self, *a, **kw)
    return wrapper


_INSTALLED = False


def _patch_attr(owner, name, maker):
    orig = owner.__dict__[name] if name in getattr(owner, "__dict__", {}) else getattr(owner, name, None)
    if orig is not None and not getattr(orig, "_raven_guard", False):
        new = maker(orig)
        new._raven_guard = True
        setattr(owner, name, new)


def _install():
    """Patch once per process. Every wrapper does nothing unless a guarded turn is running."""
    global _INSTALLED
    if _INSTALLED:
        return
    from frappe.model.base_document import BaseDocument
    from frappe.model.document import Document

    real_db = getattr(frappe.local, "db", None)
    if real_db is None:                      # no site connected (unit tests with a mocked frappe): nothing to wrap
        return
    db_cls = type(real_db)                   # frappe.db is a LocalProxy: patch the real class
    for name, maker in (("set_value", _w_set_value), ("set_single_value", _w_set_single), ("delete", _w_delete),
                        ("bulk_insert", _w_refuse("bulk_insert", hard=False)), ("sql_ddl", _w_refuse("sql_ddl")),
                        ("truncate", _w_refuse("truncate")), ("sql", _w_sql)):
        owner = next((c for c in db_cls.__mro__ if name in c.__dict__), None)
        if owner is not None:
            _patch_attr(owner, name, maker)
    _patch_attr(Document, "db_set", _w_doc_db_set)
    _patch_attr(BaseDocument, "db_insert", _w_base_db("db_insert"))
    _patch_attr(BaseDocument, "db_update", _w_base_db("db_update"))
    _patch_attr(frappe, "enqueue", _w_enqueue)
    try:
        import frappe.utils.background_jobs as bj

        _patch_attr(bj, "enqueue", _w_enqueue)
    except Exception:
        pass
    try:
        import frappe.model.naming as _naming

        _patch_attr(_naming, "make_autoname", _w_genid_name)
    except Exception:
        pass
    _patch_attr(frappe, "generate_hash", _w_genid)
    _patch_attr(frappe, "sendmail", _w_sendmail)
    _patch_attr(frappe, "publish_realtime", _w_realtime)
    _patch_attr(frappe, "rename_doc", _w_rename)
    owner = next((c for c in db_cls.__mro__ if "rollback" in c.__dict__), None)
    if owner is not None:
        _patch_attr(owner, "rollback", _w_rollback)
    try:
        import requests

        _patch_attr(requests.sessions.Session, "request", _w_requests)
    except Exception:
        pass
    try:
        import httpx

        _patch_attr(httpx.Client, "send", _w_httpx_send)
    except Exception:
        pass
    _INSTALLED = True


# ------------------------------------------------------------------------------------------- a turn
def _budget() -> float:
    try:
        return float(frappe.conf.get("raven_agent_dry_run_seconds") or DRY_RUN_BUDGET_SEC)
    except Exception:
        return DRY_RUN_BUDGET_SEC


def _cb_lengths():
    db = frappe.db
    return (len(db.before_commit._functions), len(db.after_commit._functions))


def _restore_callbacks(st):
    """A savepoint rollback does not touch Frappe's before/after-commit queues: drop what the pass added."""
    if not st:
        return
    n_before, n_after = st["cb"]
    db = frappe.db
    while len(db.before_commit._functions) > n_before:
        db.before_commit._functions.pop()
    while len(db.after_commit._functions) > n_after:
        db.after_commit._functions.pop()


def _flush_realtime(st):
    orig = _ORIG.get("publish_realtime")
    if not st or not orig:
        return
    buffered, st["rt"] = st["rt"], []
    for a, kw in buffered:
        try:
            orig(*a, **kw)
        except Exception:
            pass


@contextmanager
def guarded_turn(user: str, mode: str, expected=None):
    """Run a block as `fenced` (nothing may be written), `dry` (writes happen and are recorded; the caller undoes
    them) or `armed` (writes obey `user`'s own rights and must be among `expected`)."""
    assert mode in ("fenced", "dry", "armed")
    _install()
    db = frappe.db
    prev = _state()
    st = {"mode": mode, "user": user, "blocked": None, "records": [], "seen": set(), "keep": [],
          "expected": [dict(e) for e in (expected or [])], "done": [], "rt": [], "cb": _cb_lengths(),
          "conseq": {}, "t0": time.monotonic(), "budget": _budget(), "hold": _hold_limit()}
    frappe.local.raven_agent_guard = st
    db._disable_transaction_control += 1                  # a commit inside the turn is inert
    try:
        yield st
    finally:
        db._disable_transaction_control -= 1
        frappe.local.raven_agent_guard = prev


# ------------------------------------------------------------------------------------- the one door
def _refusal(b: AgentWriteBlocked, writer: bool) -> str:
    w = b.what
    r = b.reason
    if r == "no_permission":
        return f"No puedo hacerlo con sus permisos de ERPNext: {w}. / I cannot do that with your own ERPNext rights: {w}."
    if r == "needs_workflow_action":
        return f"Ese paso debe pasar por el flujo de trabajo, no lo ejecuto directamente: {w}. / That step must go through the workflow action; I do not run it directly: {w}."
    if r in ("refused_raw_sql", "refused_bulk_delete"):
        return f"Ese cambio no está permitido para el agente: {w}. / The agent is not allowed to make that change: {w}."
    if r == "cannot_dry_run":
        return (f"No puedo mostrarle antes lo que hará (llama a un servicio externo, escribe archivos o cambia la estructura), así que no lo ejecuto: {w}. / "
                f"I cannot show you beforehand what this will do (it calls an outside service, writes files or changes the structure), so I do not run it: {w}.")
    if r == "not_announced":
        return (f"Lo que iba a hacer ahora no coincide con lo que le mostré ({w}); no hice nada. Vuelva a pedirlo. / "
                f"What it was about to do now differs from what I showed you ({w}); I did nothing. Ask again.")
    if r == "handler_rolled_back":
        return (f"Un paso falló a mitad ({w}); deshice todo y no se guardó nada. / "
                f"A step failed half way ({w}); I undid everything and nothing was kept.")
    if r == "too_slow":
        return (f"Tardó demasiado en prepararse ({w}); no se guardó nada. Vuelva a pedirlo. / "
                f"It took too long to prepare ({w}); nothing was kept. Ask again.")
    if not writer:
        return (f"Solo puedo consultar para usted (le falta el rol {WRITER_ROLE}): {w}. / "
                f"I can only answer read-only for you (the role {WRITER_ROLE} is missing): {w}.")
    return f"No se pudo: {w}. / Not done: {w}."


def _workflow_errors() -> tuple:
    try:
        from frappe.model.workflow import WorkflowPermissionError, WorkflowTransitionError

        return (WorkflowPermissionError, WorkflowTransitionError)
    except Exception:
        return ()                                  # no Frappe workflow module (mocked tests): catches nothing


def _workflow_refusal(exc) -> str:
    return (f"El flujo de trabajo no permite este paso a su usuario: {exc}. No busco otra vía. / "
            f"The workflow does not let your user take this step: {exc}. I do not look for another way.")


def _failure_text(exc, undone: bool = True) -> str:
    if not undone:
        return (f"Algo falló ({type(exc).__name__}) y NO pude deshacer todo: puede quedar algo escrito; avise a un administrador. / "
                f"Something failed ({type(exc).__name__}) and I could NOT undo everything: something may remain written; tell an administrator.")
    return (f"Algo falló ({type(exc).__name__}); no se hizo nada. / "
            f"Something failed ({type(exc).__name__}); nothing was done.")


def _undo(st, savepoint, user: str = "", channel_id: str = "") -> bool:
    """Undo a pass: rollback to the savepoint, drop the callbacks it queued, forget the cache entries of documents
    that no longer exist, and the legacy code's own pending key. Returns False when the rollback itself failed."""
    ok = True
    try:
        frappe.db.rollback(save_point=savepoint)
    except Exception as exc:                       # e.g. an implicit commit destroyed the savepoint
        ok = False
        frappe.log_error(title="agent_guard undo failed", message=f"{type(exc).__name__}: {exc}")
    _restore_callbacks(st)
    if st:
        st["rt"] = []
        for d in st.get("keep", []):
            try:
                if getattr(d, "name", None):
                    frappe.clear_document_cache(d.doctype, d.name)
            except Exception:
                pass
    _drop_legacy_pending(user, channel_id)
    return ok


def _drop_legacy_pending(user: str, channel_id: str):
    """The legacy command router stores its own `pending_confirm` key during a pass; the guard owns confirmation."""
    if user and channel_id:
        try:
            frappe.cache().delete_value(f"pending_confirm:{user}:{channel_id}")
        except Exception:
            pass


def _conseq_text(conseq) -> str:
    """What the framework posts as a consequence: how many, where (warehouse, account), the quantities and amounts."""
    parts = []
    for (op, dt, where), v in sorted(conseq.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        fig = []
        if v["qty"]:
            fig.append(f"qty {v['qty']:g}")
        if v["debit"]:
            fig.append(f"debit {v['debit']:g}")
        if v["credit"]:
            fig.append(f"credit {v['credit']:g}")
        tail = ", ".join(([where] if where else []) + fig)
        parts.append(f"{v['n']}× {op} {dt}".strip() + (f" ({tail})" if tail else ""))
    return "; ".join(parts)


def _preview(records, conseq=None) -> str:
    """The whole list, heaviest first; heavy operations (delete, cancel, submit, mail, jobs) are never cut."""
    def weight(r):
        return _HEAVY.get(r["ident"][0], 6 if r["ident"][0] == "create" else 7)
    ordered = sorted(records, key=weight)
    counts = {}
    for r in records:
        k = f"{r['ident'][0]} {r['ident'][1]}".strip()
        counts[k] = counts.get(k, 0) + 1
    summary = ", ".join(f"{n}× {k}" for k, n in sorted(counts.items(), key=lambda kv: (weight({'ident': [kv[0].split()[0]]}), kv[0])))
    heavy = [r for r in ordered if weight(r) <= 5]
    rest = [r for r in ordered if weight(r) > 5]
    shown = heavy + rest[:MAX_PREVIEW_LINES]
    hidden = rest[MAX_PREVIEW_LINES:]
    lines = [f"{i}. {r['what']}" for i, r in enumerate(shown, 1)]
    if hidden:
        hc = {}
        for r in hidden:
            k = f"{r['ident'][0]} {r['ident'][1]}"
            hc[k] = hc.get(k, 0) + 1
        lines.append("… " + ", ".join(f"{n}× {k}" for k, n in sorted(hc.items())) + " (lower weight, not listed)")
    if conseq:
        lines.append("Además se registrará (lo hace ERPNext) / ERPNext will also post: " + _conseq_text(conseq))
    body = "\n".join(lines)
    return (f"Voy a hacer ({len(records)}: {summary}):\n{body}\nResponda exactamente `confirm` para ejecutar solo eso (5 min). / "
            f"I am about to do ({len(records)}: {summary}):\n{body}\nReply exactly `confirm` to run only that (5 min).")


def _run_lock_key(user: str, channel_id: str):
    c = frappe.cache()
    return c.make_key(f"raven_agent_run:{user}:{channel_id}")


def _take_run_lock(user: str, channel_id: str) -> bool:
    c = frappe.cache()
    try:
        return bool(c.set(_run_lock_key(user, channel_id), 1, nx=True, ex=RUN_LOCK_SEC))
    except AttributeError:                    # a cache without raw redis commands (unit-test fake)
        return True


def _release_run_lock(user: str, channel_id: str):
    try:
        frappe.cache().delete(_run_lock_key(user, channel_id))
    except AttributeError:
        pass


def run_turn(user: str, channel_id: str, text: str, runner, reply, message_name: str = "", via: str = "legacy",
             raise_failures: bool = False):
    """The whole decision for one message that IS addressed to the agent (`@ai ...`) or confirms a request.
    `runner(text)` runs the path with that message text; `reply(channel_id, text)` posts a bot message.
    Returns False when the message is not handled here, else a status string: "done", "previewed", "refused",
    "replayed"."""
    trig, _bang, rest = split_trigger(text)
    writer = is_writer(user)
    if not agent_enabled(raven=True):            # J-3: read again here, so a job queued before the switch went off stops
        clear_pending(user, channel_id)
        reply(channel_id, OFF_TEXT)
        return "refused"
    if not _take_run_lock(user, channel_id):     # J-1: one run at a time per author and channel
        reply(channel_id, BUSY_TEXT)
        return "refused"
    try:
        return _run_turn_locked(user, channel_id, text, runner, reply, message_name, via, raise_failures, trig, rest, writer)
    finally:
        _release_run_lock(user, channel_id)


def _run_turn_locked(user, channel_id, text, runner, reply, message_name, via, raise_failures, trig, rest, writer):
    # 1. a confirm / cancel word that answers a pending request of THIS author in THIS channel
    if has_pending(user, channel_id):
        pk = peek_pending(user, channel_id)
        if pk and pk.get("via", "legacy") != via and is_exact_confirm(text):
            reply(channel_id, "La acción pendiente es de otra vía: responda `confirm` solo, como mensaje aparte. / "
                              "The pending action belongs to another route: send `confirm` alone, as a separate message.")
            return "refused"                      # left intact: nothing ran, nothing was cancelled
        if is_exact_confirm(text) and writer:
            p = take_pending(user, channel_id)
            if p:
                return _replay(user, channel_id, p, runner, reply, raise_failures)
            reply(channel_id, "La confirmación expiró o no coincide. / The confirmation expired or does not match.")
            return "refused"
        clear_pending(user, channel_id)           # anything else from the author cancels it
        if is_cancel(text):
            reply(channel_id, "Cancelado. / Cancelled.")
            return "refused"

    # 2. a guarded first pass, with any leading `!` removed
    clean = f"{trig} {rest}".strip() if trig else (text or "").strip().lstrip("!").strip()
    if not clean:
        return False
    return _first_pass(user, channel_id, clean, runner, reply, writer, message_name, via, raise_failures)


def run_readonly(user: str, channel_id: str, text: str, runner, reply) -> str:
    """A message NOT addressed with `@ai` (ruling 83): it may reach a keyword path, which can only READ. Never a
    dry run, never a preview, never a write. Silent unless the path tried to write: then one short hint."""
    db = frappe.db
    sp = "raven_agent_readonly"
    db.savepoint(sp)
    st = None
    status = "done"
    try:
        with guarded_turn(user, "fenced") as st:
            runner((text or "").strip().lstrip("!").strip())
            if st["blocked"]:
                raise st["blocked"]
        _flush_realtime(st)
    except AgentWriteBlocked:
        _undo(st, sp, user, channel_id)
        status = "refused"
        reply(channel_id, "Para hacer cambios empiece el mensaje con `@ai`. / To make changes, start the message with `@ai`.")
    except _workflow_errors():
        _undo(st, sp, user, channel_id)
        status = "refused"
    except Exception as exc:
        ok = _undo(st, sp, user, channel_id)
        frappe.log_error(title="agent_guard read-only pass failed", message=f"{type(exc).__name__}: {exc}")
        status = "failed"
        if not ok:
            reply(channel_id, _failure_text(exc, undone=False))
    finally:
        try:
            db.release_savepoint(sp)
        except Exception:
            pass
        _drop_legacy_pending(user, channel_id)
    return status


def _first_pass(user, channel_id, clean, runner, reply, writer, message_name="", via="legacy", raise_failures=False):
    db = frappe.db
    sp = "raven_agent_turn"
    mode = "dry" if writer else "fenced"
    db.savepoint(sp)
    st = None
    status = "refused"
    try:
        with guarded_turn(user, mode) as st:
            # the dry run IS the preview: the path runs as it will when confirmed (its own two-step is skipped),
            # so that it really writes, is recorded, and is undone
            runner(_armed_text(clean) if mode == "dry" else clean)
            if st["blocked"]:                      # a path that swallowed the stop with a bare `except:`
                raise st["blocked"]
        if mode == "dry" and st["records"]:
            records = list(st["records"])
            conseq = dict(st["conseq"])
            ok = _undo(st, sp, user, channel_id)
            if not ok:
                reply(channel_id, _failure_text(RuntimeError("undo"), undone=False))
            else:
                reply(channel_id, _preview(records, conseq))      # the author can only confirm what was posted:
                store_pending(user, channel_id, clean, records, what=records[0]["what"], message_name=message_name,
                              via=via, conseq=_conseq_list(conseq))   # a worker lost between the two leaves nothing to confirm
                status = "previewed"
        else:
            _flush_realtime(st)
            status = "done"
    except AgentWriteBlocked as b:
        ok = _undo(st, sp, user, channel_id)
        reply(channel_id, _refusal(b, writer) if ok else _failure_text(b, undone=False))
    except _workflow_errors() as exc:
        ok = _undo(st, sp, user, channel_id)
        reply(channel_id, _workflow_refusal(exc) if ok else _failure_text(exc, undone=False))
    except Exception as exc:                       # the guard fails CLOSED: nothing is left behind
        ok = _undo(st, sp, user, channel_id)
        frappe.log_error(title="agent_guard turn failed", message=f"{type(exc).__name__}: {exc}")
        if raise_failures and ok:                  # the caller (V2 job) has its own apology and audit
            raise
        reply(channel_id, _failure_text(exc, undone=ok))
    finally:
        try:
            db.release_savepoint(sp)
        except Exception:
            pass
        _drop_legacy_pending(user, channel_id)
    return status


def _armed_text(text: str) -> str:
    trig, _b, rest = split_trigger(text)
    return f"{trig} !{rest}" if trig else f"!{text}"


def _replay(user, channel_id, p, runner, reply, raise_failures=False):
    """The armed run: exactly the announced writes, with the same content; ALL of them or nothing."""
    db = frappe.db
    sp = "raven_agent_replay"
    db.savepoint(sp)
    st = None
    status = "refused"
    try:
        with guarded_turn(user, "armed", expected=p.get("writes")) as st:
            runner(_armed_text(p["text"]))
            if st["blocked"]:
                raise st["blocked"]
            left = [e["what"] for e in st["expected"]]
            if left:                                # all or nothing (ruling 85b)
                _block("not_announced", "not done: " + "; ".join(left))
            if "conseq" in p:                       # what ERPNext posts must equal what the dry run counted (C-1)
                diff = _conseq_diff(p.get("conseq"), st["conseq"])
                if diff:
                    _block("not_announced", "ERPNext's own postings differ from what I showed: " + diff)
        _flush_realtime(st)
        done = list(st["done"])
        conseq = dict(st["conseq"])
        msg = (f"Hecho ({len(done)}): " + "; ".join(done)) if done else "No se hizo ningún cambio. / No change was made."
        if conseq:
            msg += " — ERPNext registró / posted: " + _conseq_text(conseq)
        reply(channel_id, msg)
        status = "replayed"
    except AgentWriteBlocked as b:
        ok = _undo(st, sp, user, channel_id)
        reply(channel_id, _refusal(b, True) if ok else _failure_text(b, undone=False))
    except _workflow_errors() as exc:
        ok = _undo(st, sp, user, channel_id)
        reply(channel_id, _workflow_refusal(exc) if ok else _failure_text(exc, undone=False))
    except Exception as exc:
        ok = _undo(st, sp, user, channel_id)
        frappe.log_error(title="agent_guard replay failed", message=f"{type(exc).__name__}: {exc}")
        if raise_failures and ok:
            raise
        reply(channel_id, _failure_text(exc, undone=ok))
    finally:
        try:
            db.release_savepoint(sp)
        except Exception:
            pass
        _drop_legacy_pending(user, channel_id)
    return status


# ------------------------------------------------------------------------------------- kill switch
_OFF = ("0", "false", "no", "off")


def agent_enabled(raven: bool = False) -> bool:
    """AI Agent Settings `enabled` (and, for the Raven door, `raven_enabled`). Unset or unreadable = on."""
    for field in (("enabled", "raven_enabled") if raven else ("enabled",)):
        try:
            v = frappe.db.get_single_value("AI Agent Settings", field)
        except Exception:
            continue
        if v is not None and str(v).strip().lower() in _OFF:
            return False
    return True


OFF_TEXT = "El agente está apagado. / The agent is off."
BUSY_TEXT = ("Sigo con su petición anterior en este canal; espere mi respuesta y vuelva a enviar esta. / "
             "I am still on your previous request in this channel; wait for my answer and send this one again.")
RUN_LOCK_SEC = 330                                     # the queue's job timeout (300 s) and a margin: a killed worker's lock expires
ACK_TEXT = "⏳ Preparando… si no hay respuesta en 3 minutos, envíe de nuevo. / Working on it… if there is no answer in 3 minutes, send it again."
_LEGACY = {}                                           # the undecorated handle_raven_message, set by guard_door


# -------------------------------------------------------------------------------- legacy-door glue
def _post_reply(channel_id, text):
    doc = frappe.get_doc({"doctype": "Raven Message", "channel_id": channel_id, "text": text,
                          "message_type": "Text", "is_bot_message": 1})
    doc.insert(ignore_permissions=True)
    return getattr(doc, "name", None)


def _make_runner(d, fn, method):
    def runner(t):
        d2 = copy.copy(d)
        d2.text = f"<p>{html.escape(t, quote=False)}</p>"
        return fn(d2, method)
    return runner


_ADDRESSED_RE = re.compile(r"^\s*@ai(?![\w.-])", re.I)


def _addressed(plain: str) -> bool:
    """Writes are possible only in a message that STARTS with the agent's handle, in any capitalisation."""
    return bool(_ADDRESSED_RE.match(plain or ""))


def guard_door(fn):
    """Decorator for `handle_raven_message(doc, method)` (the Raven Message after_insert door).

    * kill switch first, for every message that could reach an agent path;
    * a message that does NOT start with `@ai`: a read-only pass (ruling 83), inline, silent unless it tried to write;
    * a message that does: for a holder of the role the dry run (and, later, the confirm) runs in a BACKGROUND job
      (ruling 85c) while the author sees an acknowledgement; for anyone else a short read-only pass inline.
    No path reaches the legacy function unguarded: a failure to read, to enqueue or to guard ends in a reply that
    says nothing was done."""
    _LEGACY["fn"] = fn

    @functools.wraps(fn)
    def wrapper(doc=None, method=None):
        try:
            from bs4 import BeautifulSoup

            d = frappe.get_doc("Raven Message", doc) if isinstance(doc, str) else doc
            if d is None or d.is_bot_message or not d.text:
                return fn(doc, method)
            # `handle_raven_message` is also whitelisted: a caller may only replay a message of their own
            if isinstance(doc, str) and frappe.session.user != d.owner:
                return None
            plain = BeautifulSoup(d.text, "html.parser").get_text().strip()
        except Exception as exc:                   # fail CLOSED (N-10a): never hand an unreadable message on
            frappe.log_error(title="agent_guard could not read the message", message=f"{type(exc).__name__}: {exc}")
            return None

        user, channel = d.owner, d.channel_id
        addressed = _addressed(plain)
        if not agent_enabled(raven=True):
            if addressed:
                _post_reply(channel, OFF_TEXT)
            return None
        runner = _make_runner(d, fn, method)
        try:
            v2 = _v2_enabled()
            if v2:
                pend = peek_pending(user, channel)
                if addressed:                      # the V2 job runs the turn; a failed dispatch is reported, never retried inline
                    return _dispatch_v2(d, plain[3:].strip() or "help", user, channel)
                if pend and pend.get("via") == "v2" and is_exact_confirm(plain):
                    return _dispatch_v2(d, "confirm", user, channel)
            if not addressed:
                if has_pending(user, channel) and (is_exact_confirm(plain) or is_cancel(plain)) and is_writer(user):
                    return _enqueue_job(d, "turn", None)    # a bare `confirm` / `cancel` answers a pending request
                if has_pending(user, channel):
                    clear_pending(user, channel)            # any other message of the author cancels it
                run_readonly(user, channel, plain, runner, _post_reply)
                return None
            if is_writer(user):
                ack = _post_reply(channel, ACK_TEXT)
                return _enqueue_job(d, "turn", ack)
            run_turn(user, channel, plain, runner, _post_reply, message_name=d.name)
        except Exception as exc:                   # fail CLOSED: never fall through to the unguarded path
            frappe.log_error(title="agent_guard door failed", message=f"{type(exc).__name__}: {exc}")
            try:
                _post_reply(channel, _failure_text(exc))
            except Exception:
                pass
        return None

    return wrapper


def _v2_enabled() -> bool:
    try:
        from raven_ai_agent.api import pipeline_v2

        return bool(pipeline_v2.is_enabled())
    except Exception:
        return False


def _dispatch_v2(d, query: str, user: str, channel: str):
    try:
        from raven_ai_agent.api import pipeline_v2

        pipeline_v2.dispatch(message_name=d.name, channel_id=channel, query=query, user=user)
    except Exception as exc:
        frappe.log_error(title="agent_guard V2 dispatch failed", message=f"{type(exc).__name__}: {exc}")
        _post_reply(channel, "No pude iniciar la tarea; no se hizo nada. Vuelva a enviarlo. / "
                             "I could not start the task; nothing was done. Send it again.")
    return None


def _enqueue_job(d, kind: str, ack_name=None):
    frappe.enqueue("raven_ai_agent.api.agent_guard.run_door_job", queue="short", timeout=300,
                   enqueue_after_commit=True, message_name=d.name, kind=kind, ack_name=ack_name)


def run_door_job(message_name: str, kind: str = "turn", ack_name: str = None):
    """Background job of the door: the dry run (or the confirmed run) of one message. Never raises."""
    from bs4 import BeautifulSoup

    d = None
    try:
        d = frappe.get_doc("Raven Message", message_name)
        user, channel = d.owner, d.channel_id
        frappe.set_user(user)
        try:
            frappe.db.sql(f"set session innodb_lock_wait_timeout = {int(LOCK_WAIT_SEC)}")
        except Exception:
            pass
        plain = BeautifulSoup(d.text, "html.parser").get_text().strip()
        fn = _LEGACY.get("fn")
        if fn is None:
            from raven_ai_agent.api.agent import handle_raven_message as hrm   # noqa: F401  (registers the decorator)

            fn = _LEGACY["fn"]
        run_turn(user, channel, plain, _make_runner(d, fn, "after_insert"), _post_reply, message_name=d.name)
    except Exception as exc:
        frappe.log_error(title="agent_guard job failed", message=f"{type(exc).__name__}: {exc}")
        try:
            if d is not None:
                _post_reply(d.channel_id, _failure_text(exc))
        except Exception:
            pass
    finally:
        if ack_name:                               # the answer (or the failure notice) is out: the acknowledgement goes
            try:
                frappe.delete_doc("Raven Message", ack_name, ignore_permissions=True, force=True)
            except Exception:
                pass
        try:
            frappe.db.commit()
        except Exception:
            pass


# ------------------------------------------------------------------------- the workflow way to submit
def apply_workflow_action(doc, action: str):
    """What replaces a direct `doc.submit()` / `doc.save()` that moves a document through its workflow:
    Frappe's own `apply_workflow`, so the transition's role and its self-approval rule apply to the AUTHOR.
    Sets the flag the armed-mode submit check looks for, for this call only. A transition nobody holds
    raises Frappe's WorkflowPermissionError; the agent reports it and does not look for another way."""
    from frappe.model.workflow import apply_workflow

    prev = frappe.flags.get("raven_agent_via_workflow")
    frappe.flags.raven_agent_via_workflow = True
    try:
        return apply_workflow(doc, action)
    finally:
        frappe.flags.raven_agent_via_workflow = prev
