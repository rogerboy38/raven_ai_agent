"""
PipelineSummarizerAgent
=======================
Daily/weekly digest posted to a configurable Raven channel.

Triggered by hooks.py scheduler_events.daily -> run_daily_digest()
"""
from __future__ import annotations
from typing import Dict, List
import frappe
from frappe.utils import nowdate, add_days

from .base import CRMAgentBase


class PipelineSummarizerAgent(CRMAgentBase):
    agent_name = "pipeline_summarizer"

    def run_now(self) -> str:
        snapshot = self._snapshot()
        text = self._render(snapshot)
        self._post_to_channel(text)
        return text

    # ------------------------------------------------------------------
    def _snapshot(self) -> Dict:
        open_opps = frappe.get_all(
            "Opportunity",
            filters={"status": ["in", ["Open", "Quotation", "Replied"]]},
            fields=["name", "party_name", "status", "opportunity_amount",
                    "currency", "expected_closing", "modified",
                    "opportunity_owner", "probability"],
            limit=200,
        )
        moved = frappe.get_all(
            "Opportunity",
            filters={"modified": [">=", add_days(nowdate(), -1)]},
            fields=["name", "status", "party_name", "opportunity_amount"],
            limit=50,
        )
        stalled = [
            o for o in open_opps
            if o.get("modified") and str(o["modified"])[:10] < add_days(nowdate(), -7)
        ]
        won = frappe.get_all(
            "Opportunity",
            filters={"status": "Converted",
                     "modified": [">=", add_days(nowdate(), -1)]},
            fields=["name", "party_name", "opportunity_amount", "currency"],
        )
        return {"open": open_opps, "moved": moved, "stalled": stalled, "won": won}

    @staticmethod
    def _render(snap: Dict) -> str:
        lines = ["🤝 **CRM Daily Digest**", ""]

        if snap["won"]:
            lines.append("**🏆 Won (last 24h):**")
            for o in snap["won"]:
                lines.append(f"- `{o['name']}` · {o.get('party_name','?')} · "
                             f"{o.get('opportunity_amount',0):,.0f} {o.get('currency','MXN')}")
            lines.append("")

        if snap["moved"]:
            lines.append("**🔄 Moved (last 24h):**")
            for o in snap["moved"][:10]:
                lines.append(f"- `{o['name']}` → {o.get('status')} · {o.get('party_name','?')}")
            lines.append("")

        if snap["stalled"]:
            lines.append("**⏳ Stalled > 7d:**")
            for o in snap["stalled"][:10]:
                lines.append(f"- `{o['name']}` · {o.get('party_name','?')} · "
                             f"{o.get('status')} · "
                             f"{o.get('opportunity_amount',0):,.0f} {o.get('currency','MXN')}")
            lines.append("")

        if not (snap["won"] or snap["moved"] or snap["stalled"]):
            lines.append("_No movement._")

        return "\n".join(lines)

    def _post_to_channel(self, text: str):
        channel = frappe.db.get_single_value("AI Agent Settings", "crm_digest_channel")
        if not channel:
            return
        try:
            from raven_ai_agent.channels.raven_channel import post_message
            post_message(channel=channel, text=text)
        except Exception:
            frappe.log_error(message=frappe.get_traceback(),
                             title="[crm_agent] pipeline_summarizer post failed")


# Scheduler entrypoint
def run_daily_digest():
    PipelineSummarizerAgent().run_now()
