"""
CRM Tools — Leads
=================
Thin, whitelisted wrappers around ERPNext `Lead` DocType.
"""
from __future__ import annotations
from typing import Dict, List, Optional

import frappe


@frappe.whitelist()
def create_lead(
    lead_name: str,
    company_name: Optional[str] = None,
    email_id: Optional[str] = None,
    mobile_no: Optional[str] = None,
    source: Optional[str] = "Raven AI",
    notes: Optional[str] = None,
    status: str = "Lead",
    territory: Optional[str] = None,
) -> Dict:
    """Create a Lead. Returns {ok, name, error}."""
    try:
        doc = frappe.get_doc({
            "doctype": "Lead",
            "lead_name": lead_name,
            "company_name": company_name,
            "email_id": email_id,
            "mobile_no": mobile_no,
            "source": source,
            "status": status,
            "territory": territory,
            "notes": notes,
        })
        doc.insert(ignore_permissions=False)
        return {"ok": True, "name": doc.name, "lead_name": doc.lead_name}
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="[crm-agent.leads] create_lead")
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def update_lead(name: str, **fields) -> Dict:
    """Patch a Lead with the provided fields."""
    try:
        doc = frappe.get_doc("Lead", name)
        for k, v in fields.items():
            if v is None:
                continue
            doc.set(k, v)
        doc.save(ignore_permissions=False)
        return {"ok": True, "name": doc.name, "updated": list(fields.keys())}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def qualify_lead(name: str, qualification_status: str = "Qualified") -> Dict:
    """Mark a lead qualified/disqualified."""
    return update_lead(name=name, qualification_status=qualification_status,
                       status="Open" if qualification_status == "Qualified" else "Do Not Contact")


@frappe.whitelist()
def convert_lead_to_opportunity(
    name: str,
    opportunity_amount: Optional[float] = None,
    currency: str = "MXN",
    expected_closing: Optional[str] = None,
) -> Dict:
    """Create an Opportunity linked to the given Lead."""
    try:
        lead = frappe.get_doc("Lead", name)
        opp = frappe.get_doc({
            "doctype": "Opportunity",
            "opportunity_from": "Lead",
            "party_name": lead.name,
            "customer_name": lead.lead_name or lead.company_name,
            "company": frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company"),
            "currency": currency,
            "opportunity_amount": opportunity_amount or 0,
            "expected_closing": expected_closing,
            "status": "Open",
        })
        opp.insert(ignore_permissions=False)
        return {"ok": True, "name": opp.name, "lead": lead.name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def list_leads(
    status: Optional[str] = None,
    limit: int = 20,
    search: Optional[str] = None,
) -> List[Dict]:
    """List leads with optional filters."""
    filters = {}
    if status:
        filters["status"] = status
    or_filters = None
    if search:
        or_filters = [
            ["lead_name", "like", f"%{search}%"],
            ["company_name", "like", f"%{search}%"],
            ["email_id", "like", f"%{search}%"],
        ]
    return frappe.get_all(
        "Lead",
        filters=filters,
        or_filters=or_filters,
        fields=["name", "lead_name", "company_name", "email_id",
                "status", "qualification_status", "creation"],
        order_by="creation desc",
        limit=limit,
    )
