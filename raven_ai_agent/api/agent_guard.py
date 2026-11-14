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

_ORM_CALLER_MARKERS = ("/frappe/model/", "/frappe/utils/nestedset.py", "/frappe/database/")
_PASS_THROUGH_MARKERS = ("/frappe/query_builder/", "/pypika/")
_WRITE_SQL_RE = re.compile(r"^\s*(insert|update|delete|replace|truncate|alter|drop|create)\b", re.I)


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


def _digest(user: str, channel_id: str, text: str, writes=None) -> str:
    blob = f"{user}\x1f{channel_id}\x1f{text}\x1f{json.dumps(writes or [], sort_keys=True)}"
    return hashlib.sha256(blob.encode()).hexdigest()


def store_pending(user: str, channel_id: str, text: str, writes=None, what: str = "", message_name: str = ""):
    """`writes` = the list recorded by the dry run: [{"ident": [...], "what": "..."}]."""
    writes = list(writes or [])
    frappe.cache().set_value(
        _pending_key(user, channel_id),
        {"user": user, "channel": channel_id, "text": text, "writes": writes, "what": what,
         "message": message_name, "digest": _digest(user, channel_id, text, writes), "at": time.time()},
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
    if p.get("digest") != _digest(user, channel_id, p.get("text", ""), p.get("writes")):
        return None
    if time.time() - float(p.get("at") or 0) > PENDING_TTL_SEC:
        return None
    return p


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


def _fingerprint(doc) -> str:
    """Identifies a NEW document before it has a name: its Link and Select values (stable between two runs)."""
    try:
        fields = [f for f in doc.meta.fields if f.fieldtype in ("Link", "Select")]
        items = sorted((f.fieldname, str(doc.get(f.fieldname) or "")) for f in fields
                       if f.fieldname not in ("naming_series", "amended_from"))
    except Exception:
        items = []
    return hashlib.sha1(json.dumps(items).encode()).hexdigest()[:10]


def _what(doc, op: str) -> str:
    name = getattr(doc, "name", "") or ""
    if op == "create":
        hints = []
        try:
            for f in doc.meta.fields:
                if f.fieldtype == "Link" and doc.get(f.fieldname) and len(hints) < 2:
                    hints.append(f"{f.fieldname}={doc.get(f.fieldname)}")
        except Exception:
            pass
        name = f"({', '.join(hints)})" if hints else ""
    return f"{op} {doc.doctype} {name}".strip()


def _ident(doc, op: str) -> list:
    return [op, doc.doctype, _fingerprint(doc) if op == "create" else (getattr(doc, "name", "") or "")]


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


def _record(s, ident: list, what: str):
    s["records"].append({"ident": ident, "what": what})


def _consume(s, ident: list, what: str):
    """Armed: the write must be one the dry run announced (each announced write is used once)."""
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


def _judge_doc(s, op: str, doc):
    what = _what(doc, op)
    mode = s["mode"]
    if mode == "fenced":
        _block("fenced", what)
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
    _judge_doc(s, op, doc)


# --------------------------------------------------------------------- direct writes (no doc event)
def _caller_info(depth: int):
    """(file of the frame `depth` levels above the caller of this helper, True if any frame of the stack above
    that is agent code)."""
    try:
        f = sys._getframe(depth + 1)
    except ValueError:
        return "", False
    # the query builder is a pass-through: judge whoever called IT (agent code, or Frappe's own ORM)
    while f is not None and any(m in f.f_code.co_filename.replace("\\", "/") for m in _PASS_THROUGH_MARKERS):
        f = f.f_back
    if f is None:
        return "", False
    first = f.f_code.co_filename.replace("\\", "/")
    any_agent = False
    n = 0
    while f is not None and n < 120:
        fn = f.f_code.co_filename.replace("\\", "/")
        if "/raven_ai_agent/" in fn and not fn.endswith("agent_guard.py"):
            any_agent = True
            break
        f = f.f_back
        n += 1
    return first, any_agent


def _is_orm_frame(filename: str) -> bool:
    return any(m in filename for m in _ORM_CALLER_MARKERS)


def _direct(kind: str, doctype: str, name: str, depth: int = 2, always_refuse: str = ""):
    """Judge a write that no doc event sees. `depth` 2 = the caller of the wrapper that called this."""
    s = _state()
    if not s:
        return
    first, any_agent = _caller_info(depth)
    if not any_agent or _is_orm_frame(first):
        return                               # not agent initiated, or Frappe's own ORM (judged by its events)
    if kind == "db_insert" and doctype in INFRA_INSERT_DOCTYPES:
        return
    what = f"{kind} {doctype} {name or ''}".strip()
    if always_refuse:
        _block(always_refuse, what)
    mode = s["mode"]
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
    ident = [kind, doctype, name or ""]
    if mode == "dry":
        _record(s, ident, what)
    else:
        _consume(s, ident, what)


def _w_set_value(orig):
    @functools.wraps(orig)
    def wrapper(self, dt, dn=None, field=None, val=None, *a, **kw):
        _direct("set_value", dt, dn if isinstance(dn, str) else "")
        return orig(self, dt, dn, field, val, *a, **kw)
    return wrapper


def _w_set_single(orig):
    @functools.wraps(orig)
    def wrapper(self, doctype, fieldname, value=None, *a, **kw):
        _direct("set_single_value", doctype, fieldname if isinstance(fieldname, str) else "")
        return orig(self, doctype, fieldname, value, *a, **kw)
    return wrapper


def _w_delete(orig):
    @functools.wraps(orig)
    def wrapper(self, doctype, *a, **kw):
        _direct("db.delete", doctype, "", always_refuse="refused_bulk_delete")
        return orig(self, doctype, *a, **kw)
    return wrapper


def _w_refuse(kind):
    def maker(orig):
        @functools.wraps(orig)
        def wrapper(self, *a, **kw):
            _direct(kind, str(a[0]) if a and isinstance(a[0], str) else "", "", always_refuse="refused_raw_sql")
            return orig(self, *a, **kw)
        return wrapper
    return maker


def _w_sql(orig):
    @functools.wraps(orig)
    def wrapper(self, query, *a, **kw):
        if _state() is not None:
            text = query if isinstance(query, str) else str(query)       # a query-builder object
            if _WRITE_SQL_RE.match(text):
                _direct("raw SQL write", "", "", always_refuse="refused_raw_sql")
        return orig(self, query, *a, **kw)
    return wrapper


def _w_doc_db_set(orig):
    @functools.wraps(orig)
    def wrapper(self, *a, **kw):
        _direct("db_set", self.doctype, getattr(self, "name", "") or "")
        return orig(self, *a, **kw)
    return wrapper


def _w_base_db(kind):
    def maker(orig):
        @functools.wraps(orig)
        def wrapper(self, *a, **kw):
            _direct(kind, self.doctype, getattr(self, "name", "") or "")
            return orig(self, *a, **kw)
        return wrapper
    return maker


def _w_rename(orig):
    @functools.wraps(orig)
    def wrapper(*a, **kw):
        dt = a[0] if a and isinstance(a[0], str) else kw.get("doctype", "")
        old = a[1] if len(a) > 1 else kw.get("old", "")
        _direct("rename", dt, old if isinstance(old, str) else "")
        return orig(*a, **kw)
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


def _provider_hosts() -> frozenset:
    try:
        extra = frappe.conf.get("raven_agent_outbound_allow") or []
    except Exception:
        extra = []
    return PROVIDER_HOSTS | frozenset(str(h).lower() for h in extra)


def _w_requests(orig):
    @functools.wraps(orig)
    def wrapper(self, method, url, *a, **kw):
        s = _state()
        if s and s["mode"] in ("dry", "fenced") and _host_of(url) not in _provider_hosts():
            _block("cannot_dry_run", f"outbound call to {_host_of(url) or 'an outside host'}")
        return orig(self, method, url, *a, **kw)
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

    db_cls = type(frappe.local.db)           # frappe.db is a LocalProxy: patch the real class
    for name, maker in (("set_value", _w_set_value), ("set_single_value", _w_set_single), ("delete", _w_delete),
                        ("bulk_insert", _w_refuse("bulk_insert")), ("sql_ddl", _w_refuse("sql_ddl")),
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
    _patch_attr(frappe, "sendmail", _w_sendmail)
    _patch_attr(frappe, "publish_realtime", _w_realtime)
    _patch_attr(frappe, "rename_doc", _w_rename)
    try:
        import requests

        _patch_attr(requests.sessions.Session, "request", _w_requests)
    except Exception:
        pass
    _INSTALLED = True


# ------------------------------------------------------------------------------------------- a turn
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
          "expected": [dict(e) for e in (expected or [])], "done": [], "rt": [], "cb": _cb_lengths()}
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
        return (f"No puedo mostrarle antes lo que hará (llama a un servicio externo o escribe archivos), así que no lo ejecuto: {w}. / "
                f"I cannot show you beforehand what this will do (it calls an outside service or writes files), so I do not run it: {w}.")
    if r == "not_announced":
        return (f"Lo que iba a hacer ahora no coincide con lo que le mostré ({w}); no hice nada. Vuelva a pedirlo. / "
                f"What it was about to do now differs from what I showed you ({w}); I did nothing. Ask again.")
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


def _failure_text(exc) -> str:
    return (f"Algo falló ({type(exc).__name__}); no se hizo nada. / "
            f"Something failed ({type(exc).__name__}); nothing was done.")


def _undo(st, savepoint):
    frappe.db.rollback(save_point=savepoint)
    _restore_callbacks(st)
    if st:
        st["rt"] = []


def _preview(records) -> str:
    lines = [f"{i}. {r['what']}" for i, r in enumerate(records[:MAX_PREVIEW_LINES], 1)]
    more = len(records) - MAX_PREVIEW_LINES
    if more > 0:
        lines.append(f"… y {more} más / and {more} more")
    body = "\n".join(lines)
    return (f"Voy a hacer ({len(records)}):\n{body}\nResponda exactamente `confirm` para ejecutar solo eso (5 min). / "
            f"I am about to do ({len(records)}):\n{body}\nReply exactly `confirm` to run only that (5 min).")


def run_turn(user: str, channel_id: str, text: str, runner, reply, message_name: str = ""):
    """The whole decision for one message. `runner(text)` runs the legacy path with that message text;
    `reply(channel_id, text)` posts a bot message. Returns True when this function handled the turn."""
    trig, _bang, rest = split_trigger(text)
    writer = is_writer(user)

    # 1. a confirm / cancel word that answers a pending request of THIS author in THIS channel
    if has_pending(user, channel_id):
        if is_exact_confirm(text) and writer:
            p = take_pending(user, channel_id)
            if p:
                return _replay(user, channel_id, p, runner, reply)
            reply(channel_id, "La confirmación expiró o no coincide. / The confirmation expired or does not match.")
            return True
        clear_pending(user, channel_id)           # anything else from the author cancels it
        if is_cancel(text):
            reply(channel_id, "Cancelado. / Cancelled.")
            return True

    # 2. every other message with text: a guarded first pass, with any leading `!` removed
    clean = f"{trig} {rest}".strip() if trig else (text or "").strip().lstrip("!").strip()
    if not clean:
        return False
    _first_pass(user, channel_id, clean, runner, reply, writer, message_name)
    return True


def _first_pass(user, channel_id, clean, runner, reply, writer, message_name=""):
    db = frappe.db
    sp = "raven_agent_turn"
    mode = "dry" if writer else "fenced"
    db.savepoint(sp)
    st = None
    try:
        with guarded_turn(user, mode) as st:
            runner(clean)
            if st["blocked"]:                      # a path that swallowed the stop with a bare `except:`
                raise st["blocked"]
        if mode == "dry" and st["records"]:
            records = list(st["records"])
            _undo(st, sp)
            store_pending(user, channel_id, clean, records, what=records[0]["what"], message_name=message_name)
            reply(channel_id, _preview(records))
        else:
            _flush_realtime(st)
    except AgentWriteBlocked as b:
        _undo(st, sp)
        reply(channel_id, _refusal(b, writer))
    except _workflow_errors() as exc:
        _undo(st, sp)
        reply(channel_id, _workflow_refusal(exc))
    except Exception as exc:                       # the guard fails CLOSED: nothing is left behind
        _undo(st, sp)
        frappe.log_error(title="agent_guard turn failed", message=f"{type(exc).__name__}: {exc}")
        reply(channel_id, _failure_text(exc))
    finally:
        try:
            db.release_savepoint(sp)
        except Exception:
            pass


def _armed_text(text: str) -> str:
    trig, _b, rest = split_trigger(text)
    return f"{trig} !{rest}" if trig else f"!{text}"


def _replay(user, channel_id, p, runner, reply):
    db = frappe.db
    sp = "raven_agent_replay"
    db.savepoint(sp)
    st = None
    try:
        with guarded_turn(user, "armed", expected=p.get("writes")) as st:
            runner(_armed_text(p["text"]))
            if st["blocked"]:
                raise st["blocked"]
        _flush_realtime(st)
        done = list(st["done"])
        left = [e["what"] for e in st["expected"]]
        msg = (f"Hecho ({len(done)}): " + "; ".join(done)) if done else "No se hizo ningún cambio. / No change was made."
        if left:
            msg += f" — no hecho / not done: {'; '.join(left)}"
        reply(channel_id, msg)
    except AgentWriteBlocked as b:
        _undo(st, sp)
        reply(channel_id, _refusal(b, True))
    except _workflow_errors() as exc:
        _undo(st, sp)
        reply(channel_id, _workflow_refusal(exc))
    except Exception as exc:
        _undo(st, sp)
        frappe.log_error(title="agent_guard replay failed", message=f"{type(exc).__name__}: {exc}")
        reply(channel_id, _failure_text(exc))
    finally:
        try:
            db.release_savepoint(sp)
        except Exception:
            pass
    return True


# -------------------------------------------------------------------------------- legacy-door glue
def guard_door(fn):
    """Decorator for `handle_raven_message(doc, method)` (the Raven Message after_insert door)."""

    @functools.wraps(fn)
    def wrapper(doc=None, method=None):
        # Slice 1 guards the legacy path only. With the V2 flag on, the message is handed to the V2 job, which
        # slice 2 guards: until then step aside rather than fence an enqueue.
        try:
            from raven_ai_agent.api import pipeline_v2

            if pipeline_v2.is_enabled():
                return fn(doc, method)
        except Exception:
            pass
        try:
            from bs4 import BeautifulSoup

            d = frappe.get_doc("Raven Message", doc) if isinstance(doc, str) else doc
            if d is None or d.is_bot_message or not d.text:
                return fn(doc, method)
            # `handle_raven_message` is also whitelisted: a caller may only replay a message of their own
            if isinstance(doc, str) and frappe.session.user != d.owner:
                return None
            plain = BeautifulSoup(d.text, "html.parser").get_text().strip()
        except Exception:
            return fn(doc, method)

        def runner(t):
            d2 = copy.copy(d)
            d2.text = f"<p>{html.escape(t, quote=False)}</p>"
            return fn(d2, method)

        def reply(channel_id, text):
            frappe.get_doc({"doctype": "Raven Message", "channel_id": channel_id, "text": text,
                            "message_type": "Text", "is_bot_message": 1}).insert(ignore_permissions=True)

        try:
            handled = run_turn(d.owner, d.channel_id, plain, runner, reply, message_name=d.name)
        except Exception as exc:                   # fail CLOSED: never fall through to the unguarded path
            frappe.log_error(title="agent_guard door failed", message=f"{type(exc).__name__}: {exc}")
            try:
                reply(d.channel_id, _failure_text(exc))
            except Exception:
                pass
            return None
        if not handled:
            return fn(doc, method)

    return wrapper


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
