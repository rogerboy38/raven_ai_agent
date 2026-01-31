"""
Agent V2 - Multi-Provider Support
Drop-in replacement for the original agent.py with provider abstraction
"""

import frappe
import json
from typing import Optional, Dict, List

# Import the provider system
from raven_ai_agent.providers import get_provider, LLMProvider
from raven_ai_agent.utils.cost_monitor import CostMonitor


class RaymondLucyAgentV2:
    """
    Enhanced AI Agent with Multi-Provider Support
    
    Supports: OpenAI, DeepSeek, Claude, MiniMax, Ollama
    
    Usage:
        agent = RaymondLucyAgentV2(user="user@example.com")
        result = agent.process_query("Show my pending invoices")
    """
    
    def __init__(self, user: str, provider_override: str = None):
        """
        Initialize the agent
        
        Args:
            user: Frappe user email
            provider_override: Force specific provider (ignores settings)
        """
        self.user = user
        self.settings = self._get_settings()
        
        # Get provider (override or from settings)
        provider_name = provider_override or self.settings.get("default_provider", "openai")
        
        try:
            self.provider = get_provider(provider_name.lower(), self.settings)
            self.cost_monitor = CostMonitor()
            frappe.logger().info(f"[AI Agent V2] Using provider: {provider_name}")
        except Exception as e:
            # Fallback to configured fallback provider
            fallback = self.settings.get("fallback_provider")
            if fallback and fallback != provider_name:
                frappe.logger().warning(f"[AI Agent V2] Primary provider failed, using fallback: {fallback}")
                self.provider = get_provider(fallback.lower(), self.settings)
            else:
                raise ValueError(f"Failed to initialize provider: {e}")
        
        self.autonomy_level = 1  # Default COPILOT
    
    def _safe_get_password(self, settings, field_name):
        """Safely get password field"""
        try:
            return settings.get_password(field_name)
        except Exception:
            return None
    
    def _get_settings(self) -> Dict:
        """Load AI Agent Settings with all provider configs"""
        try:
            settings = frappe.get_single("AI Agent Settings")
            return {
                # General
                "default_provider": getattr(settings, "default_provider", "OpenAI"),
                "fallback_provider": getattr(settings, "fallback_provider", None),
                "max_tokens": settings.max_tokens or 2000,
                "confidence_threshold": settings.confidence_threshold or 0.7,
                
                # OpenAI
                "openai_api_key": settings.get_password("openai_api_key"),
                "model": settings.model or "gpt-4o-mini",
                
                # DeepSeek
                "deepseek_api_key": self._safe_get_password(settings, "deepseek_api_key"),
                "deepseek_model": getattr(settings, "deepseek_model", "deepseek-chat"),
                "deepseek_use_reasoning": getattr(settings, "deepseek_use_reasoning", False),
                
                # Claude
                "claude_api_key": self._safe_get_password(settings, "claude_api_key"),
                "claude_model": getattr(settings, "claude_model", "claude-3-5-sonnet-20241022"),
                
                # MiniMax
                "minimax_api_key": self._safe_get_password(settings, "minimax_api_key"),
                "minimax_group_id": getattr(settings, "minimax_group_id", None),
                
                # Ollama (future)
                "ollama_base_url": getattr(settings, "ollama_base_url", "http://localhost:11434"),
                "ollama_model": getattr(settings, "ollama_model", "llama3.1:8b"),
            }
        except Exception as e:
            frappe.logger().error(f"[AI Agent V2] Failed to load settings: {e}")
            return {}
    
    def process_query(self, query: str, conversation_history: List[Dict] = None) -> Dict:
        """
        Main processing function - compatible with V1 API
        
        Args:
            query: User's question/command
            conversation_history: Previous messages
            
        Returns:
            {
                "success": bool,
                "response": str,
                "autonomy_level": int,
                "context_used": dict,
                "provider": str  # NEW: which provider was used
            }
        """
        # Import original agent components
        from raven_ai_agent.api.agent import RaymondLucyAgent, SYSTEM_PROMPT, CAPABILITIES_LIST
        
        query_lower = query.lower()
        
        # Handle help command
        if any(h in query_lower for h in ["help", "capabilities", "what can you do"]):
            return {
                "success": True,
                "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 1]\n{CAPABILITIES_LIST}",
                "autonomy_level": 1,
                "context_used": {"help": True},
                "provider": self.provider.name
            }
        
        # Create temporary V1 agent for context/workflow methods
        v1_agent = RaymondLucyAgent(self.user)
        
        # Try workflow command first
        workflow_result = v1_agent.execute_workflow_command(query)
        if workflow_result:
            return self._format_workflow_result(workflow_result)
        
        # Build context using V1 methods
        morning_briefing = v1_agent.get_morning_briefing()
        erpnext_context = v1_agent.get_erpnext_context(query)
        relevant_memories = v1_agent.search_memories(query)
        memories_text = "\n".join([f"- {m['content']}" for m in relevant_memories])
        
        # Build messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"## Context\n{morning_briefing}\n\n## ERPNext Data\n{erpnext_context}\n\n## Relevant Memories\n{memories_text}"}
        ]
        
        if conversation_history:
            messages.extend(conversation_history[-10:])
        
        suggested_autonomy = v1_agent.determine_autonomy(query)
        autonomy_warning = ""
        if suggested_autonomy >= 2:
            autonomy_warning = f"\n\n⚠️ This suggests LEVEL {suggested_autonomy} autonomy. Confirm before executing changes."
        
        messages.append({"role": "user", "content": query + autonomy_warning})
        
        # Call LLM using new provider system
        try:
            # Check if DeepSeek reasoning mode is enabled
            if (self.provider.name == "deepseek" and 
                self.settings.get("deepseek_use_reasoning") and
                suggested_autonomy >= 2):
                # Use reasoning mode for complex operations
                result = self.provider.chat_with_reasoning(
                    messages=messages,
                    max_tokens=self.settings.get("max_tokens", 2000)
                )
                answer = f"**Reasoning:**\n{result['reasoning']}\n\n**Answer:**\n{result['answer']}"
            else:
                result = self.provider.chat(
                    messages=messages,
                    max_tokens=self.settings.get("max_tokens", 2000),
                    temperature=0.3,
                    return_usage=True
                )
                answer = result.get("content", result) if isinstance(result, dict) else result
                
                # Track usage for cost monitoring
                if isinstance(result, dict) and "usage" in result:
                    usage = result["usage"]
                    self.cost_monitor.track_usage(
                        user=self.user,
                        provider=self.provider.name,
                        model=self.provider.model,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0)
                    )
                    
                    # Check budget warning
                    budget_warning = self.cost_monitor.check_budget(self.user)
                    if budget_warning:
                        answer = f"⚠️ **Cost Warning:** {budget_warning}\n\n{answer}"
            
            return {
                "success": True,
                "response": answer,
                "autonomy_level": suggested_autonomy,
                "context_used": {
                    "memories": len(relevant_memories),
                    "erpnext_data": bool(erpnext_context)
                },
                "provider": self.provider.name
            }
            
        except Exception as e:
            frappe.logger().error(f"[AI Agent V2] Provider error: {e}")
            
            # Try fallback provider
            fallback = self.settings.get("fallback_provider")
            if fallback and fallback.lower() != self.provider.name:
                try:
                    fallback_provider = get_provider(fallback.lower(), self.settings)
                    answer = fallback_provider.chat(messages=messages)
                    return {
                        "success": True,
                        "response": answer + f"\n\n*[Used fallback: {fallback}]*",
                        "autonomy_level": suggested_autonomy,
                        "provider": fallback
                    }
                except Exception as e2:
                    pass
            
            return {
                "success": False,
                "error": str(e),
                "response": f"[CONFIDENCE: UNCERTAIN]\n\nError: {str(e)}",
                "provider": self.provider.name
            }
    
    def _format_workflow_result(self, result: Dict) -> Dict:
        """Format workflow result to match V1 API"""
        if result.get("requires_confirmation"):
            return {
                "success": True,
                "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 2]\n\n{result['preview']}",
                "autonomy_level": 2,
                "context_used": {"workflow": True},
                "provider": self.provider.name
            }
        elif result.get("success"):
            return {
                "success": True,
                "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 2]\n\n{result.get('message', 'Done.')}",
                "autonomy_level": 2,
                "provider": self.provider.name
            }
        else:
            return {
                "success": False,
                "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 2]\n\n❌ {result.get('error')}",
                "autonomy_level": 2,
                "provider": self.provider.name
            }


