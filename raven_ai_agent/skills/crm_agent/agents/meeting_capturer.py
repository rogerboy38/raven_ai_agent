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

__all__ = ['MeetingCapturerAgent', 'on_communication_after_insert']

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
        # S1 fix: flag the save so the after_insert hook short-circuits on the
        # re-fire it triggers. Without this we would recurse into capture()
        # for a Communication the agent itself just modified.
        comm.reference_doctype = dt
        comm.reference_name = name
        comm.status = "Linked"
        comm.flags.from_meeting_capturer = True
        comm.save(ignore_permissions=True)
        self.audit("capture", "linked",
                   {"comm": comm.name, "to": f"{dt}/{name}"})

    @staticmethod
    def _find_opportunity_for_contact(contact_name: str):
        """Return a single opportunity name (str) or None.

        Fix (M1, PR #16 review): previously returned ``frappe.db.sql`` raw output
        (``[('OPP-001',)]``) which the caller at line 46 treated as a scalar
        ``reference_name``. That broke the link silently (string-cast of a list
        of tuples).
        """
        rows = frappe.db.sql(
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
        return rows[0][0] if rows else None


def on_communication_after_insert(doc, method=None):
    """Bound to ``Communication.after_insert`` via hooks.py.

    Fix (S1, PR #16 review): explicitly short-circuit on agent-originated
    re-saves (``from_meeting_capturer`` flag) and on non-incoming-email
    communications, so we don't recurse into capture() or burn LLM tokens
    on internal notes, system mail, bulk imports, or replies the agent
    itself wrote.
    """
    # Agent's own writes set this flag; do not recurse.
    if getattr(doc, "flags", None) and doc.flags.get("from_meeting_capturer"):
        return
    # Only incoming emails are interesting.
    if doc.communication_medium not in ("Email",):
        return
    if getattr(doc, "sent_or_received", None) and doc.sent_or_received != "Received":
        return
    try:
        MeetingCapturerAgent().capture(doc.name)
    except Exception:
        frappe.log_error(message=frappe.get_traceback(),
                         title="[crm-agent] on_communication_after_insert")
