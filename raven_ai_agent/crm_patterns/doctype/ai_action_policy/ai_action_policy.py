"""
raven_ai_agent/crm_patterns/doctype/ai_action_policy/ai_action_policy.py
═══════════════════════════════════════════════════════════════════════════════
Controller for the `AI Action Policy` DocType.

This DocType stores per-skill / per-action overrides consulted by
`raven_ai_agent.patterns.crm.guardrails.is_action_allowed()`. See the module
docstring in `guardrails.py` for the full lookup-order spec.

The controller is intentionally minimal — most logic lives in
`guardrails.py`. We only enforce a couple of integrity constraints here.
"""
from __future__ import annotations

import frappe
from frappe.model.document import Document


class AIActionPolicy(Document):
    def validate(self) -> None:
        """Enforce min_autonomy_level ∈ [0, 4] and basic field hygiene."""
        if self.min_autonomy_level is None:
            self.min_autonomy_level = 0
        if not (0 <= int(self.min_autonomy_level) <= 4):
            frappe.throw(
                "Min Autonomy Level must be between 0 and 4 "
                "(0=observe, 1=suggest, 2=enrich, 3=stage_move, 4=autonomous)."
            )

        if self.skill:
            self.skill = self.skill.strip()
        if self.action:
            self.action = self.action.strip().lower()

        # Mutually-exclusive sanity: blocked + require_human_approval makes no
        # sense (a blocked action will never reach the approval step).
        if self.blocked and self.require_human_approval:
            frappe.msgprint(
                "'Require Human Approval' is ignored when 'Blocked' is set — "
                "blocked actions never reach the approval step.",
                indicator="orange",
                alert=True,
            )
