# Copyright (c) 2026, Raven AI Agent and contributors
# For license information, please see license.txt

"""
Alexa to Raven API endpoint.

This module provides the entry point for Alexa middleware to send
voice commands into Raven channels where the AI agent can process them.
"""

import frappe
from frappe import _

# Import the channel utility function for posting to Raven
from raven_ai_agent.api.channel_utils import post_message_to_channel


def _validate_bearer_or_token():
    """Validate incoming request auth (API key/secret or bearer token)."""
    auth = frappe.get_request_header("Authorization")
    if not auth:
        frappe.throw(_("Missing Authorization header"), frappe.PermissionError)

    # Accept "token key:secret" or "Bearer <token>"
    if auth.startswith("token "):
        return
    if auth.startswith("Bearer "):
        return

    frappe.throw(_("Invalid Authorization header"), frappe.PermissionError)


def _resolve_alexa_user(alexa_user_id: str) -> dict:
    """Return mapping doc for the given Alexa user id, or error."""
    if not alexa_user_id:
        frappe.throw(_("Missing alexa_user"), frappe.ValidationError)

    mapping = frappe.get_all(
        "Alexa User Mapping",
        filters={"alexa_user_id": alexa_user_id, "enabled": 1},
        fields=["name", "frappe_user", "default_workspace", "default_channel"],
        limit=1,
    )
    if not mapping:
        frappe.throw(
            _("No Alexa User Mapping found for id {0}").format(alexa_user_id),
            frappe.DoesNotExistError,
        )
    return mapping[0]


@frappe.whitelist(allow_guest=False, methods=["POST"])
def alexa_to_raven():
    """
    Entry point for Alexa middleware.

    Expected JSON body:
    {
      "alexa_user": "amzn1.account.ABC123",
      "text": "create a sales order for John for 10 units of item X",
      "intent": "FreeFormIntent",
      "slots": {...},
      "session_id": "alexa-session-uuid"
    }

    Returns:
    {
      "ok": True,
      "channel": "alexa-commands",
      "message_id": "<raven_message_name>"
    }
    """
    _validate_bearer_or_token()

    data = frappe.request.get_json() or {}
    alexa_user = data.get("alexa_user")
    text = (data.get("text") or "").strip()
    intent = data.get("intent")
    session_id = data.get("session_id")

    if not text:
        frappe.throw(_("Missing text from Alexa request"), frappe.ValidationError)

    mapping = _resolve_alexa_user(alexa_user)
    channel_name = mapping.get("default_channel") or "alexa-commands"
    frappe_user = mapping.get("frappe_user")

    # Compose message for Raven agent
    # The @ai tag triggers the AI agent to respond
    message = f"@ai from Alexa (user {frappe_user}): {text}"

    # Post into Raven channel using the channel utility
    result = post_message_to_channel(
        channel_name=channel_name,
        message=message,
        as_bot="alexa_bot",  # The bot name configured in Raven
    )

    # Log the request for auditing
    _log_alexa_request(
        alexa_user_id=alexa_user,
        frappe_user=frappe_user,
        text=text,
        intent=intent,
        session_id=session_id,
        channel=channel_name,
        status="Sent",
    )

    return {
        "ok": True,
        "channel": channel_name,
        "message_id": result.get("name") if isinstance(result, dict) else None,
    }


def _log_alexa_request(
    alexa_user_id: str,
    frappe_user: str,
    text: str,
    intent: str | None,
    session_id: str | None,
    channel: str,
    status: str,
):
    """
    Log Alexa request for auditing purposes.
    
    If Alexa Request Log DocType exists, create a log entry.
    Otherwise, just log to the error log for debugging.
    """
    try:
        if frappe.db.exists("DocType", "Alexa Request Log"):
            frappe.get_doc(
                {
                    "doctype": "Alexa Request Log",
                    "alexa_user_id": alexa_user_id,
                    "frappe_user": frappe_user,
                    "text": text,
                    "intent": intent,
                    "session_id": session_id,
                    "channel": channel,
                    "status": status,
                }
            ).insert(ignore_permissions=True)
        else:
            # Fallback: log to error log
            frappe.log_error(
                title="Alexa Request",
                message=f"User: {frappe_user}, Channel: {channel}, Text: {text}",
            )
    except Exception as e:
        # Don't fail the main request if logging fails
        frappe.log_error(
            title="Alexa Request Log Error",
            message=str(e),
        )
