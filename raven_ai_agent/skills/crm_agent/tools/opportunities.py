"""
CRM Tools — Opportunities
=========================
Whitelisted wrappers around ERPNext `Opportunity`.
"""
from __future__ import annotations
from typing import Dict, List, Optional

import frappe


# Static fallback list — used when the Opportunity DocType meta isn't available
# (fresh installs, sandbox without the site loaded). Production code path uses
# :func:`_valid_statuses` which reads the DocType meta at runtime so v16's
# "Replied" (and any future statuses) are picked up automatically. See N2 in
# the PR #16 review.
_STATIC_VALID_STATUSES = {"Open", "Quotation", "Converted", "Replied", "Lost", "Closed"}


def _valid_statuses() -> set:
    """Read allowed Opportunity statuses from DocType meta at runtime.

    Falls back to the static set if the meta lookup fails (e.g. running
    outside a Frappe site during smoke tests).
    """
    try:
        meta = frappe.get_meta("Opportunity")
        field = meta.get_field("status")
        if field and field.options:
            return {s.strip() for s in field.options.split("\n") if s.strip()}
    except Exception:
        pass
    return _STATIC_VALID_STATUSES


# Backwards-compatible alias for callers that imported the old constant.
VALID_STATUSES = _STATIC_VALID_STATUSES


def _default_company() -> Optional[str]:
    """Resolve the active company (user default → global default)."""
    try:
        return (frappe.defaults.get_user_default("Company")
                or frappe.db.get_single_value("Global Defaults", "default_company"))
    except Exception:
        return None


def _default_currency() -> str:
    """Resolve the active currency from the company's ``default_currency``.

    Used by ``create_opportunity`` and the parsing layer (M4 fix) so bare
    ``$`` never silently defaults to MXN — it follows the company config.
    Falls back to ``MXN`` only as a last resort.
    """
    try:
        company = _default_company()
        if company:
            cur = frappe.db.get_value("Company", company, "default_currency")
            if cur:
                return cur
    except Exception:
        pass
    return "MXN"


@frappe.whitelist()
def create_opportunity(
    party_name: str,
    opportunity_from: str = "Customer",
    customer_name: Optional[str] = None,
    currency: Optional[str] = None,
    opportunity_amount: float = 0,
    expected_closing: Optional[str] = None,
    source: str = "Raven AI",
) -> Dict:
    """Create an Opportunity.

    Fix (N1, PR #16 review): ``currency`` now defaults to the company's
    ``default_currency`` instead of hard-coded "MXN". Pass an explicit
    ``currency=`` to override.
    """
    try:
        opp = frappe.get_doc({
            "doctype": "Opportunity",
            "opportunity_from": opportunity_from,
            "party_name": party_name,
            "customer_name": customer_name or party_name,
            "currency": currency or _default_currency(),
            "opportunity_amount": opportunity_amount,
            "expected_closing": expected_closing,
            "source": source,
            "status": "Open",
            "company": _default_company(),
        })
        opp.insert(ignore_permissions=False)
        return {"ok": True, "name": opp.name}
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="[crm-agent.opportunities] create_opportunity")
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

    valid = _valid_statuses()
    if status_clean not in valid:
        return {"ok": False,
                "error": f"Unknown status '{status}'. Valid: {sorted(valid)}"}
    try:
        opp = frappe.get_doc("Opportunity", name)
        opp.status = status_clean
        opp.save(ignore_permissions=False)
        return {"ok": True, "name": opp.name, "status": opp.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def set_amount(name: str, amount: float, currency: Optional[str] = None) -> Dict:
    """Set Opportunity amount (and optionally currency).

    Fix (M3, PR #16 review): added explicit ``ignore_permissions=False``
    to match the convention used by every other write in this skill
    (``create_opportunity``, ``move_stage``, ``create_lead``, etc.).
    Default is the same, but the explicit flag prevents the next reader
    from assuming the lack of flag is load-bearing.
    """
    try:
        opp = frappe.get_doc("Opportunity", name)
        opp.opportunity_amount = float(amount)
        if currency:
            opp.currency = currency
        opp.save(ignore_permissions=False)
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
