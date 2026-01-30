"""
Base LLM Provider Abstract Class
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Generator


class LLMProvider(ABC):
    """Abstract base class for all LLM providers"""
    
    name: str = "base"
    
    def __init__(self, settings: Dict):
        self.settings = settings
    
    @abstractmethod
    def chat(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> str:
        """
        Send chat completion request
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (uses default if None)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response
            stream: Whether to stream response
            
        Returns:
            Response text or generator if streaming
        """
        pass
    
    @abstractmethod
    def chat_stream(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> Generator[str, None, None]:
        """Stream chat completion response"""
        pass
    
    def embed(self, text: str) -> List[float]:
        """Generate embedding for text (optional, not all providers support)"""
        raise NotImplementedError(f"{self.name} does not support embeddings")
    
    def get_default_model(self) -> str:
        """Get default model for this provider"""
        return self.settings.get("model", "default")
