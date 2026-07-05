"""
Skill Router for Raven AI Agent
================================
Routes incoming messages to appropriate skills based on triggers and patterns.
"""

import re
import frappe
from typing import Dict, List, Optional, Any


class SkillRouter:
    """
    Routes incoming queries to the appropriate skill handler.
    
    Skills register themselves with triggers (keywords) and patterns (regex).
    The router matches incoming queries and delegates to the best matching skill.
    """
    
    def __init__(self):
        self.skills: Dict[str, Any] = {}
        self._load_skills()
    
    def _load_skills(self):
        """R2: load every skill from the framework SkillRegistry — single
        source of truth. The old hardcoded import block silently diverged
        from the registry (coa_validator was reachable here but invisible
        to the V2 pipeline for months). Registry discovery + the
        AI Skill Registry doctype is_active flag now govern both routers."""
        try:
            from raven_ai_agent.skills.framework import get_registry

            registry = get_registry()
            for name, skill_class in registry.get_all().items():
                try:
                    skill = skill_class()
                    self.skills[getattr(skill, "name", name)] = skill
                except Exception as exc:  # noqa: BLE001
                    frappe.logger().warning(
                        f"[SkillRouter] could not instantiate {name}: {exc}"
                    )
        except Exception as exc:  # noqa: BLE001
            frappe.logger().error(f"[SkillRouter] registry load failed: {exc}")

    def route(self, query: str, context: Dict = None) -> Optional[Dict]:
        """
        Route a query to the best matching skill.
        
        Args:
            query: User's input query
            context: Session context
            
        Returns:
            Response dict from the handling skill, or None if no match
        """
        context = context or {}
        query_lower = query.lower()
        
        # Find matching skills
        matches = []
        
        for skill in self.skills.values():
            score = 0
            
            # Check triggers
            for trigger in skill.triggers:
                if trigger.lower() in query_lower:
                    score += 10
            
            # Check patterns
            if hasattr(skill, 'patterns'):
                for pattern in skill.patterns:
                    if re.search(pattern, query, re.IGNORECASE):
                        score += 20
            
            if score > 0:
                matches.append((skill, score))
        
        if not matches:
            return None
        
        # Sort by score (and priority as tiebreaker)
        matches.sort(key=lambda x: (x[1], getattr(x[0], 'priority', 50)), reverse=True)
        
        # Execute best match
        best_skill = matches[0][0]
        frappe.logger().info(f"[SkillRouter] Calling skill: {best_skill.name}")
        try:
            result = best_skill.handle(query, context)
            if isinstance(result, dict):
                result.setdefault("skill", getattr(best_skill, "name", "skill"))
            frappe.logger().info(f"[SkillRouter] Skill result: {result}")
            return result
        except Exception as e:
            frappe.logger().error(f"[SkillRouter] Error in skill {best_skill.name}: {e}")
            return None
    
    def can_handle(self, query: str) -> bool:
        """Check if any skill can handle this query."""
        query_lower = query.lower()
        
        for skill in self.skills.values():
            for trigger in skill.triggers:
                if trigger.lower() in query_lower:
                    return True
            
            if hasattr(skill, 'patterns'):
                for pattern in skill.patterns:
                    if re.search(pattern, query, re.IGNORECASE):
                        return True
        
        return False
