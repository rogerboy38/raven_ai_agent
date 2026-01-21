import frappe
from frappe import _

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
