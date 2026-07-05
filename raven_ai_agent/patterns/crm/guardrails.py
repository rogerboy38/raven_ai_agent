"""
raven_ai_agent/patterns/guardrails.py
═══════════════════════════════════════════════════════════════════════════════
Pre-flight action policy gate for raven_ai_agent sub-agents.

This module is the single source of truth for "is this agent allowed to do X?"
across the entire raven_ai_agent skill ecosystem. Every sub-agent that performs
a write — `crm_agent`, `formulation_orchestrator`, `iot_sensor_manager`, etc. —
should call `is_action_allowed(...)` before touching a DocType.

────────────────────────────────────────────────────────────────────────────────
DESIGN RATIONALE
────────────────────────────────────────────────────────────────────────────────

Research across NVIDIA NeMo Guardrails, Guardrails AI, LangGraph, AutoGen,
CrewAI, the OpenAI Agents SDK, and Anthropic's "Building Effective Agents"
essay converges on a single conceptual split:

    POLICY EVALUATION  ──►  is the action permitted at this autonomy level?
                            (separate from execution)
    EXECUTION GATING   ──►  pause / log / interrupt / auto-reject
                            (separate from policy)

This module implements POLICY EVALUATION. Execution gating is the caller's job
(usually a `try/except` around the actual `frappe.get_doc(...).save()`).

────────────────────────────────────────────────────────────────────────────────
LOOKUP ORDER (deterministic, top-to-bottom)
────────────────────────────────────────────────────────────────────────────────

    1. AI Action Policy row matching (skill=X, action=Y)        ← most specific
    2. AI Action Policy row matching (skill="*", action=Y)      ← wildcard
    3. _DEFAULT_POLICY ladder dict in this file                  ← hardcoded
    4. STAGE_MOVE (3) if action is completely unknown            ← conservative

If any of step 1-3 raises an exception, the function logs a `frappe.log_error`
and falls back to step 3. It NEVER raises to the caller — agents must be able
to assume `is_action_allowed()` returns a bool, period.

────────────────────────────────────────────────────────────────────────────────
AUTONOMY LADDER (mirrors PR #16)
────────────────────────────────────────────────────────────────────────────────

    0  OBSERVE       read-only; no writes whatsoever
    1  SUGGEST       (default) may draft text, suggest actions, but not persist
    2  ENRICH        may write enrichment fields, log notes, capture meetings
    3  STAGE_MOVE    may advance pipeline stages (Opportunity status, etc.)
    4  AUTONOMOUS    may send external messages, emails, assign users

Defaults are conservative: an unknown action requires STAGE_MOVE (level 3).
Operators can loosen via AI Action Policy if they want, but the default
posture is "deny unless explicitly known to be safe at a lower level".

────────────────────────────────────────────────────────────────────────────────
UPGRADE PATHS (signature-stable)
────────────────────────────────────────────────────────────────────────────────

v0.2 — LangGraph interrupt() for require_human_approval:
    When a policy row sets require_human_approval=1, instead of allowing-and-
    logging, raise a LangGraph interrupt payload that surfaces the pending
    action to a Raven channel with Approve/Reject buttons. The public
    `is_action_allowed()` signature does NOT change — the interrupt is raised
    inside `_evaluate_policy()`.

    See: https://docs.langchain.com/oss/python/langgraph/interrupts

v0.3 — NeMo Guardrails Colang flow evaluation:
    Replace `_evaluate_policy()` body with an `LLMRails.generate()` call that
    consults a Colang flow. Useful when "is this action safe?" needs LLM
    judgement (e.g. content-policy violations in draft emails). Again, the
    public signature does NOT change.

    See: https://github.com/NVIDIA/NeMo-Guardrails

────────────────────────────────────────────────────────────────────────────────
REFERENCES
────────────────────────────────────────────────────────────────────────────────
- Anthropic — Building Effective Agents (Dec 2024)
  https://www.anthropic.com/engineering/building-effective-agents
- OpenAI Agents SDK — Human in the Loop
  https://openai.github.io/openai-agents-python/human_in_the_loop/
- OpenAI Agents SDK — Tools (needs_approval)
  https://openai.github.io/openai-agents-python/tools/
- LangGraph — Interrupts
  https://docs.langchain.com/oss/python/langgraph/interrupts
- ReAct paper (Yao et al., ICLR 2023): https://arxiv.org/abs/2210.03629

Module is part of the raven_ai_agent v14.1.0 release line.
"""

