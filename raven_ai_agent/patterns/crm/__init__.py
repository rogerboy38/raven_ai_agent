"""
raven_ai_agent/patterns/
═══════════════════════════════════════════════════════════════════════════════
Cross-skill agentic patterns: guardrails + planner.

This package is the single source of truth for "is this agent action
permitted?" (`guardrails`) and "how should this goal be decomposed?"
(`planner`) across every raven_ai_agent skill.

Both modules are designed with stable public signatures so future swaps
to NeMo Guardrails / LangGraph / LLMCompiler don't ripple into call sites.

Usage
─────
    from raven_ai_agent.patterns.crm import guardrails, planner

    # Guardrails — pre-flight policy gate
    if guardrails.is_action_allowed("opportunity_mover", "stage_move", 3):
        opp.status = "Quotation"
        opp.save()

    # Planner — decompose a goal into Steps
    p = planner.Planner()
    plan = p.plan("Coach deal OPP-001", context={"opportunity": "OPP-001"})
    for step in plan.steps:
        print(step.description)

    # Or do both together via SkillDispatcher
    dispatcher = planner.SkillDispatcher(autonomy_level=2)
    dispatcher.register("lead_enricher", lead_enricher)
    dispatcher.register("deal_coach", deal_coach)
    result = dispatcher.execute(plan)

Module versioning
─────────────────
v0.1.0 — rule-based stubs, ladder + DocType policy, audit logging
v0.2.0 — LangGraph Plan-and-Execute swap (planner)
v0.3.0 — LangGraph interrupt() for human-approval flows (guardrails)
v1.0.0 — optional NeMo Guardrails Colang integration

Lives under raven_ai_agent v14.1.0+.
"""

from raven_ai_agent.patterns.crm import guardrails  # noqa: F401
from raven_ai_agent.patterns.crm import planner     # noqa: F401

# Convenience top-level exports for the most common call sites
from raven_ai_agent.patterns.crm.guardrails import (  # noqa: F401
    is_action_allowed,
    get_required_level,
    OBSERVE,
    SUGGEST,
    ENRICH,
    STAGE_MOVE,
    AUTONOMOUS,
)
from raven_ai_agent.patterns.crm.planner import (  # noqa: F401
    Planner,
    Plan,
    Step,
    SkillDispatcher,
    plan,  # module-level shim for PR #16 deal_coach.py compatibility
)

__version__ = "0.1.0"

__all__ = [
    # modules
    "guardrails",
    "planner",
    # guardrails API
    "is_action_allowed",
    "get_required_level",
    "OBSERVE",
    "SUGGEST",
    "ENRICH",
    "STAGE_MOVE",
    "AUTONOMOUS",
    # planner API
    "Planner",
    "Plan",
    "Step",
    "SkillDispatcher",
    "plan",
]