# API Endpoints

@frappe.whitelist()
def process_message_v2(message: str, conversation_history: str = None, provider: str = None) -> Dict:
    """
    API endpoint for V2 agent
    
    Args:
        message: User query
        conversation_history: JSON string of previous messages
        provider: Override provider (optional)
    """
    user = frappe.session.user
    agent = RaymondLucyAgentV2(user, provider_override=provider)
    
    history = json.loads(conversation_history) if conversation_history else []
    
    return agent.process_query(message, history)


@frappe.whitelist()
def get_available_providers() -> Dict:
    """List available and configured providers"""
    settings = frappe.get_single("AI Agent Settings")
    
    providers = {
        "openai": {
            "name": "OpenAI",
            "configured": bool(settings.get_password("openai_api_key") if hasattr(settings, "openai_api_key") else None),
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
        },
        "deepseek": {
            "name": "DeepSeek",
            "configured": bool(settings.get_password("deepseek_api_key") if hasattr(settings, "deepseek_api_key") else None),
            "models": ["deepseek-chat", "deepseek-reasoner"]
        },
        "claude": {
            "name": "Claude",
            "configured": bool(settings.get_password("claude_api_key") if hasattr(settings, "claude_api_key") else None),
            "models": ["claude-3-5-sonnet", "claude-3-opus"]
        },
        "minimax": {
            "name": "MiniMax",
            "configured": bool(settings.get_password("minimax_api_key") if hasattr(settings, "minimax_api_key") else None),
            "models": ["abab6.5-chat", "abab5.5-chat"]
        }
    }
    
    return {
        "default": getattr(settings, "default_provider", "OpenAI"),
        "providers": providers
    }
