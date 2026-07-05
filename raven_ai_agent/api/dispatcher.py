"""
Unified dispatcher — Phase R2 of the raven-smarter remake.

ONE ordered routing path for every chat command entering Pipeline V2:

    1. skill_exact       framework SkillRegistry, confidence >= 0.90
                         (explicit document ids: COA-xx-xxxx, etc.)
    2. multi_agent       deterministic regex pipelines (workflow run SO-…,
                         full status SO-…, morning briefing, …)
    3. semantic_pipeline Coordinator pattern maps free-form phrasing to a
                         pipeline key (second chance for stage 2, needs LLM)
    4. agent_v2          RaymondLucyAgentV2.process_query — help, broad
                         skills, workflow commands, then provider LLM

Every result carries a ``stage`` key which pipeline_v2 writes into
AI Routing Audit Log.resolved_intent, so misroutes are observable.
"""

from typing import Dict

import frappe

STAGE_SKILL_EXACT = "skill_exact"
STAGE_MULTI_AGENT = "multi_agent"
STAGE_SEMANTIC = "semantic_pipeline"
STAGE_AGENT = "agent_v2"

EXACT_SKILL_CONFIDENCE = 0.90


def route(query: str, user: str) -> Dict:
    """Route a chat command through the ordered stages. Returns the V2-shaped
    result dict with an added ``stage`` key. Never raises for stage failures —
    a broken stage falls through to the next one."""
    from raven_ai_agent.api.agent_v2 import RaymondLucyAgentV2

    agent = RaymondLucyAgentV2(user=user)

    # ---- Stage 1: exact skill match ------------------------------------
    try:
        router = agent.skill_router
        matches = sorted(
            router._find_matches(query), key=lambda m: (m[1], m[2]), reverse=True
        )
        if matches and matches[0][1] >= EXACT_SKILL_CONFIDENCE:
            res = router.route(query, context={"user": user})
            if res and res.get("handled"):
                skill = res.get("skill") or matches[0][0]
                return {
                    "success": True,
                    "response": f"[CONFIDENCE: HIGH] [SKILL: {skill}]\n\n{res.get('response', '')}",
                    "autonomy_level": 1,
                    "context_used": {"skill": skill},
                    "provider": "skill",
                    "skill_used": skill,
                    "stage": STAGE_SKILL_EXACT,
                }
    except Exception:
        frappe.logger().warning("[Dispatcher] skill_exact stage failed", exc_info=True)

    # ---- Stage 2: deterministic multi-agent pipelines -------------------
    try:
        from raven_ai_agent.api.multi_agent_router import handle_multi_agent_command

        resp = handle_multi_agent_command(query, user)
        if resp:
            return {
                "success": True,
                "response": resp,
                "autonomy_level": 1,
                "context_used": {"pipeline": True},
                "provider": "pipeline",
                "stage": STAGE_MULTI_AGENT,
            }
    except Exception:
        frappe.logger().warning("[Dispatcher] multi_agent stage failed", exc_info=True)

    # ---- Stage 3: semantic coordinator → pipeline key --------------------
    if agent.provider is not None:
        try:
            from raven_ai_agent.api.multi_agent_router import (
                build_agent_pipeline,
                execute_pipeline,
                semantic_route,
            )

            key = semantic_route(query, agent.provider)
            if key:
                pipeline = build_agent_pipeline(query, pipeline_type=key)
                if pipeline:
                    resp = execute_pipeline(pipeline, user)
                    if resp:
                        return {
                            "success": True,
                            "response": resp,
                            "autonomy_level": 1,
                            "context_used": {"pipeline": key, "semantic": True},
                            "provider": "pipeline",
                            "stage": STAGE_SEMANTIC,
                        }
        except Exception:
            frappe.logger().warning("[Dispatcher] semantic stage failed", exc_info=True)

    # ---- Stage 4: full V2 agent -----------------------------------------
    result = agent.process_query(query)
    if isinstance(result, dict):
        if result.get("skill_used"):
            result["stage"] = "skill"
        elif (result.get("context_used") or {}).get("workflow"):
            result["stage"] = "workflow"
        else:
            result["stage"] = STAGE_AGENT
    return result
