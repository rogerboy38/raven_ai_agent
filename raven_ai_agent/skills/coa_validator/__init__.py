"""COA Validator skill package.

SKILL_CLASS export is required for the framework SkillRegistry
(skills/framework.py discover_skills) — without it this skill is invisible
to the V2 pipeline and only reachable via the legacy hardcoded block in
skills/router.py (T141).
"""
from raven_ai_agent.skills.coa_validator.skill import COAValidatorSkill

SKILL_CLASS = COAValidatorSkill

__all__ = ["COAValidatorSkill", "SKILL_CLASS"]
