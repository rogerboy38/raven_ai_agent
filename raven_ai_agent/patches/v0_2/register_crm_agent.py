"""
Patch — register crm_agent skill + create AI Agent Settings custom fields.

Idempotent. Safe to re-run.
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CRM_FIELDS = {
    "AI Agent Settings": [
        {
            "fieldname": "crm_section",
            "fieldtype": "Section Break",
            "label": "CRM Agent",
            "insert_after": "ollama_model",
        },
        {
            "fieldname": "crm_autonomy_level",
            "fieldtype": "Int",
            "label": "CRM Autonomy Level",
            "default": 1,
            "description": "0=observe, 1=suggest, 2=draft, 3=act, 4=autonomous",
            "insert_after": "crm_section",
        },
        {
            "fieldname": "crm_digest_channel",
            "fieldtype": "Link",
            "options": "Raven Channel",
            "label": "CRM Digest Channel",
            "description": "Where the daily pipeline digest is posted",
            "insert_after": "crm_autonomy_level",
        },
        {
            "fieldname": "crm_column_break",
            "fieldtype": "Column Break",
            "insert_after": "crm_digest_channel",
        },
        {
            "fieldname": "crm_default_pipeline",
            "fieldtype": "Data",
            "label": "CRM Default Pipeline",
            "default": "Sales",
            "insert_after": "crm_column_break",
        },
        {
            "fieldname": "crm_followup_language",
            "fieldtype": "Select",
            "options": "auto\nen\nes",
            "label": "Follow-up Language",
            "default": "auto",
            "description": "Language for agent-drafted follow-ups; 'auto' detects from last communication",
            "insert_after": "crm_default_pipeline",
        },
    ]
}


def execute():
    """Create CRM custom fields on AI Agent Settings and register the skill."""
    # 1. Custom fields ----------------------------------------------------
    try:
        create_custom_fields(CRM_FIELDS, ignore_validate=True, update=True)
        print("[crm_agent] AI Agent Settings — CRM custom fields ensured.")
    except Exception as e:
        # Don't break migration; log and continue.
        frappe.log_error(
            title="[crm_agent] custom field creation failed",
            message=frappe.get_traceback(),
        )
        print(f"[crm_agent] custom field creation warning: {e}")

    # 2. Skill registry row (if the AI Skill Registry DocType exists) ------
    try:
        if "AI Skill Registry" in frappe.get_all(
            "DocType", filters={"name": "AI Skill Registry"}, pluck="name"
        ):
            if not frappe.db.exists("AI Skill Registry", "crm_agent"):
                frappe.get_doc({
                    "doctype": "AI Skill Registry",
                    "name": "crm_agent",
                    "skill": "crm_agent",
                    "enabled": 1,
                    "category": "crm",
                    "priority": 65,
                    "description": (
                        "Agentic CRM for ERPNext — enrich leads, advance "
                        "opportunities, draft follow-ups, summarize pipeline."
                    ),
                }).insert(ignore_permissions=True, ignore_if_duplicate=True)
                print("[crm_agent] registered in AI Skill Registry.")
            else:
                print("[crm_agent] already registered in AI Skill Registry.")
    except Exception:
        # Registry row is best-effort; skill is auto-discovered from the
        # filesystem regardless.
        frappe.log_error(
            title="[crm_agent] skill registry write failed",
            message=frappe.get_traceback(),
        )

    frappe.db.commit()
