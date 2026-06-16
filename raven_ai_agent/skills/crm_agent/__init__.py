"""
CRM Agent Skill
===============
Agentic CRM for ERPNext / raven_ai_agent.

Exports SKILL_CLASS for SkillRegistry auto-discovery.
"""
from raven_ai_agent.skills.crm_agent.skill import CRMAgentSkill

SKILL_CLASS = CRMAgentSkill

__all__ = ["CRMAgentSkill", "SKILL_CLASS"]
