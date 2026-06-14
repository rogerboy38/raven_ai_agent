"""
FollowUpWriterAgent
===================
Drafts a personalized follow-up email/WhatsApp for an Opportunity or Lead.

Always returns a draft (never sends), unless autonomy ≥ 4 AND the user
explicitly invokes send_email afterwards.
"""
from __future__ import annotations
from typing import Dict, Optional

import frappe
from .base import CRMAgentBase

__all__ = ['FollowUpWriterAgent']


SYSTEM_PROMPT = """You are a senior B2B account manager.
Write a concise, personalized follow-up email (or WhatsApp if requested).
- Tone: warm, direct, no fluff.
- Reference at least one specific item from the deal history.
- Propose ONE clear next step.
- Match the language of the most recent communication.
- ≤ 120 words.
Return:
SUBJECT: <line>
BODY:
<body>
"""


class FollowUpWriterAgent(CRMAgentBase):
    agent_name = "follow_up_writer"

    def draft(self, target: str = "", query: str = "", channel: str = "email") -> str:
        target = (target or "").strip()
        if not target:
            return "⚠️ I need an Opportunity or Lead id. Try: `draft follow-up for Opp-0042`."

        doctype, name = self._resolve_target(target)
        if not doctype:
            return f"⚠️ Could not find `{target}` as Opportunity or Lead."

        record = frappe.get_doc(doctype, name)
        history = self._load_history(doctype, name)

        user_prompt = (
            f"Channel: {channel}\n"
            f"Target: {doctype} `{name}`\n"
            f"Party: {getattr(record, 'party_name', None) or getattr(record, 'lead_name', '')}\n"
            f"Amount: {getattr(record, 'opportunity_amount', '')}\n"
            f"Stage: {getattr(record, 'status', '')}\n"
            f"Expected close: {getattr(record, 'expected_closing', '')}\n\n"
            f"Recent communication history (most recent first):\n{history}\n\n"
            f"Extra user instruction: {query!r}\n\n"
            "Write the follow-up now."
        )

        draft = self.llm(system=SYSTEM_PROMPT, user=user_prompt, temperature=0.4)
        if not draft:
            return f"⚠️ Could not draft (LLM error)."

        self.audit("draft", "produced", {"target": f"{doctype}/{name}",
                                          "channel": channel, "chars": len(draft)})

        # Append a "[ Send ]" affordance hint for the front-end / Raven channel
        return (
            f"✉️ **Draft for {doctype} `{name}`** (review before sending):\n\n"
            f"{draft}\n\n"
            f"_Reply `send {name}` to send, or edit and re-ask._"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_target(token: str):
        token = token.strip(" .,?!")
        for dt in ("Opportunity", "Lead"):
            if frappe.db.exists(dt, token):
                return dt, token
        # Case-insensitive fallback
        for dt in ("Opportunity", "Lead"):
            row = frappe.db.get_value(dt, {"name": ["like", token]}, "name")
            if row:
                return dt, row
        return None, None

    @staticmethod
    def _load_history(doctype: str, name: str, limit: int = 8) -> str:
        rows = frappe.get_all(
            "Communication",
            filters={"reference_doctype": doctype, "reference_name": name},
            fields=["communication_date", "sent_or_received", "sender",
                    "recipients", "subject", "content"],
            order_by="communication_date desc",
            limit=limit,
        )
        if not rows:
            return "(no prior communication)"
        out = []
        for r in rows:
            content = (r.get("content") or "").replace("\n", " ")[:300]
            out.append(
                f"[{r.get('communication_date')}] "
                f"{r.get('sent_or_received')} · "
                f"{r.get('subject') or '(no subject)'} :: {content}"
            )
        return "\n".join(out)
