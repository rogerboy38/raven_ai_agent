"""Agent guard (TASKS-337, Hugh's decisions 55-58): who may make the agent WRITE, and how.

One door, one rule. Every chat turn runs FENCED first: any write the agent attempts is stopped
(`AgentWriteBlocked`, a BaseException so the many `except Exception:` blocks in the handlers cannot
swallow it), the turn is rolled back to a savepoint, and the author is told what the agent wanted to do.
Only an author who holds the dedicated role (WRITER_ROLE) can then send, as a SEPARATE later message,
exactly a confirm word; that message replays the stored request ARMED. In armed mode the doc-event hook
checks the AUTHOR's own ERPNext permission for every write, whatever `ignore_permissions` the call site
passes, and refuses a direct `submit()` on a document whose doctype has an active Workflow.

What this does NOT cover (see the design letter): raw SQL writes issued by agent code outside the ORM are
refused here (`_make_db_sql`), but the sites themselves are still to be rewritten; the V2
background job and the four whitelisted chat endpoints are separate doors (slice 2).
"""

from __future__ import annotations

import copy
import functools
import hashlib
import re
import time
from contextlib import contextmanager

import frappe

WRITER_ROLE = "AI Agent Operator"

# A confirm is a whole message that is exactly one of these (case and surrounding spaces ignored).
CONFIRM_WORDS = frozenset({"confirm", "confirmar"})
CANCEL_WORDS = frozenset({"cancel", "cancelar"})
PENDING_TTL_SEC = 300

# Read-side effects the agent may always write while answering (replies, its memory, logs).
INFRA_DOCTYPES = frozenset({
    "Raven Message", "AI Memory", "Error Log", "Access Log", "View Log", "Route History",
    "AI Skill Registry", "Bug Report",
    # side effects Frappe itself writes when a judged write or a workflow transition goes through
    "Workflow Action", "Version", "Comment", "Notification Log", "Email Queue", "Email Queue Recipient",
    "Deleted Document",
})

_TRIGGER = re.compile(r"^\s*(@[\w.-]+)\s*(!?)\s*(.*)$", re.S)
_WRITE_SQL = re.compile(r"^\s*(insert|update|delete|replace|truncate|alter|drop|create)\b", re.I)


