"""
CRM Tools — Opportunities
=========================
Whitelisted wrappers around ERPNext `Opportunity`.
"""
from __future__ import annotations
from typing import Dict, List, Optional

import frappe


VALID_STATUSES = {"Open", "Quotation", "Converted", "Replied", "Lost", "Closed"}


@frappe.whitelist()
def create_opportunity(
    party_name: str,
    opportunity_from: str = "Customer",
    customer_name: Optional[str] = None,
    currency: str = "MXN",
    opportunity_amount: float = 0,
    expected_closing: Optional[str] = None,
    source: str = "Raven AI",
) -> Dict:
    try:
        opp = frappe.get_doc({
            "doctype": "Opportunity",
            "opportunity_from": opportunity_from,
            "party_name": party_name,
            "customer_name": customer_name or party_name,
            "currency": currency,
            "opportunity_amount": opportunity_amount,
            "expected_closing": expected_closing,
            "source": source,
            "status": "Open",
            "company": frappe.defaults.get_user_default("Company")
                       or frappe.db.get_single_value("Global Defaults", "default_company"),
        })
        opp.insert(ignore_permissions=False)
        return {"ok": True, "name": opp.name}
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="[crm_agent] create_opportunity")
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def move_stage(name: str, status: str) -> Dict:
    """Move opportunity to a new status (ERPNext stage)."""
    status_clean = status.strip().title()
    # Normalize a few common aliases
    aliases = {
        "Quote": "Quotation",
        "Cotización": "Quotation",
        "Cotizacion": "Quotation",
        "Ganado": "Converted",
        "Won": "Converted",
        "Perdido": "Lost",
    }
    status_clean = aliases.get(status_clean, status_clean)

    if status_clean not in VALID_STATUSES:
        return {"ok": False,
                "error": f"Unknown status '{status}'. Valid: {sorted(VALID_STATUSES)}"}
    try:
        opp = frappe.get_doc("Opportunity", name)
        opp.status = status_clean
        opp.save(ignore_permissions=False)
        return {"ok": True, "name": opp.name, "status": opp.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def set_amount(name: str, amount: float, currency: Optional[str] = None) -> Dict:
    try:
        opp = frappe.get_doc("Opportunity", name)
        opp.opportunity_amount = float(amount)
        if currency:
            opp.currency = currency
        opp.save()
        return {"ok": True, "name": opp.name, "amount": opp.opportunity_amount}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def list_open_opportunities(limit: int = 20, owner: Optional[str] = None) -> List[Dict]:
    filters = {"status": ["in", ["Open", "Quotation", "Replied"]]}
    if owner:
        filters["opportunity_owner"] = owner
    return frappe.get_all(
        "Opportunity",
        filters=filters,
        fields=["name", "party_name", "customer_name", "status",
                "opportunity_amount", "currency", "expected_closing",
                "opportunity_owner", "modified"],
        order_by="modified desc",
        limit=limit,
    )


@frappe.whitelist()
def forecast(period_days: int = 30) -> Dict:
    """Sum of opportunity_amount * probability for opps closing within N days."""
    from frappe.utils import nowdate, add_days
    rows = frappe.db.sql(
        """
        SELECT currency,
               SUM(opportunity_amount) AS total,
               SUM(opportunity_amount * IFNULL(probability,50) / 100) AS weighted
        FROM `tabOpportunity`
        WHERE status IN ('Open','Quotation','Replied')
          AND expected_closing BETWEEN %(start)s AND %(end)s
        GROUP BY currency
        """,
        {"start": nowdate(), "end": add_days(nowdate(), period_days)},
        as_dict=True,
    )
    return {"ok": True, "period_days": period_days, "by_currency": rows}
