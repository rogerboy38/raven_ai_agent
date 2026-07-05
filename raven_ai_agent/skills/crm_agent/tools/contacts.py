"""
CRM Tools — Contacts
====================
"""
from __future__ import annotations
from typing import Dict, List, Optional
import frappe


@frappe.whitelist()
def find_or_create_contact(
    email: Optional[str] = None,
    phone: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    company: Optional[str] = None,
) -> Dict:
    """Find by email/phone first, else create."""
    if email:
        match = frappe.db.get_value(
            "Contact Email", {"email_id": email}, "parent"
        )
        if match:
            return {"ok": True, "name": match, "created": False}
    if phone:
        match = frappe.db.get_value(
            "Contact Phone", {"phone": phone}, "parent"
        )
        if match:
            return {"ok": True, "name": match, "created": False}

    try:
        doc = frappe.get_doc({
            "doctype": "Contact",
            "first_name": first_name or (email.split("@")[0] if email else "Unknown"),
            "last_name": last_name,
            "company_name": company,
        })
        if email:
            doc.append("email_ids", {"email_id": email, "is_primary": 1})
        if phone:
            doc.append("phone_nos", {"phone": phone, "is_primary_mobile_no": 1})
        doc.insert(ignore_permissions=False)
        return {"ok": True, "name": doc.name, "created": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def enrich_contact(name: str, **fields) -> Dict:
    """Patch a Contact with enrichment data (designation, company, etc.)."""
    try:
        doc = frappe.get_doc("Contact", name)
        for k, v in fields.items():
            if v is None:
                continue
            doc.set(k, v)
        doc.save()
        return {"ok": True, "name": doc.name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def find_duplicates(limit: int = 50) -> List[Dict]:
    """Naive duplicate detection by email."""
    return frappe.db.sql(
        """
        SELECT email_id, COUNT(*) AS dup_count,
               GROUP_CONCAT(parent) AS contacts
        FROM `tabContact Email`
        GROUP BY email_id
        HAVING dup_count > 1
        ORDER BY dup_count DESC
        LIMIT %(limit)s
        """,
        {"limit": limit},
        as_dict=True,
    )