class AgentWriteBlocked(BaseException):
    """Raised from inside a fenced/armed turn. BaseException on purpose: handler code wraps its work in
    `except Exception:` and would otherwise turn a stopped write into a quiet "error" reply."""

    def __init__(self, reason: str, what: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.what = what


# --------------------------------------------------------------------------------------------- state
def _block(reason: str, what: str):
    """Record the stop on the turn (so a path that swallowed it with a bare `except:` is still caught by
    the door) and raise it."""
    exc = AgentWriteBlocked(reason, what)
    s = _state()
    if s is not None and s.get("blocked") is None:
        s["blocked"] = exc
    raise exc


def _state():
    return getattr(frappe.local, "raven_agent_guard", None)


def confirmed() -> bool:
    """True only while an armed replay is running (a legacy path may ask this instead of reading `!`)."""
    s = _state()
    return bool(s and s["mode"] == "armed")


def is_writer(user: str) -> bool:
    return WRITER_ROLE in frappe.get_roles(user)


# ------------------------------------------------------------------------------------ text helpers
def split_trigger(text: str):
    """('@ai', '!' or '', 'rest') for '@ai !rest'; (None, '', text) when there is no trigger."""
    m = _TRIGGER.match(text or "")
    if not m:
        return None, "", (text or "").strip()
    return m.group(1), m.group(2), m.group(3).strip()


def is_exact_confirm(text: str) -> bool:
    """The whole message is a confirm word (an optional leading trigger is allowed, a `!` is not)."""
    _t, bang, rest = split_trigger(text)
    return not bang and (rest or "").strip().lower() in CONFIRM_WORDS


def is_cancel(text: str) -> bool:
    _t, _bang, rest = split_trigger(text)
    return (rest or "").strip().lower() in CANCEL_WORDS


def _pending_key(user: str, channel_id: str) -> str:
    return f"raven_agent_pending:{user}:{channel_id}"


def _digest(user: str, channel_id: str, text: str) -> str:
    return hashlib.sha256(f"{user}\x1f{channel_id}\x1f{text}".encode()).hexdigest()


def store_pending(user: str, channel_id: str, text: str, what: str, message_name: str = "",
                  via: str = "legacy", payload=None):
    """`via` says which door asked for the confirmation ("legacy", "v2", "api"): only that door replays it.
    `payload` is the stored call of an API endpoint (the digest covers `text`, which the endpoint builds from it)."""
    frappe.cache().set_value(
        _pending_key(user, channel_id),
        {"user": user, "channel": channel_id, "text": text, "what": what, "message": message_name,
         "via": via, "payload": payload, "digest": _digest(user, channel_id, text), "at": time.time()},
        expires_in_sec=PENDING_TTL_SEC,
    )


def peek_pending(user: str, channel_id: str):
    """The pending request without consuming it (None when absent). Used by the door to pick the route."""
    p = frappe.cache().get_value(_pending_key(user, channel_id))
    return p if isinstance(p, dict) else None


def take_pending(user: str, channel_id: str):
    """The pending request for exactly this author and channel, or None. It is consumed either way."""
    key = _pending_key(user, channel_id)
    p = frappe.cache().get_value(key)
    if p:
        frappe.cache().delete_value(key)
    if not p:
        return None
    if p.get("user") != user or p.get("channel") != channel_id:
        return None
    if p.get("digest") != _digest(user, channel_id, p.get("text", "")):
        return None
    if time.time() - float(p.get("at") or 0) > PENDING_TTL_SEC:
        return None
    return p


def has_pending(user: str, channel_id: str) -> bool:
    return bool(frappe.cache().get_value(_pending_key(user, channel_id)))


def clear_pending(user: str, channel_id: str):
    frappe.cache().delete_value(_pending_key(user, channel_id))


def _rollback_to(save_point: str):
    """Roll back to the turn's savepoint. A handler that commits inside the turn releases the savepoint; then a
    plain rollback is all that is left (it can only drop what was not yet committed)."""
    try:
        frappe.db.rollback(save_point=save_point)
    except Exception:
        frappe.db.rollback()


# ---------------------------------------------------------------------------------- the write fence
def _describe(doc_or_doctype, op: str, name: str = "") -> str:
    if hasattr(doc_or_doctype, "doctype"):
        dt, name = doc_or_doctype.doctype, name or (getattr(doc_or_doctype, "name", "") or "")
    else:
        dt = doc_or_doctype
    return f"{op} {dt} {name}".strip()


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


_PTYPE = {"before_insert": "create", "before_save": "write", "before_submit": "submit",
    "before_cancel": "cancel", "on_trash": "delete", "before_update_after_submit": "write"}


def on_write_event(doc, method=None):
    """doc_events["*"] hook. Free when no guarded turn is running."""
    s = _state()
    if not s or doc.doctype in INFRA_DOCTYPES:
        return
    op = {"before_insert": "create", "before_save": "save", "before_submit": "submit",
        "before_cancel": "cancel", "on_trash": "delete", "before_update_after_submit": "update"}.get(method, method)
    # before_save also fires for the first save of a new document, which before_insert already judged
    if method == "before_save" and doc.is_new():
        return
    what = _describe(doc, op)
    if s["mode"] == "fenced":
        _block("fenced", what)
    # armed: the AUTHOR's own rights, whatever ignore flag the call site passed
    user = s["user"]
    ptype = _PTYPE.get(method, "write")
    if not _author_may(doc, ptype, user):
        _block("no_permission", what)
    if method == "before_submit" and _has_active_workflow(doc.doctype) and not frappe.flags.get("raven_agent_via_workflow"):
        _block("needs_workflow_action", what)


def _agent_caller(depth: int) -> bool:
    """True when the frame `depth` levels above the caller of this helper is code of raven_ai_agent (a direct
    write by agent code), as opposed to Frappe's own ORM reaching the same function from frappe/model or
    frappe/database (nested-set updates, db_set inside the ORM...)."""
    import sys

    try:
        f = sys._getframe(depth + 1)
    except ValueError:
        return False
    fn = f.f_code.co_filename.replace("\\", "/")
    return "/raven_ai_agent/" in fn and not fn.endswith("agent_guard.py")


def _direct_write_check(s, dt, dn, what):
    """fenced: stop. armed: the author needs `write` on that very document."""
    if dt in INFRA_DOCTYPES:
        return
    if s["mode"] == "fenced":
        _block("fenced", what)
    if not (isinstance(dn, str) and frappe.has_permission(dt, "write", doc=dn, user=s["user"], throw=False)):
        _block("no_permission", what)


def _make_db_set_value(orig):
    @functools.wraps(orig)
    def wrapper(dt, dn=None, field=None, val=None, *a, **kw):
        s = _state()
        if s and _agent_caller(1):
            _direct_write_check(s, dt, dn, _describe(dt, "set_value", dn if isinstance(dn, str) else ""))
        return orig(dt, dn, field, val, *a, **kw)
    return wrapper


def _make_db_delete(orig):
    @functools.wraps(orig)
    def wrapper(doctype, *a, **kw):
        s = _state()
        if s and doctype not in INFRA_DOCTYPES and _agent_caller(1):
            _block("fenced" if s["mode"] == "fenced" else "refused_bulk_delete", _describe(doctype, "db.delete"))
        return orig(doctype, *a, **kw)
    return wrapper


def _make_doc_db_set(orig):
    @functools.wraps(orig)
    def wrapper(self, *a, **kw):
        s = _state()
        if s and _agent_caller(1):
            _direct_write_check(s, self.doctype, getattr(self, "name", None), _describe(self, "db_set"))
        return orig(self, *a, **kw)
    return wrapper


_INFRA_JOB_PREFIXES = ("raven_ai_agent.bug_reporter.",)


def _make_enqueue(orig):
    @functools.wraps(orig)
    def wrapper(method, *a, **kw):
        s = _state()
        if s and _agent_caller(1):
            name = method if isinstance(method, str) else getattr(method, "__name__", str(method))
            if not name.startswith(_INFRA_JOB_PREFIXES):
                if s["mode"] == "fenced":
                    _block("fenced", f"enqueue {name}")
                # armed: allowed; the job runs as the session user, which is the author in every door
        return orig(method, *a, **kw)
    return wrapper


def _make_db_sql(orig):
    @functools.wraps(orig)
    def wrapper(query, *a, **kw):
        s = _state()
        if s and isinstance(query, str) and _WRITE_SQL.match(query) and _agent_caller(1):
            _block("fenced" if s["mode"] == "fenced" else "refused_raw_sql", "raw SQL write")
        return orig(query, *a, **kw)
    return wrapper


@contextmanager
def guarded_turn(user: str, mode: str):
    """Run a block as `fenced` (nothing may be written) or `armed` (writes obey `user`'s own rights)."""
    assert mode in ("fenced", "armed")
    try:
        from frappe.model.document import Document
    except Exception:                              # mocked frappe (zero-DB tests): no Document class to patch
        Document = None

    db = frappe.db
    saved = {k: db.__dict__.get(k) for k in ("set_value", "delete", "sql")}
    orig_db_set = Document.__dict__.get("db_set") if Document is not None else None
    prev = _state()
    frappe.local.raven_agent_guard = {"mode": mode, "user": user, "blocked": None}
    db.set_value = _make_db_set_value(db.set_value)
    db.delete = _make_db_delete(db.delete)
    db.sql = _make_db_sql(db.sql)
    if orig_db_set is not None:
        Document.db_set = _make_doc_db_set(orig_db_set)
    orig_enqueue = frappe.__dict__.get("enqueue")
    if orig_enqueue is not None:
        frappe.enqueue = _make_enqueue(orig_enqueue)
    try:
        yield frappe.local.raven_agent_guard
    finally:
        if orig_enqueue is not None:
            frappe.enqueue = orig_enqueue
        if orig_db_set is not None:
            Document.db_set = orig_db_set
        for k, v in saved.items():
            if v is None:
                db.__dict__.pop(k, None)
            else:
                setattr(db, k, v)
        frappe.local.raven_agent_guard = prev


# ------------------------------------------------------------------------------------- the one door
def _refusal(blocked: AgentWriteBlocked, writer: bool) -> str:
    if blocked.reason == "no_permission":
        return f"No puedo hacerlo con sus permisos de ERPNext: {blocked.what}. / I cannot do that with your own ERPNext rights: {blocked.what}."
    if blocked.reason == "needs_workflow_action":
        return f"Esa acción debe pasar por el flujo de trabajo, no la ejecuto directamente: {blocked.what}. / That step must go through the workflow action; I do not run it directly: {blocked.what}."
    if blocked.reason in ("refused_raw_sql", "refused_bulk_delete"):
        return f"Ese cambio no está permitido para el agente: {blocked.what}. / The agent is not allowed to make that change: {blocked.what}."
    if not writer:
        return (f"Solo puedo consultar para usted (le falta el rol {WRITER_ROLE}): {blocked.what}. / "
            f"I can only answer read-only for you (the role {WRITER_ROLE} is missing): {blocked.what}.")
    return ""


def run_turn(user: str, channel_id: str, text: str, runner, reply, message_name: str = "", via: str = "legacy"):
    """The whole decision for one message. `runner(text)` runs the legacy path with that message text;
    `reply(channel_id, text)` posts a bot message. Returns True when this function handled the turn."""
    trig, _bang, rest = split_trigger(text)
    writer = is_writer(user)

    # 1. a confirm / cancel word that answers a pending request of THIS author in THIS channel
    if has_pending(user, channel_id):
        if is_exact_confirm(text) and writer:
            pk = peek_pending(user, channel_id)
            if pk and pk.get("via", "legacy") != via:
                reply(channel_id, "La acción pendiente es de otra vía: responda `confirm` solo, como mensaje aparte. / "
                    "The pending action belongs to another route: send `confirm` alone, as a separate message.")
                return True                       # left intact: nothing ran, nothing was cancelled
            p = take_pending(user, channel_id)
            if p:
                return _replay(user, channel_id, p, runner, reply)
            reply(channel_id, "La confirmación expiró o no coincide. / The confirmation expired or does not match.")
            return True
        clear_pending(user, channel_id)          # anything else from the author cancels it
        if is_cancel(text):
            reply(channel_id, "Cancelado. / Cancelled.")
            return True
    elif is_exact_confirm(text) and trig is None:
        return False                              # a bare word with nothing pending is just chat

    if trig is None:
        return False                              # not addressed to the agent: not our business

    # 2. a normal turn: fenced, with any leading `!` removed (it no longer means anything)
    clean = f"{trig} {rest}".strip()
    run_fenced(user, channel_id, clean, runner, reply, writer, message_name, via)
    return True


def _workflow_errors() -> tuple:
    try:
        from frappe.model.workflow import WorkflowPermissionError, WorkflowTransitionError

        return (WorkflowPermissionError, WorkflowTransitionError)
    except Exception:
        return ()                                  # no Frappe workflow module (mocked tests): catches nothing


def _workflow_refusal(exc) -> str:
    return (f"El flujo de trabajo no permite este paso a su usuario: {exc}. No busco otra vía. / "
        f"The workflow does not let your user take this step: {exc}. I do not look for another way.")


def run_fenced(user, channel_id, clean, runner, reply, writer, message_name="", via="legacy"):
    db = frappe.db
    db.savepoint("raven_agent_turn")
    try:
        with guarded_turn(user, "fenced") as st:
            runner(clean)
            if st["blocked"]:
                raise st["blocked"]
    except AgentWriteBlocked as b:
        _rollback_to("raven_agent_turn")
        if writer and b.reason == "fenced":
            store_pending(user, channel_id, clean, b.what, message_name, via=via)
            reply(channel_id, f"Voy a hacer: {b.what}. Responda exactamente `confirm` para ejecutar (5 min). / "
                f"I am about to: {b.what}. Reply exactly `confirm` to run it (5 min).")
        else:
            reply(channel_id, _refusal(b, writer))
    except _workflow_errors() as exc:
        _rollback_to("raven_agent_turn")
        reply(channel_id, _workflow_refusal(exc))
    finally:
        try:
            db.release_savepoint("raven_agent_turn")
        except Exception:
            pass


def _replay(user, channel_id, p, runner, reply):
    trig, _b, rest = split_trigger(p["text"])
    armed_text = f"{trig} !{rest}" if trig else p["text"]
    db = frappe.db
    db.savepoint("raven_agent_replay")
    try:
        with guarded_turn(user, "armed") as st:
            runner(armed_text)
            if st["blocked"]:                      # a path that swallowed the stop with a bare `except:`
                raise st["blocked"]
    except AgentWriteBlocked as b:
        _rollback_to("raven_agent_replay")
        reply(channel_id, _refusal(b, True))
    except _workflow_errors() as exc:
        # the transition's role is not the author's (or nobody holds it): say so, never look for another way
        _rollback_to("raven_agent_replay")
        reply(channel_id, _workflow_refusal(exc))
    return True


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


# -------------------------------------------------------------------------------- legacy-door glue
def guard_door(fn):
    """Decorator for `handle_raven_message(doc, method)` (the Raven Message after_insert door).
    `@ai ...` under the V2 flag goes to the V2 job, which runs the same turn logic itself (pipeline_v2.process_command);
    every other trigger (`@mfg`, `@bot_name`...) runs here, fenced."""

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
        except Exception:
            return fn(doc, method)

        def reply(channel_id, text):
            frappe.get_doc({"doctype": "Raven Message", "channel_id": channel_id, "text": text,
                "message_type": "Text", "is_bot_message": 1}).insert(ignore_permissions=True)

        trig, _bang, _rest = split_trigger(plain)
        try:
            pend = peek_pending(d.owner, d.channel_id)
        except Exception:
            pend = None
        if trig is not None and not agent_enabled(raven=True):
            reply(d.channel_id, OFF_TEXT)
            return None

        try:
            from raven_ai_agent.api import pipeline_v2

            v2 = pipeline_v2.is_enabled()
        except Exception:
            v2 = False
        if v2:
            if trig == "@ai":
                return fn(doc, method)             # ack + enqueue; the job runs the turn
            if trig is None and pend and pend.get("via") == "v2" and is_exact_confirm(plain):
                return pipeline_v2.dispatch(message_name=d.name, channel_id=d.channel_id,
                    query="confirm", user=d.owner)  # a bare `confirm` reaches the job that asked for it

        def runner(t):
            d2 = copy.copy(d)
            d2.text = f"<p>{t}</p>"
            return fn(d2, method)

        handled = run_turn(d.owner, d.channel_id, plain, runner, reply, message_name=d.name)
        if not handled:
            return fn(doc, method)

    return wrapper


# --------------------------------------------------------------------------- the whitelisted endpoints
def _result(shape: str, ok: bool, text: str, **extra):
    body = {"success": ok, "response": text, "guard": True, **extra}
    if shape == "json":
        import json

        return json.dumps(body, default=str)
    return body


def guard_endpoint(endpoint: str, confirm_arg: str, shape: str = "dict"):
    """Decorator for a whitelisted chat endpoint, under `@frappe.whitelist()`. Same two steps as the chat:
    a first call runs FENCED; a write attempt stops it and, for a holder of the role, stores the call and
    answers `needs_confirmation`; a later call whose `confirm_arg` is exactly `confirm` replays the stored
    call ARMED. The author is the session user; the pending key is (author, `api:<endpoint>`)."""
    import inspect

    channel = f"api:{endpoint}"

    def deco(fn):
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*a, **kw):
            user = frappe.session.user
            if not agent_enabled():
                return _result(shape, False, OFF_TEXT, agent_off=True)
            args = dict(sig.bind_partial(*a, **kw).arguments)
            extra = args.pop("kwargs", None) or {}
            flat = {**args, **extra}
            word = str(flat.get(confirm_arg) or "")
            writer = is_writer(user)
            if has_pending(user, channel):
                if is_exact_confirm(word) and writer:
                    p = take_pending(user, channel)
                    if not p:
                        return _result(shape, False, "La confirmación expiró o no coincide. / The confirmation expired or does not match.")
                    db = frappe.db
                    db.savepoint("raven_agent_api")
                    try:
                        with guarded_turn(user, "armed") as st:
                            res = fn(**p["payload"])
                            if st["blocked"]:
                                raise st["blocked"]
                        return res
                    except AgentWriteBlocked as b:
                        _rollback_to("raven_agent_api")
                        return _result(shape, False, _refusal(b, True), refused=b.reason)
                    except _workflow_errors() as exc:
                        _rollback_to("raven_agent_api")
                        return _result(shape, False, _workflow_refusal(exc), refused="workflow")
                clear_pending(user, channel)
            import json

            db = frappe.db
            db.savepoint("raven_agent_api")
            try:
                with guarded_turn(user, "fenced") as st:
                    res = fn(*a, **kw)
                    if st["blocked"]:
                        raise st["blocked"]
                return res
            except AgentWriteBlocked as b:
                _rollback_to("raven_agent_api")
                if writer and b.reason == "fenced":
                    store_pending(user, channel, json.dumps(flat, sort_keys=True, default=str), b.what,
                        via="api", payload=flat)
                    return _result(shape, False,
                        f"Voy a hacer: {b.what}. Llame de nuevo con {confirm_arg}=\"confirm\" (5 min). / "
                        f"I am about to: {b.what}. Call again with {confirm_arg}=\"confirm\" (5 min).",
                        needs_confirmation=True, preview=b.what)
                return _result(shape, False, _refusal(b, writer), refused=b.reason, read_only=not writer)
            except _workflow_errors() as exc:
                _rollback_to("raven_agent_api")
                return _result(shape, False, _workflow_refusal(exc), refused="workflow")

        return wrapper

    return deco


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


