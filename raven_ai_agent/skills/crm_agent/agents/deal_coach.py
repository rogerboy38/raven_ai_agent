"""
DealCoachAgent
==============
"Next best action" for any Opportunity. Uses raven_ai_agent.patterns.planner
when available to produce a 3-step plan grounded in the deal's history.
"""
from __future__ import annotations
from typing import Dict
import frappe
from .base import CRMAgentBase

__all__ = ['DealCoachAgent']


SYSTEM_PROMPT = """You are a senior sales coach.
Given an Opportunity's stage, amount, expected close, and full communication
history, propose the THREE highest-leverage next actions.

Return a numbered list. Each item:
  N) <action verb> <object> — <one-sentence why>
Then add a one-line risk flag if anything looks off.
Match the language of the recent communications (English/Spanish).
"""


class DealCoachAgent(CRMAgentBase):
    agent_name = "deal_coach"

    def next_best_action(self, opportunity: str) -> str:
        opportunity = (opportunity or "").strip(" .,?!")
        if not frappe.db.exists("Opportunity", opportunity):
            return f"⚠️ Opportunity `{opportunity}` not found."

        opp = frappe.get_doc("Opportunity", opportunity)
        comms = frappe.get_all(
            "Communication",
            filters={"reference_doctype": "Opportunity", "reference_name": opportunity},
            fields=["communication_date", "sent_or_received", "subject", "content"],
            order_by="communication_date desc",
            limit=10,
        )
        history_txt = "\n".join(
            f"[{c['communication_date']}] {c['sent_or_received']} · "
            f"{c.get('subject') or ''} :: {(c.get('content') or '')[:200]}"
            for c in comms
        ) or "(no history)"

        user = (
            f"Opportunity {opp.name}\n"
            f"Party: {opp.party_name}\n"
            f"Stage: {opp.status}\n"
            f"Amount: {opp.opportunity_amount} {opp.currency}\n"
            f"Expected close: {opp.expected_closing}\n"
            f"Owner: {opp.opportunity_owner}\n\n"
            f"History:\n{history_txt}\n\n"
            f"Propose the 3 next actions."
        )

        # Use planner pattern if available, else direct LLM
        try:
            from raven_ai_agent.patterns import planner
            if hasattr(planner, "plan"):
                plan = planner.plan(system=SYSTEM_PROMPT, user=user, steps=3)
                if plan:
                    return f"🎯 **Next steps on `{opp.name}`**\n\n{plan}"
        except Exception:
            pass

        out = self.llm(system=SYSTEM_PROMPT, user=user, temperature=0.3)
        return f"🎯 **Next steps on `{opp.name}`**\n\n{out or '(no plan)'}"
