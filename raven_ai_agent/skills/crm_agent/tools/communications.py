"""
CRM Tools — Communications
==========================
Log emails/calls/WhatsApp into ERPNext `Communication`; send emails.
"""
from __future__ import annotations
from typing import Dict, Optional
import frappe


@frappe.whitelist()
def log_communication(
    reference_doctype: str,
    reference_name: str,
    content: str,
    subject: Optional[str] = None,
    communication_medium: str = "Email",   # Email/Phone/Chat/Other
    sent_or_received: str = "Sent",        # Sent/Received
    sender: Optional[str] = None,
    recipients: Optional[str] = None,
) -> Dict:
    try:
        doc = frappe.get_doc({
            "doctype": "Communication",
            "communication_type": "Communication",
            "communication_medium": communication_medium,
            "sent_or_received": sent_or_received,
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "subject": subject or "(no subject)",
            "content": content,
            "sender": sender or frappe.session.user,
            "recipients": recipients,
            "status": "Linked",
        })
        doc.insert(ignore_permissions=False)
        return {"ok": True, "name": doc.name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def send_email(
    recipients: str,
    subject: str,
    content: str,
    reference_doctype: Optional[str] = None,
    reference_name: Optional[str] = None,
) -> Dict:
    """Send an email via Frappe's mailer + log a Communication."""
    try:
        frappe.sendmail(
            recipients=[r.strip() for r in recipients.split(",") if r.strip()],
            subject=subject,
            message=content,
            reference_doctype=reference_doctype,
            reference_name=reference_name,
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
