"""
MeetingCapturerAgent
====================
Bound to Communication.after_insert.

If the sender/recipient is unknown → create Contact and a Lead.
If we can match the email to an existing Opportunity's party → link it.
"""
from __future__ import annotations
import re
import frappe
from .base import CRMAgentBase

EMAIL_RE = re.compile(r"[\w\.\+\-]+@[\w\-]+\.[\w\.\-]+")


class MeetingCapturerAgent(CRMAgentBase):
    agent_name = "meeting_capturer"

    def capture(self, comm_name: str):
        comm = frappe.get_doc("Communication", comm_name)
        if comm.reference_doctype and comm.reference_name:
            return  # already linked

        emails = EMAIL_RE.findall(
            " ".join([comm.sender or "", comm.recipients or "", comm.cc or "",
                      comm.subject or "", (comm.content or "")[:500]])
        )
        emails = [e.lower() for e in emails if e]
        if not emails:
            return

        # Try to match an existing Lead/Contact/Customer
        for email in emails:
            lead = frappe.db.get_value("Lead", {"email_id": email}, "name")
            if lead:
                self._link(comm, "Lead", lead)
                return
            contact_parent = frappe.db.get_value(
                "Contact Email", {"email_id": email}, "parent"
            )
            if contact_parent:
                # Try to find an opportunity tied to that contact
                opp = self._find_opportunity_for_contact(contact_parent)
                if opp:
                    self._link(comm, "Opportunity", opp)
                    return

        # Unknown sender → create a Lead from the first email
        if self.can_act("enrich"):
            from raven_ai_agent.skills.crm_agent.tools.leads import create_lead
            primary = emails[0]
            created = create_lead(
                lead_name=primary.split("@")[0],
                email_id=primary,
                source="Email",
                notes=(comm.subject or "")[:140],
            )
            if created.get("ok"):
                self._link(comm, "Lead", created["name"])
                self.audit("capture", "lead_created",
                           {"comm": comm.name, "lead": created["name"]})

    def _link(self, comm, dt: str, name: str):
        comm.reference_doctype = dt
        comm.reference_name = name
        comm.status = "Linked"
        comm.save(ignore_permissions=True)
        self.audit("capture", "linked",
                   {"comm": comm.name, "to": f"{dt}/{name}"})

    @staticmethod
    def _find_opportunity_for_contact(contact_name: str):
        # Find a recent open opportunity whose customer has this contact
        return frappe.db.sql(
            """
            SELECT o.name FROM `tabOpportunity` o
            JOIN `tabDynamic Link` dl
              ON dl.link_doctype = 'Customer'
             AND dl.link_name = o.party_name
             AND dl.parenttype = 'Contact'
             AND dl.parent = %(contact)s
            WHERE o.status IN ('Open','Quotation','Replied')
            ORDER BY o.modified DESC LIMIT 1
            """,
            {"contact": contact_name},
        )
        # Returns [(name,)] or []


def on_communication_after_insert(doc, method=None):
    if doc.communication_medium not in ("Email",):
        return
    try:
        MeetingCapturerAgent().capture(doc.name)
    except Exception:
        frappe.log_error(message=frappe.get_traceback(),
                         title="[crm_agent] on_communication_after_insert")
