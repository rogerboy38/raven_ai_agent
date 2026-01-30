"""
Multi-LLM Provider System for Raven AI Agent
Supports: OpenAI, DeepSeek, Claude, MiniMax, Ollama
"""

from typing import Dict, Optional
from .base import LLMProvider
from .openai_provider import OpenAIProvider
from .deepseek import DeepSeekProvider
from .claude import ClaudeProvider
from .minimax import MiniMaxProvider


def get_provider(provider_name: str, settings: Dict) -> LLMProvider:
    """Factory function to get the appropriate LLM provider"""
    
    providers = {
        "openai": OpenAIProvider,
        "deepseek": DeepSeekProvider,
        "claude": ClaudeProvider,
        "minimax": MiniMaxProvider,
        # "ollama": OllamaProvider,      # Coming soon
    }
    
    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"Unknown provider: {provider_name}. Available: {list(providers.keys())}")
    
    return provider_class(settings)


__all__ = [
    "LLMProvider",
    "OpenAIProvider", 
    "DeepSeekProvider",
    "ClaudeProvider",
    "MiniMaxProvider",
    "get_provider"
]
