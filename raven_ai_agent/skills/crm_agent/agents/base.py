"""
CRMAgentBase
============
Shared base for all CRM sub-agents. Wraps:
  - provider selection (from ai_agent_settings, via raven_ai_agent.providers)
  - autonomy enforcement (via raven_ai_agent.patterns.guardrails)
  - structured logging into AI Routing Audit Log

Sub-agents implement run() / domain-specific methods.
"""
from __future__ import annotations
from typing import Dict, Optional, Any

import frappe


class CRMAgentBase:
    """Common base for crm_agent sub-agents."""

    agent_name: str = "crm_base"

    def __init__(self, parent: Any = None, context: Optional[Dict] = None):
        self.parent = parent
        self.context = context or {}
        self._autonomy = self._load_autonomy()

    # ----------------------------------------------------------------
    # Provider / LLM
    # ----------------------------------------------------------------
    def _get_provider(self):
        """Get a configured LLM provider (raven_ai_agent.providers.base.Provider)."""
        try:
            from raven_ai_agent.providers import openai_provider, claude, deepseek, minimax
            settings = frappe.get_single("AI Agent Settings")
            choice = (settings.default_provider or "OpenAI").lower()
            return {
                "openai":  openai_provider.OpenAIProvider,
                "claude":  claude.ClaudeProvider,
                "deepseek": deepseek.DeepSeekProvider,
                "minimax": minimax.MiniMaxProvider,
            }.get(choice, openai_provider.OpenAIProvider)()
        except Exception:
            return None

    def llm(self, system: str, user: str, **kwargs) -> str:
        """Single-turn LLM call; returns text or empty string on failure."""
        provider = self._get_provider()
        if not provider:
            return ""
        try:
            return provider.complete(system=system, user=user, **kwargs) or ""
        except Exception:
            frappe.log_error(message=frappe.get_traceback(),
                             title=f"[crm_agent.{self.agent_name}] llm failed")
            return ""

    # ----------------------------------------------------------------
    # Autonomy + guardrails
    # ----------------------------------------------------------------
    def _load_autonomy(self) -> int:
        try:
            return int(frappe.db.get_single_value(
                "AI Agent Settings", "crm_autonomy_level") or 1)
        except Exception:
            return 1

    def can_act(self, action: str) -> bool:
        """
        Map action class → minimum autonomy level required.
        action ∈ {'read','enrich','log','draft','stage_move','send'}.
        """
        required = {
            "read": 0,
            "enrich": 2,
            "log": 2,
            "draft": 2,
            "stage_move": 3,
            "send": 4,
        }.get(action, 4)

        try:
            from raven_ai_agent.patterns import guardrails
            if hasattr(guardrails, "is_action_allowed"):
                return guardrails.is_action_allowed(
                    skill="crm_agent",
                    action=action,
                    autonomy_level=self._autonomy,
                )
        except Exception:
            pass
        return self._autonomy >= required

    # ----------------------------------------------------------------
    # Audit
    # ----------------------------------------------------------------
    def audit(self, intent: str, decision: str, payload: Optional[Dict] = None):
        try:
            frappe.get_doc({
                "doctype": "AI Routing Audit Log",
                "skill": "crm_agent",
                "agent": self.agent_name,
                "intent": intent,
                "decision": decision,
                "payload": frappe.as_json(payload or {}),
                "user": frappe.session.user,
            }).insert(ignore_permissions=True)
        except Exception:
            # Audit log is best-effort; never break the user-facing flow.
            pass
