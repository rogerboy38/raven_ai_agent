"""
Skill Framework for RaymondLucyAgent
====================================

A dynamic, auto-learning skill system that:
1. Auto-discovers skills from the skills/ directory
2. Routes queries to the appropriate skill
3. Learns from usage patterns to improve routing
4. Allows new skills to be added without code changes

Architecture:
    SkillBase (abstract) -> Individual Skills
    SkillRegistry -> Discovers and manages skills
    SkillRouter -> Routes queries with ML-like matching
    SkillLearner -> Tracks patterns and improves over time
"""

import frappe
import os
import re
import json
import importlib
import pkgutil
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Callable
from datetime import datetime
from pathlib import Path


# ===========================================
# Skill Base Class
# ===========================================

class SkillBase(ABC):
    """
    Abstract base class for all skills.
    
    Every skill must implement:
        - name: Unique skill identifier
        - description: What the skill does
        - triggers: List of trigger phrases/patterns
        - handle(): Process the query
    """
    
    name: str = "base"
    description: str = "Base skill"
    emoji: str = "🔧"
    version: str = "1.0.0"
    
    # Trigger configuration
    triggers: List[str] = []  # Simple keyword triggers
    patterns: List[str] = []  # Regex patterns
    priority: int = 50  # 0-100, higher = checked first
    
    def __init__(self, agent=None):
        """Initialize skill with optional agent reference"""
        self.agent = agent
        self._usage_count = 0
        self._success_count = 0
    
    @abstractmethod
    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """
        Handle a query if this skill can process it.
        
        Args:
            query: The user's query
            context: Optional context (user, history, etc.)
            
        Returns:
            None if skill doesn't handle this query
            Dict with response if handled:
                {
                    "handled": True,
                    "response": str,
                    "confidence": float (0-1),
                    "data": Any (optional)
                }
        """
        pass
    
    def can_handle(self, query: str) -> Tuple[bool, float]:
        """
        Check if this skill can handle the query.
        
        Returns:
            (can_handle: bool, confidence: float)
        """
        query_lower = query.lower()
        
        # Check simple triggers
        for trigger in self.triggers:
            if trigger.lower() in query_lower:
                return True, 0.8
        
        # Check regex patterns
        for pattern in self.patterns:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True, 0.9
        
        return False, 0.0
    
    def get_help(self) -> str:
        """Return help text for this skill"""
        return f"**{self.emoji} {self.name}**: {self.description}"
    
    def record_usage(self, success: bool = True):
        """Record skill usage for learning"""
        self._usage_count += 1
        if success:
            self._success_count += 1
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self._usage_count == 0:
            return 1.0
        return self._success_count / self._usage_count


# ===========================================
# Skill Registry
# ===========================================

