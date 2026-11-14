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
from .ollama import OllamaProvider


def _build(provider_name: str, settings: Dict) -> LLMProvider:
    providers = {
        "openai": OpenAIProvider,
        "deepseek": DeepSeekProvider,
        "claude": ClaudeProvider,
        "minimax": MiniMaxProvider,
        "ollama": OllamaProvider,
    }
    
    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"Unknown provider: {provider_name}. Available: {list(providers.keys())}")
    
    return provider_class(settings)


def get_provider(provider_name: str, settings: Dict) -> LLMProvider:
    """Factory: the provider named, wrapped with the fallback named in `settings["fallback_provider"]` (TASKS-344:
    a failed call is retried once on it). No wrapper when none is named or it is the same provider."""
    primary = _build(provider_name, settings)
    fallback = (settings or {}).get("fallback_provider")
    if fallback and str(fallback).strip().lower() not in ("", provider_name.lower()):
        from .failover import FailoverProvider

        fb = str(fallback).strip().lower()
        return FailoverProvider(primary, fb, lambda: _build(fb, settings))
    return primary


__all__ = [
    "LLMProvider",
    "OpenAIProvider", 
    "DeepSeekProvider",
    "ClaudeProvider",
    "MiniMaxProvider",
    "get_provider"
]
