"""
CRM Tools — Activities (ToDo, Event, CRM Note)
"""
from __future__ import annotations
from typing import Dict, Optional
import frappe


@frappe.whitelist()
def create_todo(
    description: str,
    reference_type: Optional[str] = None,
    reference_name: Optional[str] = None,
    allocated_to: Optional[str] = None,
    date: Optional[str] = None,
    priority: str = "Medium",
) -> Dict:
    try:
        doc = frappe.get_doc({
            "doctype": "ToDo",
            "description": description,
            "reference_type": reference_type,
            "reference_name": reference_name,
            "allocated_to": allocated_to or frappe.session.user,
            "date": date,
            "priority": priority,
        })
        doc.insert(ignore_permissions=False)
        return {"ok": True, "name": doc.name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def schedule_event(
    subject: str,
    starts_on: str,
    ends_on: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_name: Optional[str] = None,
) -> Dict:
    try:
        doc = frappe.get_doc({
            "doctype": "Event",
            "subject": subject,
            "starts_on": starts_on,
            "ends_on": ends_on,
            "event_type": "Private",
        })
        if reference_type and reference_name:
            doc.append("event_participants", {
                "reference_doctype": reference_type,
                "reference_docname": reference_name,
            })
        doc.insert(ignore_permissions=False)
        return {"ok": True, "name": doc.name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def add_note(
    reference_doctype: str,
    reference_name: str,
    content: str,
    title: Optional[str] = None,
) -> Dict:
    """Use ERPNext 'CRM Note' if present, else a Comment."""
    try:
        if "CRM Note" in frappe.get_meta_module_list() if hasattr(frappe, "get_meta_module_list") else True:
            try:
                doc = frappe.get_doc({
                    "doctype": "CRM Note",
                    "title": title or "Agent note",
                    "content": content,
                    "reference_doctype": reference_doctype,
                    "reference_name": reference_name,
                })
                doc.insert()
                return {"ok": True, "name": doc.name, "kind": "CRM Note"}
            except Exception:
                pass
        # fallback → Comment on the document
        ref = frappe.get_doc(reference_doctype, reference_name)
        ref.add_comment("Comment", text=f"**{title or 'Agent note'}**\n{content}")
        return {"ok": True, "kind": "Comment", "reference": reference_name}
    except Exception as e:
        return {"ok": False, "error": str(e)}
