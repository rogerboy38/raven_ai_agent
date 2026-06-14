"""
OpportunityMoverAgent
=====================
Hourly scan + Opportunity.on_update trigger.

Suggests (or auto-applies, depending on autonomy) stage advances based
on activity signals:
  - Quotation linked → suggest 'Quotation'
  - Reply received in last 24h on Quotation stage → suggest 'Replied'
  - No activity in 14d → flag as stalled
"""
from __future__ import annotations
import frappe
from frappe.utils import nowdate, add_days
from .base import CRMAgentBase


class OpportunityMoverAgent(CRMAgentBase):
    agent_name = "opportunity_mover"

    def scan(self):
        opps = frappe.get_all(
            "Opportunity",
            filters={"status": ["in", ["Open", "Quotation", "Replied"]]},
            fields=["name", "status", "modified"],
            limit=500,
        )
        for o in opps:
            try:
                self._evaluate(o["name"])
            except Exception:
                frappe.log_error(
                    title=f"[crm_agent] opportunity_mover {o['name']}",
                    message=frappe.get_traceback(),
                )

    def _evaluate(self, name: str):
        opp = frappe.get_doc("Opportunity", name)
        suggestion = None

        # Rule 1: Quotation exists for this Opp → move to Quotation
        has_quote = frappe.db.exists(
            "Quotation",
            {"opportunity": opp.name, "docstatus": ["<", 2]},
        )
        if has_quote and opp.status == "Open":
            suggestion = "Quotation"

        # Rule 2: Received Communication in last 24h while on Quotation
        if opp.status == "Quotation":
            recent_reply = frappe.db.exists(
                "Communication",
                {
                    "reference_doctype": "Opportunity",
                    "reference_name": opp.name,
                    "sent_or_received": "Received",
                    "communication_date": [">=", add_days(nowdate(), -1)],
                },
            )
            if recent_reply:
                suggestion = "Replied"

        if not suggestion:
            return

        if self.can_act("stage_move"):
            from raven_ai_agent.skills.crm_agent.tools.opportunities import move_stage
            res = move_stage(name=opp.name, status=suggestion)
            self.audit("stage_move", "applied" if res.get("ok") else "failed",
                       {"opp": opp.name, "to": suggestion, "result": res})
        else:
            self.audit("stage_move", "suggested",
                       {"opp": opp.name, "to": suggestion})


# Scheduler & hook entrypoints
def scan_stalled_opportunities():
    OpportunityMoverAgent().scan()


def on_opportunity_update(doc, method=None):
    try:
        OpportunityMoverAgent()._evaluate(doc.name)
    except Exception:
        frappe.log_error(message=frappe.get_traceback(),
                         title="[crm_agent] on_opportunity_update")