class SkillRegistry:
    """
    Manages skill discovery and registration.
    
    Auto-discovers skills from:
        1. raven_ai_agent/skills/ directory
        2. Manually registered skills
        3. External skill packages
    """
    
    _instance = None
    _skills: Dict[str, SkillBase] = {}
    _initialized = False
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._skills = {}
            self._initialized = True
    
    def discover_skills(self, skills_path: str = None):
        """
        Auto-discover skills from the skills directory.
        
        Looks for:
            - __init__.py with a SKILL_CLASS export
            - Classes inheriting from SkillBase
            - SKILL.md for metadata
        """
        if skills_path is None:
            skills_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "skills"
            )
        
        if not os.path.exists(skills_path):
            frappe.logger().warning(f"[SkillRegistry] Skills path not found: {skills_path}")
            return
        
        # Scan for skill directories
        for item in os.listdir(skills_path):
            skill_dir = os.path.join(skills_path, item)
            
            if not os.path.isdir(skill_dir):
                continue
            
            if item.startswith("_"):
                continue
            
            # Try to load the skill
            try:
                self._load_skill_from_dir(item, skill_dir)
            except Exception as e:
                frappe.logger().error(f"[SkillRegistry] Failed to load skill '{item}': {e}")
    
    def _load_skill_from_dir(self, skill_name: str, skill_dir: str):
        """Load a skill from its directory"""
        # Check for SKILL.md metadata
        skill_md = os.path.join(skill_dir, "SKILL.md")
        metadata = {}
        
        if os.path.exists(skill_md):
            metadata = self._parse_skill_md(skill_md)
        
        # Try to import the skill module
        try:
            module_name = f"raven_ai_agent.skills.{skill_name}"
            module = importlib.import_module(module_name)
            
            # Look for SKILL_CLASS or auto-detect
            skill_class = getattr(module, "SKILL_CLASS", None)
            
            if skill_class is None:
                # Auto-detect SkillBase subclasses
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, SkillBase) and 
                        attr is not SkillBase):
                        skill_class = attr
                        break
            
            if skill_class:
                self.register(skill_class, metadata)
                frappe.logger().info(f"[SkillRegistry] Loaded skill: {skill_name}")
            else:
                # Register as a function-based skill
                handler = getattr(module, "handle_command", None) or \
                          getattr(module, "handle_migration_command", None) or \
                          getattr(module, "handle", None)
                
                if handler:
                    self._register_function_skill(skill_name, handler, metadata)
                    
        except ImportError as e:
            frappe.logger().debug(f"[SkillRegistry] Could not import {skill_name}: {e}")
    
    def _parse_skill_md(self, filepath: str) -> Dict:
        """Parse SKILL.md frontmatter"""
        metadata = {}
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Parse YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                import yaml
                try:
                    metadata = yaml.safe_load(parts[1])
                except:
                    pass
        
        return metadata or {}
    
    def _register_function_skill(self, name: str, handler: Callable, metadata: Dict):
        """Wrap a function as a skill"""
        
        class FunctionSkill(SkillBase):
            pass
        
        FunctionSkill.name = name
        FunctionSkill.description = metadata.get("description", f"{name} skill")
        FunctionSkill.emoji = metadata.get("metadata", {}).get("raven", {}).get("emoji", "🔧")
        FunctionSkill.triggers = metadata.get("triggers", [name.replace("-", " "), name.replace("_", " ")])
        
        def handle_wrapper(self, query: str, context: Dict = None):
            result = handler(query)
            if result:
                return {
                    "handled": True,
                    "response": result,
                    "confidence": 0.9
                }
            return None
        
        FunctionSkill.handle = handle_wrapper
        self.register(FunctionSkill, metadata)
    
    def register(self, skill_class: type, metadata: Dict = None):
        """Register a skill class"""
        if metadata:
            # Override class attributes with metadata
            if "name" in metadata:
                skill_class.name = metadata["name"]
            if "description" in metadata:
                skill_class.description = metadata["description"]
            if "triggers" in metadata:
                skill_class.triggers = metadata["triggers"]
        
        self._skills[skill_class.name] = skill_class
    
    def get(self, name: str) -> Optional[type]:
        """Get a skill class by name"""
        return self._skills.get(name)
    
    def list_skills(self) -> List[str]:
        """List all registered skill names"""
        return list(self._skills.keys())
    
    def get_all(self) -> Dict[str, type]:
        """Get all registered skills"""
        return self._skills.copy()
    
    def instantiate(self, name: str, agent=None) -> Optional[SkillBase]:
        """Create an instance of a skill"""
        skill_class = self.get(name)
        if skill_class:
            return skill_class(agent=agent)
        return None


# ===========================================
# Skill Router
# ===========================================

class SkillRouter:
    """
    Routes queries to the appropriate skill.
    
    Uses multiple matching strategies:
        1. Exact trigger matching
        2. Pattern matching
        3. Semantic similarity (if LLM available)
        4. Learning from past matches
    """
    
    def __init__(self, registry: SkillRegistry = None, agent=None):
        self.registry = registry or SkillRegistry()
        self.agent = agent
        self._skill_instances: Dict[str, SkillBase] = {}
        self._learner = SkillLearner()
    
    def _get_or_create_skill(self, name: str) -> Optional[SkillBase]:
        """Get or create a skill instance"""
        if name not in self._skill_instances:
            instance = self.registry.instantiate(name, self.agent)
            if instance:
                self._skill_instances[name] = instance
        return self._skill_instances.get(name)
    
    def route(self, query: str, context: Dict = None) -> Optional[Dict]:
        """
        Route a query to the best matching skill.
        
        Returns:
            {
                "skill": str,
                "response": str,
                "confidence": float,
                "handled": bool
            }
        """
        # Get all skill matches with confidence
        matches = self._find_matches(query)
        
        if not matches:
            return None
        
        # Sort by confidence and priority
        matches.sort(key=lambda x: (x[1], x[2]), reverse=True)
        
        # Try skills in order until one handles the query
        for skill_name, confidence, priority in matches:
            skill = self._get_or_create_skill(skill_name)
            if not skill:
                continue
            
            try:
                result = skill.handle(query, context)
                
                if result and result.get("handled"):
                    # Record successful match for learning
                    self._learner.record_match(query, skill_name, success=True)
                    skill.record_usage(success=True)
                    
                    return {
                        "skill": skill_name,
                        "response": result.get("response", ""),
                        "confidence": result.get("confidence", confidence),
                        "handled": True,
                        "data": result.get("data")
                    }
            except Exception as e:
                frappe.logger().error(f"[SkillRouter] Error in skill {skill_name}: {e}")
                skill.record_usage(success=False)
        
        return None
    
    def _find_matches(self, query: str) -> List[Tuple[str, float, int]]:
        """
        Find all potentially matching skills.
        
        Returns list of (skill_name, confidence, priority)
        """
        matches = []
        
        for name, skill_class in self.registry.get_all().items():
            skill = self._get_or_create_skill(name)
            if not skill:
                continue
            
            can_handle, confidence = skill.can_handle(query)
            
            if can_handle:
                # Boost confidence based on learning
                learned_boost = self._learner.get_confidence_boost(query, name)
                final_confidence = min(1.0, confidence + learned_boost)
                
                matches.append((name, final_confidence, skill.priority))
        
        return matches
    
    def get_skills_help(self) -> str:
        """Generate help text for all skills"""
        lines = ["**Available Skills:**\n"]
        
        for name in sorted(self.registry.list_skills()):
            skill = self._get_or_create_skill(name)
            if skill:
                lines.append(skill.get_help())
        
        return "\n".join(lines)


