"""BOM Agent skill package — SKILL_CLASS export required for registry discovery."""
from raven_ai_agent.skills.bom_agent.skill import BOMAgentSkill

SKILL_CLASS = BOMAgentSkill
__all__ = ["BOMAgentSkill", "SKILL_CLASS"]
