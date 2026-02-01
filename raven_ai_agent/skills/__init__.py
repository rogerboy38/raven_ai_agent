"""
Skills Module - Extensible Agent Capabilities
=============================================

A dynamic skill system with:
- Auto-discovery of skills from subdirectories
- Learning-based query routing
- Standard SkillBase interface

Usage:
    from raven_ai_agent.skills import get_router, list_available_skills
    
    router = get_router(agent)
    result = router.route("scan migration 2024")
"""

# Core framework
from raven_ai_agent.skills.framework import (
    SkillBase,
    SkillRegistry,
    SkillRouter,
    SkillLearner,
    get_registry,
    get_router,
    list_available_skills
)

# Built-in skills
from raven_ai_agent.skills.browser import BrowserSkill

__all__ = [
    # Framework
    "SkillBase",
    "SkillRegistry", 
    "SkillRouter",
    "SkillLearner",
    "get_registry",
    "get_router",
    "list_available_skills",
    # Skills
    "BrowserSkill"
]