from __future__ import annotations

import json
import traceback
from typing import Any

import frappe


# ═══════════════════════════════════════════════════════════════════════════════
# Autonomy-level constants — PUBLIC API, mirrors the PR #16 ladder
# ═══════════════════════════════════════════════════════════════════════════════
# These integer constants are exposed at module level so callers can write:
#
#     from raven_ai_agent.patterns.crm.guardrails import STAGE_MOVE, is_action_allowed
#     if is_action_allowed("opportunity_mover", "stage_move", STAGE_MOVE):
#         opp.status = "Quotation"
#         opp.save()
#
# The numeric values MUST match `CRMAgentBase._autonomy` semantics in
# skills/crm_agent/agents/base.py — do not renumber without coordinating.

OBSERVE: int = 0
SUGGEST: int = 1
ENRICH: int = 2
STAGE_MOVE: int = 3
AUTONOMOUS: int = 4

# Human-readable labels for audit log enrichment.
AUTONOMY_LABELS: dict[int, str] = {
    OBSERVE: "observe",
    SUGGEST: "suggest",
    ENRICH: "enrich",
    STAGE_MOVE: "stage_move",
    AUTONOMOUS: "autonomous",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Default policy ladder
# ═══════════════════════════════════════════════════════════════════════════════
# Maps action keyword → minimum autonomy level required.
#
# This dict is the single source of truth when no AI Action Policy row exists.
# When you add a new action keyword to any skill, ADD IT HERE TOO so the gate
# has a sensible default. Otherwise the conservative fallback (STAGE_MOVE) will
# block the action at default autonomy level 1.
#
# Naming convention: lowercase, snake_case. Match the action label that the
# calling sub-agent passes to `can_act()` / `is_action_allowed()`.

_DEFAULT_POLICY: dict[str, int] = {
    # ── read / observe ────────────────────────────────────────────────────
    "read":              OBSERVE,
    "fetch":             OBSERVE,
    "list":              OBSERVE,
    "search":            OBSERVE,
    "summarize":         OBSERVE,
    "describe":          OBSERVE,

    # ── suggest / draft (no persistence) ──────────────────────────────────
    "draft":             SUGGEST,
    "suggest":           SUGGEST,
    "score":             SUGGEST,
    "recommend":         SUGGEST,
    "preview":           SUGGEST,

    # ── enrich / log (writes fields, logs notes) ──────────────────────────
    "enrich":            ENRICH,
    "log":               ENRICH,
    "log_note":          ENRICH,
    "create_note":       ENRICH,
    "create_activity":   ENRICH,
    "capture_meeting":   ENRICH,
    "update_field":      ENRICH,
    "link":              ENRICH,

    # ── stage moves (changes business state) ──────────────────────────────
    "stage_move":        STAGE_MOVE,
    "move_stage":        STAGE_MOVE,
    "update_status":     STAGE_MOVE,
    "qualify_lead":      STAGE_MOVE,
    "convert_lead":      STAGE_MOVE,
    "set_amount":        STAGE_MOVE,
    "create_lead":       STAGE_MOVE,
    "create_opportunity": STAGE_MOVE,

    # ── autonomous / external (sends, assigns, deletes) ──────────────────
    "send":              AUTONOMOUS,
    "send_email":        AUTONOMOUS,
    "send_message":      AUTONOMOUS,
    "create_task":       AUTONOMOUS,
    "assign_user":       AUTONOMOUS,
    "delete":            AUTONOMOUS,
}

# DocType names used for policy storage + audit. Defined as constants so
# a global rename only touches this file.
_POLICY_DOCTYPE: str = "AI Action Policy"
_AUDIT_DOCTYPE: str = "AI Routing Audit Log"


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def is_action_allowed(
    skill: str,
    action: str,
    autonomy_level: int,
    context: dict[str, Any] | None = None,
) -> bool:
    """
    Evaluate whether *skill* may execute *action* at the given *autonomy_level*.

    This is THE function every sub-agent calls before a write. It always
    returns a bool — it NEVER raises. On any internal error it falls back
    to the default ladder integer comparison and logs the error via
    `frappe.log_error`.

    Parameters
    ----------
    skill : str
        Snake_case skill identifier matching the sub-agent's `self.skill_name`
        or `CRMAgentBase.skill_name`. Examples: "crm_agent", "lead_enricher",
        "opportunity_mover", "follow_up_writer".
    action : str
        Action keyword the skill is about to perform. Must match a key in
        `_DEFAULT_POLICY` (above) OR have a corresponding AI Action Policy
        row. Unknown actions fall back to STAGE_MOVE (3) — conservative deny.
    autonomy_level : int
        Current autonomy level of the skill instance (0–4). Typically set
        per-skill in CRM Agent Settings or per-message via Raven UI.
    context : dict | None
        Optional payload included in the audit log row (DocType + name,
        truncated to 2000 chars when serialized). Safe to pass `frappe.local`
        bits; we json-serialize with `default=str`.

    Returns
    -------
    bool
        True if the action is permitted, False if it should be blocked.

    Side effects
    ------------
    Writes one row to `AI Routing Audit Log` if that DocType exists. Audit
    failures are logged via `frappe.log_error` but never propagate.

    Examples
    --------
    >>> # Inside CRMAgentBase.can_act
    >>> from raven_ai_agent.patterns.crm.guardrails import is_action_allowed
    >>> if not is_action_allowed("opportunity_mover", "stage_move", self._autonomy):
    ...     return False
    >>> # ... proceed with opp.save() ...
    """
    # Coerce autonomy_level defensively; sub-agents sometimes pass strings.
    try:
        autonomy_level = int(autonomy_level)
    except (TypeError, ValueError):
        autonomy_level = SUGGEST  # safest default

    try:
        allowed, reason = _evaluate_policy(skill, action, autonomy_level)
    except Exception:
        # Graceful degradation: log the exception, fall back to the bare
        # ladder comparison. This matches the existing try/except pattern
        # in PR #16 call sites — but now we leave a trace.
        try:
            frappe.log_error(
                title=f"[guardrails] policy eval error: {skill}.{action}",
                message=traceback.format_exc(),
            )
        except Exception:
            pass  # frappe.log_error itself may fail during test stubs

        required = _DEFAULT_POLICY.get(action, STAGE_MOVE)
        allowed = autonomy_level >= required
        reason = f"fallback (exception): autonomy {autonomy_level} >= required {required}"

    _write_audit_log(skill, action, autonomy_level, allowed, reason, context or {})
    return allowed


def get_required_level(action: str) -> int:
    """
    Return the default minimum autonomy level for *action*.

    Convenience helper for sub-agents that want to display "this requires
    level N" in error messages without re-implementing the lookup.
    Unknown actions return STAGE_MOVE (3) — the conservative default.

    Examples
    --------
    >>> get_required_level("draft")
    1
    >>> get_required_level("send_email")
    4
    >>> get_required_level("totally_unknown")
    3
    """
    return _DEFAULT_POLICY.get(action, STAGE_MOVE)


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _evaluate_policy(
    skill: str,
    action: str,
    autonomy_level: int,
) -> tuple[bool, str]:
    """
    Core policy evaluation. Returns (allowed, human-readable reason).

    Lookup order (first match wins):
      1. AI Action Policy row matching (skill, action) exactly
      2. AI Action Policy row matching ("*", action)
      3. _DEFAULT_POLICY dict (fallback)

    Anything raised here is caught by `is_action_allowed()` and routed
    through the fault-tolerant fallback path.
    """
    # Step 1+2: look up policy row, then wildcard
    policy = _get_policy_row(skill, action) or _get_policy_row("*", action)

    if policy:
        if policy.get("blocked"):
            return False, f"policy blocked: {policy.get('notes') or 'no notes'}"

        min_level = int(policy.get("min_autonomy_level") or 0)
        if autonomy_level < min_level:
            return (
                False,
                f"policy requires autonomy>={min_level}, got {autonomy_level}",
            )

        if policy.get("require_human_approval"):
            # v0.1 behaviour: allow + flag in audit log (an external workflow
            # rule or BG job can intercept the audit row and surface approval
            # UI). v0.3 will replace this with a LangGraph interrupt().
            return True, "allowed (human approval flagged in audit log)"

        return True, f"policy allows (min_level={min_level})"

    # Step 3: fall back to hardcoded ladder
    required = _DEFAULT_POLICY.get(action, STAGE_MOVE)
    if autonomy_level >= required:
        return True, f"ladder: {autonomy_level} >= {required}"
    return False, f"ladder: {autonomy_level} < {required} required for '{action}'"


def _get_policy_row(skill: str, action: str) -> dict | None:
    """
    Fetch a single AI Action Policy row.

    Returns None if:
      - The DocType doesn't exist yet (fresh install before migration)
      - No matching row is found
      - Anything fails (returns None silently — caller falls back to ladder)
    """
    try:
        if not frappe.db.table_exists(f"tab{_POLICY_DOCTYPE}"):
            return None
        row = frappe.db.get_value(
            _POLICY_DOCTYPE,
            {"skill": skill, "action": action},
            ["min_autonomy_level", "require_human_approval", "blocked", "notes"],
            as_dict=True,
        )
        return dict(row) if row else None
    except Exception:
        # Don't leak; ladder fallback in caller is fine.
        return None


def _write_audit_log(
    skill: str,
    action: str,
    autonomy_level: int,
    allowed: bool,
    reason: str,
    context: dict,
) -> None:
    """
    Insert one row into AI Routing Audit Log.

    Best-effort: if the DocType doesn't exist, or the insert fails, we
    log via `frappe.log_error` but never raise to the caller.

    Why `ignore_permissions=True`:
      The audit log is a security/compliance artifact. A user must not
      be able to suppress their own audit trail by virtue of not having
      write permission on the audit DocType. Read permission on this
      DocType should be restricted to System Manager / Audit roles via
      the DocType's perm tab.
    """
    try:
        if not frappe.db.table_exists(f"tab{_AUDIT_DOCTYPE}"):
            return

        try:
            user = frappe.session.user
        except Exception:
            user = "Guest"

        # Serialize context defensively — datetime, Document, set, etc.
        try:
            context_json = json.dumps(context, default=str)[:2000]
        except Exception:
            context_json = "<unserializable>"

        doc = frappe.get_doc({
            "doctype": _AUDIT_DOCTYPE,
            "skill": skill,
            "action": action,
            "autonomy_level": autonomy_level,
            "autonomy_label": AUTONOMY_LABELS.get(autonomy_level, str(autonomy_level)),
            "allowed": 1 if allowed else 0,
            "decision": "allowed" if allowed else "blocked",
            "reason": (reason or "")[:500],
            "context_json": context_json,
            "user": user,
        })
        doc.insert(ignore_permissions=True)
    except Exception:
        # Audit write must never bubble. We log and move on.
        try:
            frappe.log_error(
                title="[guardrails] audit log write failed",
                message=traceback.format_exc(),
            )
        except Exception:
            pass
