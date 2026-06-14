"""
CRM Agent Skill
===============
Top-level skill that routes CRM intents to the right tool or sub-agent.

Follows the SkillBase contract from raven_ai_agent.skills.framework.
Sub-agents under .agents.* do the heavy lifting; this class is the
intent dispatcher exposed to SkillRouter.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, List, Tuple

import frappe
from raven_ai_agent.skills.framework import SkillBase


# ----------------------------------------------------------------------
# Intent table
# ----------------------------------------------------------------------
# Each tuple: (intent_id, regex, handler_method_name)
# Order matters — first match wins. Keep most-specific patterns first.

INTENTS: List[Tuple[str, str, str]] = [
    # --- pipeline / digest ---------------------------------------------------
    ("pipeline_digest",
     r"(?:morning\s+brief|daily\s+digest|pipeline\s+(?:summary|digest|status|report)|resumen\s+(?:de\s+hoy|del\s+d[ií]a))",
     "_handle_pipeline_digest"),
    ("pipeline_list",
     r"(?:show|list|view)\s+(?:my\s+)?(?:pipeline|leads|opportunities|deals)",
     "_handle_pipeline_list"),

    # --- next best action / deal coach ---------------------------------------
    ("deal_coach",
     r"(?:next\s+(?:step|action|move)|what\s+should\s+i\s+do)\s+(?:on|for|next\s+on)\s+(\S+)",
     "_handle_deal_coach"),
    ("deal_coach_es",
     r"(?:qu[eé]\s+sigue\s+con|qu[eé]\s+hacer\s+con|pr[oó]ximo\s+paso\s+(?:en|para))\s+(\S+)",
     "_handle_deal_coach"),

    # --- follow-up draft -----------------------------------------------------
    ("follow_up_draft",
     r"(?:draft|write|compose)\s+(?:a\s+)?(?:follow[-\s]?up|email)\s+(?:for\s+|to\s+)?(\S+)?",
     "_handle_follow_up_draft"),
    ("follow_up_draft_es",
     r"(?:redacta|escribe|haz)\s+(?:un\s+)?(?:seguimiento|correo)\s+(?:para|a)\s+(\S+)?",
     "_handle_follow_up_draft"),

    # --- stage move ----------------------------------------------------------
    ("stage_move",
     r"(?:move|advance|set)\s+(?:opp|opportunity|deal|oportunidad)\s+(\S+)\s+to\s+(.+)$",
     "_handle_stage_move"),

    # --- enrichment ----------------------------------------------------------
    ("enrich",
     r"(?:enrich|complete|completa)\s+(?:lead|contact|prospect|prospecto)\s+(\S+)",
     "_handle_enrich"),

    # --- creation ------------------------------------------------------------
    ("create_lead",
     r"(?:new|create|add)\s+lead\s+(.+)$",
     "_handle_create_lead"),
    ("create_opportunity",
     r"(?:new|create|add)\s+(?:opportunity|deal|oportunidad)\s+(.+)$",
     "_handle_create_opportunity"),

    # --- generic CRM help ----------------------------------------------------
    ("crm_help",
     r"\bcrm\b(?:\s+help)?$",
     "_handle_help"),
]


class CRMAgentSkill(SkillBase):
    """Agentic CRM skill — humans supervise agents."""

    name = "crm_agent"
    description = (
        "Agentic CRM for ERPNext — enriches leads, advances opportunities, "
        "drafts follow-ups, summarizes pipeline."
    )
    emoji = "🤝"
    version = "0.1.0"
    priority = 65

    triggers = [
        "lead", "leads", "opportunity", "opportunities", "pipeline",
        "deal", "deals", "prospect", "follow up", "follow-up", "followup",
        "next step", "next best action", "enrich contact", "enrich lead",
        "move stage", "close deal", "customer", "crm",
        # Spanish
        "prospecto", "oportunidad", "cliente", "seguimiento", "cotización",
        "cotizar", "pipeline de ventas",
    ]

    patterns = [pat for _id, pat, _h in INTENTS]

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """Match intent → call handler → return SkillBase response dict."""
        context = context or {}
        q = (query or "").strip()
        if not q:
            return None

        for intent_id, pattern, method_name in INTENTS:
            m = re.search(pattern, q, re.IGNORECASE)
            if not m:
                continue

            handler = getattr(self, method_name, None)
            if not callable(handler):
                continue

            try:
                result = handler(query=q, match=m, context=context)
            except Exception as e:
                frappe.log_error(
                    title=f"[crm_agent] {intent_id} failed",
                    message=frappe.get_traceback(),
                )
                return {
                    "handled": True,
                    "response": f"⚠️ CRM error ({intent_id}): {e}",
                    "confidence": 0.6,
                }

            if result is None:
                continue

            # Normalize to SkillBase contract
            return {
                "handled": True,
                "response": result.get("response", ""),
                "confidence": result.get("confidence", 0.85),
                "data": result.get("data"),
                "skill": self.name,
                "intent": intent_id,
            }

        return None

    # ------------------------------------------------------------------
    # Intent handlers — thin wrappers around tools & agents
    # ------------------------------------------------------------------
    def _handle_pipeline_digest(self, *, query, match, context) -> Dict:
        from raven_ai_agent.skills.crm_agent.agents.pipeline_summarizer import (
            PipelineSummarizerAgent,
        )
        agent = PipelineSummarizerAgent(parent=self.agent, context=context)
        digest = agent.run_now()
        return {"response": digest, "data": {"agent": "pipeline_summarizer"}}

    def _handle_pipeline_list(self, *, query, match, context) -> Dict:
        from raven_ai_agent.skills.crm_agent.tools import opportunities
        opps = opportunities.list_open_opportunities(limit=20)
        if not opps:
            return {"response": "No open opportunities."}
        lines = ["**Open pipeline (top 20):**"]
        for o in opps:
            lines.append(
                f"- `{o['name']}` · {o.get('party_name','?')} · "
                f"{o.get('status','?')} · "
                f"{o.get('opportunity_amount',0):,.0f} {o.get('currency','MXN')}"
            )
        return {"response": "\n".join(lines), "data": {"opportunities": opps}}

    def _handle_deal_coach(self, *, query, match, context) -> Dict:
        from raven_ai_agent.skills.crm_agent.agents.deal_coach import DealCoachAgent
        opp_id = match.group(1).strip().rstrip(".?!,")
        agent = DealCoachAgent(parent=self.agent, context=context)
        plan = agent.next_best_action(opportunity=opp_id)
        return {"response": plan, "data": {"agent": "deal_coach", "opportunity": opp_id}}

    def _handle_follow_up_draft(self, *, query, match, context) -> Dict:
        from raven_ai_agent.skills.crm_agent.agents.follow_up_writer import (
            FollowUpWriterAgent,
        )
        target = (match.group(1) or "").strip().rstrip(".?!,") if match.groups() else ""
        agent = FollowUpWriterAgent(parent=self.agent, context=context)
        draft = agent.draft(target=target, query=query)
        return {"response": draft, "data": {"agent": "follow_up_writer", "target": target}}

    def _handle_stage_move(self, *, query, match, context) -> Dict:
        from raven_ai_agent.skills.crm_agent.tools import opportunities
        opp_id = match.group(1).strip()
        new_stage = match.group(2).strip().rstrip(".")
        result = opportunities.move_stage(name=opp_id, status=new_stage)
        return {
            "response": f"✅ Moved `{opp_id}` to **{new_stage}**." if result.get("ok")
                        else f"⚠️ {result.get('error','could not move stage')}",
            "data": result,
        }

    def _handle_enrich(self, *, query, match, context) -> Dict:
        from raven_ai_agent.skills.crm_agent.agents.lead_enricher import LeadEnricherAgent
        target = match.group(1).strip()
        agent = LeadEnricherAgent(parent=self.agent, context=context)
        result = agent.enrich(lead=target)
        return {"response": result.get("summary", "Enrichment done."), "data": result}

    def _handle_create_lead(self, *, query, match, context) -> Dict:
        from raven_ai_agent.skills.crm_agent.tools import leads
        from raven_ai_agent.skills.crm_agent.tools.parsing import parse_lead_oneliner
        parsed = parse_lead_oneliner(match.group(1))
        created = leads.create_lead(**parsed)
        if created.get("ok"):
            # Kick off enrichment asynchronously
            try:
                frappe.enqueue(
                    "raven_ai_agent.skills.crm_agent.agents.lead_enricher.enrich_async",
                    queue="long",
                    lead=created["name"],
                )
            except Exception:
                pass
            return {
                "response": f"✅ Lead `{created['name']}` created for **"
                            f"{parsed.get('lead_name','?')}** "
                            f"({parsed.get('company_name','?')}). "
                            f"Enrichment queued.",
                "data": created,
            }
        return {"response": f"⚠️ {created.get('error','could not create lead')}",
                "data": created}

    def _handle_create_opportunity(self, *, query, match, context) -> Dict:
        from raven_ai_agent.skills.crm_agent.tools import opportunities
        from raven_ai_agent.skills.crm_agent.tools.parsing import parse_opp_oneliner
        parsed = parse_opp_oneliner(match.group(1))
        created = opportunities.create_opportunity(**parsed)
        if created.get("ok"):
            return {
                "response": f"✅ Opportunity `{created['name']}` created.",
                "data": created,
            }
        return {"response": f"⚠️ {created.get('error','could not create opportunity')}",
                "data": created}

    def _handle_help(self, *, query, match, context) -> Dict:
        return {
            "response": (
                "**🤝 CRM Agent** — what I can do:\n"
                "- `new lead <name> at <company>, <email>, <notes>`\n"
                "- `new opportunity <name> for <customer>, <amount>`\n"
                "- `show pipeline`\n"
                "- `move Opp-0042 to Quotation`\n"
                "- `enrich lead LEAD-2026-00031`\n"
                "- `draft follow-up for Opp-0042`\n"
                "- `what should I do next on Opp-0042?`\n"
                "- `morning brief` / `pipeline digest`\n"
                "Español: `prospecto`, `oportunidad`, `seguimiento`, "
                "`¿qué sigue con Opp-0042?`"
            ),
            "confidence": 1.0,
        }
