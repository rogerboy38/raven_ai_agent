"""
Message Router - Multi-Agent Routing System
Inspired by OpenClaw's routing architecture

Routes incoming messages to appropriate handlers based on intent and context.
"""

import frappe
import re
from typing import Dict, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum


class RouteType(Enum):
    """Types of message routes"""
    QUERY = "query"           # Information retrieval
    COMMAND = "command"       # Execute action
    WORKFLOW = "workflow"     # Multi-step process
    CONVERSATION = "conversation"  # General chat
    VOICE = "voice"           # Voice command
    SKILL = "skill"           # Specific skill invocation


@dataclass
class Route:
    """Represents a routing decision"""
    route_type: RouteType
    handler: str
    confidence: float
    extracted_params: Dict
    requires_confirmation: bool = False


class MessageRouter:
    """
    Intelligent message router for multi-agent system.
    
    Features:
    - Intent classification
    - Skill matching
    - Context-aware routing
    - Fallback handling
    """
    
    def __init__(self):
        self.skill_patterns: Dict[str, Dict] = {}
        self.command_patterns: List[Dict] = []
        self._register_default_patterns()
    
    def _register_default_patterns(self):
        """Register built-in routing patterns"""
        # ERPNext command patterns
        self.command_patterns = [
            {
                "pattern": r"(?:create|make|add)\s+(sales\s+order|invoice|quotation)",
                "handler": "erpnext_create",
                "route_type": RouteType.COMMAND,
                "requires_confirmation": True
            },
            {
                "pattern": r"(?:approve|reject|submit)\s+(.+)",
                "handler": "erpnext_workflow",
                "route_type": RouteType.WORKFLOW,
                "requires_confirmation": True
            },
            {
                "pattern": r"(?:show|list|get|find)\s+(?:my\s+)?(.+)",
                "handler": "erpnext_query",
                "route_type": RouteType.QUERY,
                "requires_confirmation": False
            },
            {
                "pattern": r"(?:help|capabilities|what can you do)",
                "handler": "help",
                "route_type": RouteType.QUERY,
                "requires_confirmation": False
            }
        ]
    
    def register_skill(
        self,
        skill_name: str,
        patterns: List[str],
        handler: str,
        description: str = ""
    ):
        """Register a new skill with its trigger patterns"""
        self.skill_patterns[skill_name] = {
            "patterns": [re.compile(p, re.IGNORECASE) for p in patterns],
            "handler": handler,
            "description": description
        }
    
    def route(self, message: str, context: Dict = None) -> Route:
        """
        Route a message to appropriate handler.
        
        Args:
            message: User's message
            context: Session context for context-aware routing
            
        Returns:
            Route object with handler and parameters
        """
        message_lower = message.lower().strip()
        context = context or {}
        
        # Check for explicit skill invocation (@skill_name)
        skill_match = re.match(r"@(\w+)\s*(.*)", message)
        if skill_match:
            skill_name = skill_match.group(1)
            skill_params = skill_match.group(2)
            if skill_name in self.skill_patterns:
                return Route(
                    route_type=RouteType.SKILL,
                    handler=self.skill_patterns[skill_name]["handler"],
                    confidence=1.0,
                    extracted_params={"skill": skill_name, "params": skill_params}
                )
        
        # Check command patterns
        for cmd in self.command_patterns:
            match = re.search(cmd["pattern"], message_lower)
            if match:
                return Route(
                    route_type=cmd["route_type"],
                    handler=cmd["handler"],
                    confidence=0.9,
                    extracted_params={"match": match.groups()},
                    requires_confirmation=cmd.get("requires_confirmation", False)
                )
        
        # Check skill patterns
        for skill_name, skill_info in self.skill_patterns.items():
            for pattern in skill_info["patterns"]:
                if pattern.search(message_lower):
                    return Route(
                        route_type=RouteType.SKILL,
                        handler=skill_info["handler"],
                        confidence=0.8,
                        extracted_params={"skill": skill_name}
                    )
        
        # Context-aware routing
        if context.get("pending_workflow"):
            return Route(
                route_type=RouteType.WORKFLOW,
                handler="continue_workflow",
                confidence=0.85,
                extracted_params={"workflow": context["pending_workflow"]}
            )
        
        # Default to conversation/query
        return Route(
            route_type=RouteType.CONVERSATION,
            handler="ai_agent",
            confidence=0.5,
            extracted_params={}
        )
    
    def get_available_skills(self) -> List[Dict]:
        """List all registered skills"""
        return [
            {
                "name": name,
                "description": info.get("description", ""),
                "handler": info["handler"]
            }
            for name, info in self.skill_patterns.items()
        ]


# Global router instance
message_router = MessageRouter()
