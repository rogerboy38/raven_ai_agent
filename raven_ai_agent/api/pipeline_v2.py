"""
Pipeline V2 — async dispatch of @ai chat commands to RaymondLucyAgentV2.

Phase R1 of the "raven smarter" remake (see RAVEN_SMARTER_REVIEW.md):
- Instant acknowledgement message, then processing in a background job
  (frappe.enqueue) instead of blocking Raven Message.after_insert.
- One dispatcher: skills-first (COA / Data Quality Scanner behavior is
  preserved because SkillRouter runs inside RaymondLucyAgentV2.process_query),
  then patterns IntelligenceLayer, then provider LLM with fallback chain.
- Every command writes an AI Routing Audit Log row.

Enabled per-site via AI Agent Settings.agent_pipeline_v2_enabled.
"""

import time
import uuid

import frappe

ACK_TEXT = "🤔 Working on it…"


def is_enabled(settings=None) -> bool:
    """Cheap flag check usable inside the after_insert hook."""
    try:
        value = frappe.db.get_single_value(
            "AI Agent Settings", "agent_pipeline_v2_enabled"
        )
        return bool(int(value or 0))
    except Exception:
        return False


def dispatch(message_name: str, channel_id: str, query: str, user: str) -> None:
    """Called from handle_raven_message. Ack + enqueue. Must stay fast."""
    request_id = uuid.uuid4().hex[:12]
    ack_name = None
    try:
        if frappe.db.get_single_value("AI Agent Settings", "pipeline_ack_enabled"):
            ack = frappe.get_doc(
                {
                    "doctype": "Raven Message",
                    "channel_id": channel_id,
                    "text": ACK_TEXT,
                    "message_type": "Text",
                    "is_bot_message": 1,
                }
            )
            ack.insert(ignore_permissions=True)
            ack_name = ack.name
    except Exception:
        frappe.logger().warning("[Pipeline V2] ack insert failed", exc_info=True)

    frappe.enqueue(
        "raven_ai_agent.api.pipeline_v2.process_command",
        queue="short",
        timeout=300,
        request_id=request_id,
        message_name=message_name,
        channel_id=channel_id,
        query=query,
        user=user,
        ack_name=ack_name,
    )


def process_command(
    request_id: str,
    message_name: str,
    channel_id: str,
    query: str,
    user: str,
    ack_name: str = None,
) -> None:
    """Background job: run V2 agent, reply, audit. Never raises."""
    from raven_ai_agent.api.agent_v2 import RaymondLucyAgentV2

    started = time.monotonic()
    status, intent, skill, error_text, response = "Failed", None, None, None, None

    try:
        agent = RaymondLucyAgentV2(user=user)
        result = agent.process_query(query)
        response = result.get("response") or "I could not produce an answer."
        status = "Routed" if result.get("success") else "Failed"
        skill = result.get("skill_used")
        intent = (result.get("context_used") or {}).get("pattern") or (
            "skill" if skill else "llm"
        )
    except Exception as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        frappe.logger().error(f"[Pipeline V2] {request_id} failed", exc_info=True)
        response = (
            "⚠️ Something went wrong while processing your request. "
            f"It has been logged (ref `{request_id}`)."
        )
        try:
            from raven_ai_agent.bug_reporter.collector import capture

            capture(exception=exc, query=query, user=user, intent="pipeline_v2", failure_class="exception")
        except Exception:
            pass

    latency_ms = int((time.monotonic() - started) * 1000)

    try:
        frappe.get_doc(
            {
                "doctype": "Raven Message",
                "channel_id": channel_id,
                "text": response,
                "message_type": "Text",
                "is_bot_message": 1,
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.logger().error(f"[Pipeline V2] {request_id} reply insert failed", exc_info=True)

    if ack_name:
        try:
            frappe.delete_doc("Raven Message", ack_name, ignore_permissions=True, force=True)
        except Exception:
            pass

    try:
        frappe.get_doc(
            {
                "doctype": "AI Routing Audit Log",
                "request_id": request_id,
                "source_channel": channel_id,
                "routing_status": status,
                "resolved_intent": intent,
                "selected_skill": skill,
                "raw_input": query[:2000],
                "latency_ms": latency_ms,
                "error_text": error_text,
                "reference_doctype": "Raven Message",
                "reference_name": message_name,
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.logger().warning(f"[Pipeline V2] {request_id} audit insert failed", exc_info=True)

    frappe.db.commit()