# ===========================================
# Skill Learner
# ===========================================

class SkillLearner:
    """
    Learns from skill usage patterns to improve routing.
    
    Tracks:
        - Query patterns that match skills
        - Success/failure rates
        - User preferences
    """
    
    def __init__(self):
        self._patterns: Dict[str, Dict] = {}  # query_pattern -> {skill: count}
        self._cache_file = None
    
    def record_match(self, query: str, skill: str, success: bool = True):
        """Record a query-skill match"""
        # Extract key patterns from query
        patterns = self._extract_patterns(query)
        
        for pattern in patterns:
            if pattern not in self._patterns:
                self._patterns[pattern] = {}
            
            if skill not in self._patterns[pattern]:
                self._patterns[pattern][skill] = {"success": 0, "fail": 0}
            
            if success:
                self._patterns[pattern][skill]["success"] += 1
            else:
                self._patterns[pattern][skill]["fail"] += 1
        
        # Persist periodically
        self._maybe_persist()
    
    def get_confidence_boost(self, query: str, skill: str) -> float:
        """
        Get confidence boost based on learning.
        
        Returns 0.0 to 0.2 boost based on past success
        """
        patterns = self._extract_patterns(query)
        total_score = 0.0
        pattern_count = 0
        
        for pattern in patterns:
            if pattern in self._patterns:
                skill_stats = self._patterns[pattern].get(skill, {})
                success = skill_stats.get("success", 0)
                fail = skill_stats.get("fail", 0)
                total = success + fail
                
                if total > 0:
                    pattern_count += 1
                    total_score += (success / total) * 0.2
        
        if pattern_count > 0:
            return total_score / pattern_count
        
        return 0.0
    
    def _extract_patterns(self, query: str) -> List[str]:
        """Extract learnable patterns from a query"""
        patterns = []
        query_lower = query.lower()
        
        # Extract 2-grams and 3-grams
        words = query_lower.split()
        
        for i in range(len(words) - 1):
            patterns.append(" ".join(words[i:i+2]))
        
        for i in range(len(words) - 2):
            patterns.append(" ".join(words[i:i+3]))
        
        # Extract key action words
        action_words = ["scan", "fix", "compare", "report", "show", "list", 
                       "create", "update", "delete", "migrate", "validate"]
        
        for word in action_words:
            if word in query_lower:
                patterns.append(word)
        
        return patterns
    
    def _maybe_persist(self):
        """Persist learning data periodically"""
        # Could save to DocType or file
        pass
    
    def load(self, filepath: str = None):
        """Load persisted learning data"""
        pass
    
    def save(self, filepath: str = None):
        """Save learning data"""
        pass


# ===========================================
# Convenience Functions
# ===========================================

def get_registry() -> SkillRegistry:
    """Get the global skill registry"""
    registry = SkillRegistry()
    if not registry._skills:
        registry.discover_skills()
    return registry


def get_router(agent=None) -> SkillRouter:
    """Get a skill router instance"""
    return SkillRouter(get_registry(), agent)


def list_available_skills() -> List[Dict]:
    """List all available skills with metadata"""
    registry = get_registry()
    skills = []
    
    for name, skill_class in registry.get_all().items():
        skills.append({
            "name": name,
            "description": skill_class.description,
            "emoji": getattr(skill_class, "emoji", "🔧"),
            "triggers": skill_class.triggers[:5] if skill_class.triggers else []
        })
    
    return skills