def _active_workflow(doctype: str):
    try:
        name = frappe.db.get_value("Workflow", {"document_type": doctype, "is_active": 1})
        return frappe.get_cached_doc("Workflow", name) if name else None
    except Exception:
        return None


def _author_roles() -> set:
    st = _state()
    return set(frappe.get_roles(st["user"] if st else None))


def _move_doc(doc, target: int):
    """submit (target 1) / cancel (target 2) a document the way its Workflow wants it, for the author.
    Outside a guarded turn: the plain call, unchanged. In a turn: a doctype without an active Workflow takes the plain
    call (the armed hook checks the author's own right); with one, the transition that leaves the current state for a
    state of that docstatus, allowed to the author's roles, is applied through `apply_workflow_action`. No such
    transition = refuse with the workflow's own reason, naming the roles; a role nobody holds is reported, never
    worked around."""
    plain = doc.submit if target == 1 else doc.cancel
    if not _state():
        return plain()
    wf = _active_workflow(doc.doctype)
    if not wf:
        return plain()
    from frappe.model.workflow import WorkflowPermissionError

    state_field = wf.workflow_state_field or "workflow_state"
    current = doc.get(state_field)
    docstatus_of = {r.state: int(r.doc_status) for r in wf.states}
    here = [t for t in wf.transitions if t.state == current and docstatus_of.get(t.next_state) == target]
    roles = _author_roles()
    ok = [t for t in here if t.allowed in roles]
    if not ok:
        if here:
            names = ", ".join(sorted({t.allowed for t in here}))
            holders = {
                r: frappe.db.count("Has Role", {"role": r, "parenttype": "User"}) for r in {t.allowed for t in here}
            }
            empty = [r for r, n in holders.items() if not n]
            more = f" (nobody holds: {', '.join(sorted(empty))})" if empty else ""
            frappe.throw(
                f"The workflow of {doc.doctype} lets only {names} take this step{more}; your roles do not include it.",
                WorkflowPermissionError,
            )
        frappe.throw(
            f"The workflow of {doc.doctype} has no single step from '{current}' that "
            f"{'submits' if target == 1 else 'cancels'} the document; the agent does not walk a workflow.",
            WorkflowPermissionError,
        )
    return apply_workflow_action(doc, ok[0].action)


def submit_doc(doc):
    return _move_doc(doc, 1)


def cancel_doc(doc):
    return _move_doc(doc, 2)
