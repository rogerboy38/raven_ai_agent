"""
LeadEnricherAgent
=================
Triggered by Lead.after_insert (or on-demand from chat).

Steps:
  1. Read the Lead's email/company.
  2. Pull web info via raven_ai_agent.api.handlers.web_search (already in repo).
  3. Use the LLM to extract structured fields.
  4. Apply update_lead() if autonomy allows; otherwise return a suggestion.
"""
from __future__ import annotations
from typing import Dict, Optional

import frappe
from .base import CRMAgentBase

__all__ = ['LeadEnricherAgent', 'enrich_async', 'on_lead_after_insert']


SYSTEM_PROMPT = """You are a CRM data enrichment agent.
Given a lead's name, email, and any notes, infer structured fields:
  company_name, industry, country, no_of_employees (bucket), website, designation, language.

Return strict JSON with only these keys. Use null when unknown.
Do not invent specific employee counts — use buckets: '1-10','11-50','51-200','201-500','501-1000','1000+'.
"""


class LeadEnricherAgent(CRMAgentBase):
    agent_name = "lead_enricher"

    def enrich(self, lead: str) -> Dict:
        """Enrich a Lead by name. Returns {summary, applied, fields}."""
        try:
            doc = frappe.get_doc("Lead", lead)
        except frappe.DoesNotExistError:
            return {"summary": f"⚠️ Lead `{lead}` not found.", "applied": False}

        # --- Build context for the LLM --------------------------------------
        seed = {
            "lead_name": doc.lead_name,
            "company_name": doc.company_name,
            "email_id": doc.email_id,
            "mobile_no": doc.mobile_no,
            "notes": (doc.notes or "")[:1000],
        }

        web_snippets = self._web_research(seed)

        user_prompt = (
            f"Lead seed:\n{frappe.as_json(seed)}\n\n"
            f"Web snippets:\n{web_snippets}\n\n"
            "Extract enrichment fields as JSON."
        )

        raw = self.llm(system=SYSTEM_PROMPT, user=user_prompt, temperature=0.1)
        fields = self._safe_json(raw)
        if not fields:
            self.audit("enrich", "llm_no_output", {"lead": lead})
            return {"summary": f"⚠️ Could not enrich `{lead}` (no model output).",
                    "applied": False}

        # --- Apply --------------------------------------------------------
        applied = False
        if self.can_act("enrich"):
            from raven_ai_agent.skills.crm_agent.tools.leads import update_lead
            allowed = {"company_name", "industry", "country",
                       "no_of_employees", "website"}
            patch = {k: v for k, v in fields.items() if k in allowed and v}
            if patch:
                result = update_lead(name=lead, **patch)
                applied = bool(result.get("ok"))
                self.audit("enrich", "applied" if applied else "apply_failed",
                           {"lead": lead, "patch": patch, "result": result})
        else:
            self.audit("enrich", "suggested_only", {"lead": lead, "fields": fields})

        summary = self._format_summary(lead, fields, applied)
        return {"summary": summary, "applied": applied, "fields": fields}

    # --------------------------------------------------------------------
    # Helpers
    # --------------------------------------------------------------------
    def _web_research(self, seed: Dict) -> str:
        """Best-effort web search; returns up to ~1KB of text."""
        try:
            from raven_ai_agent.api.handlers import web_search
            q_parts = [seed.get("company_name") or "",
                       seed.get("email_id", "").split("@")[-1] if seed.get("email_id") else ""]
            query = " ".join(p for p in q_parts if p).strip()
            if not query:
                return ""
            results = web_search.search(query=query, max_results=5) \
                if hasattr(web_search, "search") else []
            return "\n".join(
                f"- {r.get('title','')}: {r.get('snippet','')}"
                for r in (results or [])
            )[:1500]
        except Exception:
            return ""

    @staticmethod
    def _safe_json(text: str) -> Optional[Dict]:
        import json, re
        if not text:
            return None
        # Find first {...} block
        m = re.search(r"\{[\s\S]+\}", text)
        try:
            return json.loads(m.group(0)) if m else None
        except Exception:
            return None

    @staticmethod
    def _format_summary(lead: str, fields: Dict, applied: bool) -> str:
        bullets = [f"- **{k}**: {v}" for k, v in fields.items() if v]
        head = (f"✅ Enriched `{lead}` (applied)" if applied
                else f"💡 Enrichment suggestion for `{lead}` (autonomy too low to write)")
        return head + "\n" + "\n".join(bullets) if bullets else head


# ----------------------------------------------------------------------
# Public entrypoints (Frappe hooks + queue jobs)
# ----------------------------------------------------------------------
def enrich_async(lead: str):
    """Background-queue safe wrapper."""
    LeadEnricherAgent().enrich(lead=lead)


def on_lead_after_insert(doc, method=None):
    """Bind to Lead.after_insert in hooks.py:
        doc_events = {"Lead": {"after_insert":
            "raven_ai_agent.skills.crm_agent.agents.lead_enricher.on_lead_after_insert"}}

    Note (S2, PR #16 review): ``enqueue_after_commit=True`` requires Frappe
    ≥ v15. Sandbox is v16 so this is fine. If backporting to v13/v14, drop
    the kwarg and accept the small risk of the worker picking up the job
    before the parent transaction commits.
    """
    try:
        frappe.enqueue(
            "raven_ai_agent.skills.crm_agent.agents.lead_enricher.enrich_async",
            queue="long",
            lead=doc.name,
            enqueue_after_commit=True,   # Frappe ≥ v15
        )
    except Exception:
        # As a fallback, run synchronously (don't break Lead creation).
        try:
            enrich_async(lead=doc.name)
        except Exception:
            frappe.log_error(message=frappe.get_traceback(),
                             title="[crm-agent] lead_enricher hook failed")
