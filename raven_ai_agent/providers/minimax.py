"""
MiniMax LLM Provider - The Jewel of the Crown 👑
https://api.minimax.chat/

Models:
- abab6.5s-chat - Latest flagship model (MiniMax-Text-01)
- abab6.5g-chat - General purpose
- abab5.5-chat - Legacy model

Special Features:
- Excellent Chinese language support
- Voice synthesis integration (T2A)
- Long context (up to 1M tokens with abab6.5s)
- Very competitive pricing
"""

import frappe
import httpx
from typing import Dict, List, Optional, Generator
from .base import LLMProvider


class MiniMaxProvider(LLMProvider):
    """
    MiniMax API Provider - Chinese AI Powerhouse
    
    Features:
    - 1M token context window (abab6.5s)
    - Excellent Chinese/English bilingual
    - Voice synthesis built-in
    - Competitive pricing
    - Good for business applications
    """
    
    name = "minimax"
    BASE_URL = "https://api.minimax.io/v1"
    
    MODELS = {
        "abab6.5s-chat": "Flagship model, 1M context, best quality",
        "abab6.5g-chat": "General purpose, 245K context",
        "abab6.5t-chat": "Turbo mode, faster responses",
        "abab5.5-chat": "Legacy model, stable",
    }
    
    # Pricing per 1M tokens (USD) - approximate
    PRICING = {
        "abab6.5s-chat": {"input": 1.00, "output": 4.00},
        "abab6.5g-chat": {"input": 0.50, "output": 2.00},
        "abab6.5t-chat": {"input": 0.30, "output": 1.20},
        "abab5.5-chat": {"input": 0.20, "output": 0.80},
    }
    
    DEFAULT_MODEL = "abab6.5s-chat"
    
    def __init__(self, settings: Dict):
        super().__init__(settings)
        
        api_key = settings.get("minimax_api_key")
        group_id = settings.get("minimax_group_id")
        
        if not api_key:
            try:
                agent_settings = frappe.get_single("AI Agent Settings")
                api_key = agent_settings.get_password("minimax_api_key")
                group_id = getattr(agent_settings, "minimax_group_id", None)
            except Exception:
                pass
        
        if not api_key:
            raise ValueError("MiniMax API key not configured")
        
        self.api_key = api_key
        self.group_id = group_id or "0"  # Default group
        self.default_model = settings.get("minimax_model", self.DEFAULT_MODEL)
    
    def chat(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> str:
        """Send chat request to MiniMax API"""
        model = model or self.default_model
        
        # Convert to MiniMax format
        minimax_messages = []
        system_prompt = ""
        
        for msg in messages:
            if msg["role"] == "system":
                system_prompt += msg["content"] + "\n"
            else:
                minimax_messages.append({
                    "sender_type": "USER" if msg["role"] == "user" else "BOT",
                    "sender_name": "user" if msg["role"] == "user" else "assistant",
                    "text": msg["content"]
                })
        
        # Use chatcompletion_v2 for OpenAI-compatible format
        url = f"{self.BASE_URL}/text/chatcompletion_v2"
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False
                }
            )
            
            response.raise_for_status()
            data = response.json()
            
            if data.get("base_resp", {}).get("status_code") != 0:
                error_msg = data.get("base_resp", {}).get("status_msg", "Unknown error")
                raise Exception(f"MiniMax API error: {error_msg}")
            
            return data["choices"][0]["message"]["content"]
    
    def chat_stream(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> Generator[str, None, None]:
        """Stream response from MiniMax"""
        model = model or self.default_model
        
        with httpx.Client(timeout=60.0) as client:
            url = f"{self.BASE_URL}/text/chatcompletion_v2"
            with client.stream(
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True
                }
            ) as response:
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        import json
                        data = json.loads(line[6:])
                        if data.get("choices"):
                            delta = data["choices"][0].get("delta", {})
                            if delta.get("content"):
                                yield delta["content"]
    
    def text_to_speech(
        self,
        text: str,
        voice_id: str = "male-qn-qingse",
        speed: float = 1.0
    ) -> bytes:
        """
        Convert text to speech using MiniMax T2A
        
        Voice IDs:
        - male-qn-qingse: Young male
        - female-shaonv: Young female
        - female-yujie: Mature female
        - male-qn-jingying: Professional male
        """
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.BASE_URL}/t2a_v2",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "speech-01-turbo",
                    "text": text,
                    "voice_setting": {
                        "voice_id": voice_id,
                        "speed": speed
                    },
                    "audio_setting": {
                        "format": "mp3",
                        "sample_rate": 32000
                    }
                }
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Decode base64 audio
            import base64
            return base64.b64decode(data["data"]["audio"])
    
    def get_pricing(self, model: str = None) -> Dict[str, float]:
        """Get pricing for model"""
        model = model or self.default_model
        return self.PRICING.get(model, {"input": 0, "output": 0})
    
    def get_default_model(self) -> str:
        return self.default_model
    
    @classmethod
    def get_available_voices(cls) -> Dict[str, str]:
        """List available TTS voices"""
        return {
            "male-qn-qingse": "Young Male (清澈)",
            "female-shaonv": "Young Female (少女)",
            "female-yujie": "Mature Female (御姐)",
            "male-qn-jingying": "Professional Male (精英)",
            "male-qn-badao": "Authoritative Male (霸道)",
            "female-tianmei": "Sweet Female (甜美)",
        }
