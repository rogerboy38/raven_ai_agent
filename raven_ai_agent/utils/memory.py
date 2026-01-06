"""Memory management utilities"""
import frappe
from datetime import datetime, timedelta


def generate_daily_summaries():
    """Scheduled job: Generate daily summaries for all users with memories"""
    settings = frappe.get_single("AI Agent Settings")
    
    if not settings.generate_daily_summaries:
        return
    
    # Get users with memories from today
    users = frappe.db.sql("""
        SELECT DISTINCT user FROM `tabAI Memory`
        WHERE DATE(creation) = CURDATE()
    """, as_dict=True)
    
    for user_data in users:
        generate_user_summary(user_data.user)


def generate_user_summary(user: str):
    """Generate summary for a specific user"""
    from raven_ai_agent.api.agent import RaymondLucyAgent
    
    # Get today's memories
    memories = frappe.get_list(
        "AI Memory",
        filters={
            "user": user,
            "creation": [">=", datetime.now().replace(hour=0, minute=0, second=0)]
        },
        fields=["content", "importance", "memory_type"]
    )
    
    if not memories:
        return
    
    agent = RaymondLucyAgent(user)
    agent.end_session([{"role": "system", "content": str(memories)}])


def cleanup_old_memories():
    """Remove expired and old non-critical memories"""
    settings = frappe.get_single("AI Agent Settings")
    retention_days = settings.memory_retention_days or 90
    
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    
    # Delete expired memories
    frappe.db.delete("AI Memory", {
        "expires_on": ["<", datetime.now().date()],
        "expires_on": ["is", "set"]
    })
    
    # Delete old low-importance memories
    frappe.db.delete("AI Memory", {
        "creation": ["<", cutoff_date],
        "importance": ["in", ["Low", "Normal"]]
    })
    
    frappe.db.commit()


def search_similar_memories(user: str, query: str, limit: int = 5):
    """Search memories using keyword matching (upgrade to vector for production)"""
    return frappe.get_list(
        "AI Memory",
        filters={
            "user": user,
            "content": ["like", f"%{query}%"]
        },
        fields=["name", "content", "importance", "memory_type", "source", "creation"],
        order_by="importance desc, creation desc",
        limit=limit
    )
