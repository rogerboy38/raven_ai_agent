import frappe
from frappe import _
from typing import Optional, Dict, Any


def publish_message_created_event(message_doc, channel_id: str) -> None:
    """
    Publish a realtime event when a new Raven Message is created.
    
    This function uses the same event format as the official Raven application
    (see raven/raven_messaging/doctype/raven_message/raven_message.py).
    
    This ensures that messages sent by the AI agent appear in the UI
    immediately without requiring a page refresh.
    
    Args:
        message_doc: The Raven Message document that was just inserted
        channel_id: The channel ID where the message was sent
    
    Usage:
        from raven_ai_agent.api.channel_utils import publish_message_created_event
        
        message = frappe.get_doc({
            "doctype": "Raven Message",
            "channel_id": channel_id,
            "text": "Hello!",
            "message_type": "Text"
        })
        message.insert(ignore_permissions=True)
        frappe.db.commit()
        
        # Publish realtime event so UI updates immediately
        publish_message_created_event(message, channel_id)
    """
    frappe.publish_realtime(
        "message_created",
        {
            "channel_id": channel_id,
            "sender": frappe.session.user,
            "message_id": message_doc.name,
            "message_details": _get_message_details(message_doc),
        },
        doctype="Raven Channel",
        docname=channel_id,
        after_commit=True,
    )


def _get_message_details(message_doc) -> Dict[str, Any]:
    """
    Extract message details in the format expected by Raven frontend.
    
    This helper safely extracts attributes, providing None for missing fields.
    """
    def safe_get(attr: str, default=None):
        """Safely get attribute from document"""
        return getattr(message_doc, attr, default) if hasattr(message_doc, attr) else default
    
    return {
        "text": safe_get("text"),
        "channel_id": safe_get("channel_id"),
        "content": safe_get("content"),
        "file": safe_get("file"),
        "message_type": safe_get("message_type", "Text"),
        "is_edited": 1 if safe_get("is_edited") else 0,
        "is_thread": safe_get("is_thread", 0),
        "is_forwarded": safe_get("is_forwarded", 0),
        "is_reply": safe_get("is_reply", 0),
        "poll_id": safe_get("poll_id"),
        "creation": str(message_doc.creation) if hasattr(message_doc, 'creation') else None,
        "owner": safe_get("owner"),
        "modified_by": safe_get("modified_by"),
        "modified": str(message_doc.modified) if hasattr(message_doc, 'modified') else None,
        "linked_message": safe_get("linked_message"),
        "replied_message_details": safe_get("replied_message_details"),
        "link_doctype": safe_get("link_doctype"),
        "link_document": safe_get("link_document"),
        "message_reactions": safe_get("message_reactions"),
        "thumbnail_width": safe_get("thumbnail_width"),
        "thumbnail_height": safe_get("thumbnail_height"),
        "file_thumbnail": safe_get("file_thumbnail"),
        "image_width": safe_get("image_width"),
        "image_height": safe_get("image_height"),
        "name": message_doc.name,
        "is_bot_message": 1 if safe_get("is_bot_message") else 0,
        "bot": safe_get("bot"),
        "hide_link_preview": safe_get("hide_link_preview", 0),
        "blurhash": safe_get("blurhash"),
    }

@frappe.whitelist()
def get_channels_for_bot(bot_user_id=None, hide_archived=True):
    """
    Get all channels where a specific bot is a member.
    This is used for Document Notification channel selection.
    
    Args:
        bot_user_id: The user ID of the bot (e.g., 'sales_order_bot')
        hide_archived: Whether to hide archived channels
    
    Returns:
        List of channels where the bot is a member
    """
    if not bot_user_id:
        return []
    
    # Get all channel memberships for the bot
    channel_member = frappe.qb.DocType("Raven Channel Member")
    channel = frappe.qb.DocType("Raven Channel")
    
    query = (
        frappe.qb.from_(channel)
        .inner_join(channel_member)
        .on(channel.name == channel_member.channel_id)
        .select(
            channel.name,
            channel.channel_name,
            channel.type,
            channel.workspace,
            channel.is_archived,
            channel.is_dm_thread,
            channel.is_self_message,
        )
        .where(channel_member.user_id == bot_user_id)
        .where(channel.is_dm_thread == 0)
        .where(channel.is_self_message == 0)
        .where(channel.is_thread == 0)
    )
    
    if hide_archived:
        query = query.where(channel.is_archived == 0)
    
    query = query.orderby(channel.channel_name)
    
    return query.run(as_dict=True)


@frappe.whitelist()
def get_all_non_dm_channels(hide_archived=True):
    """
    Get ALL non-DM channels in the system (for admin use).
    Bypasses the user membership filter.
    
    Returns:
        List of all channels that are not DMs
    """
    channel = frappe.qb.DocType("Raven Channel")
    
    query = (
        frappe.qb.from_(channel)
        .select(
            channel.name,
            channel.channel_name,
            channel.type,
            channel.workspace,
            channel.is_archived,
        )
        .where(channel.is_dm_thread == 0)
        .where(channel.is_self_message == 0)
        .where(channel.is_thread == 0)
    )
    
    if hide_archived:
        query = query.where(channel.is_archived == 0)
    
    query = query.orderby(channel.channel_name)
    
    return query.run(as_dict=True)
