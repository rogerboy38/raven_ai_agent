"""
MiniMax LLM Provider - The Jewel of the Crown 👑
https://api.minimax.io/v1

Models (live IDs, verified against api.minimax.io on 2026-11-19):
- MiniMax-M3         - flagship, 1M context, multimodal, agentic coding
- MiniMax-M3.1-Flash - cheapest current model, high throughput

Retired by MiniMax - the API answers HTTP 404 "no longer available":
- MiniMax-M2, MiniMax-M2.1, MiniMax-M2-Stable
- abab6.5-chat, abab5.5-chat, abab6.5s-chat, abab6.5g-chat

Special Features:
- Excellent Chinese language support
- Voice synthesis integration (T2A)
- Long context (up to 1M tokens with MiniMax-M3)
- Very competitive pricing
"""

import frappe
import httpx
from typing import Dict, List, Optional, Generator
from .base import LLMProvider
from ._secrets import resolve_secret


class MiniMaxProvider(LLMProvider):
    """
    MiniMax API Provider - Chinese AI Powerhouse
    
    Features:
    - 1M token context window (MiniMax-M3)
    - Excellent Chinese/English bilingual
    - Voice synthesis built-in
    - Competitive pricing
    - Good for business applications
    """
    
    name = "minimax"
    BASE_URL = "https://api.minimax.io/v1"
    
    # Only IDs MiniMax still serves. Model IDs are retired without notice and
    # a retired one answers HTTP 404 "no longer available", so anything absent
    # from this dict is refused by design.
    MODELS = {
        "MiniMax-M3": "Flagship - 1M context, multimodal, agentic coding",
        "MiniMax-M3.1-Flash": "Cheapest current model - high throughput",
    }
    
    # USD per 1M tokens, standard tier (platform.minimax.io pricing)
    PRICING = {
        "MiniMax-M3": {"input": 0.30, "output": 1.20},
        "MiniMax-M3.1-Flash": {"input": 0.15, "output": 0.60},
    }
    
    DEFAULT_MODEL = "MiniMax-M3"  # Served by both CP (sk-cp-) and regular keys
    
    def __init__(self, settings: Dict):
        super().__init__(settings)

        # Prefer Coding Plan key (sk-cp-...) when available; fall back to regular.
        api_key = resolve_secret(
            settings,
            env_vars=(
                "RAVEN_MINIMAX_CP_KEY", "MINIMAX_CP_KEY",
                "RAVEN_MINIMAX_API_KEY", "MINIMAX_API_KEY",
            ),
            site_config_keys=(
                "minimax_cp_key", "MINIMAX_CP_KEY",
                "minimax_api_key", "MINIMAX_API_KEY",
            ),
            db_field="minimax_cp_key",
            settings_keys=("minimax_cp_key", "minimax_api_key"),
            label="MiniMax API key (CP or regular)",
            required=False,
        )
        if not api_key:
            # Try the regular key field if the CP field is empty in DB.
            api_key = resolve_secret(
                settings,
                env_vars=("RAVEN_MINIMAX_API_KEY", "MINIMAX_API_KEY"),
                site_config_keys=("minimax_api_key", "MINIMAX_API_KEY"),
                db_field="minimax_api_key",
                settings_keys=("minimax_api_key",),
                label="MiniMax API key",
            )

        # group_id is not encrypted, so it's safe to read from settings/conf directly.
        group_id = (
            settings.get("minimax_group_id")
            or settings.get("MINIMAX_GROUP_ID")
            or (frappe.conf.get("MINIMAX_GROUP_ID") if hasattr(frappe, "conf") else None)
            or "0"
        )

        self.api_key = api_key
        self.group_id = group_id
        # Model selection: the Desk value (AI Agent Settings.minimax_model)
        # wins, but only when it still names a live model. The stored value
        # outlives the model - MiniMax retires IDs without notice and the
        # retired one answers HTTP 404 "no longer available" - so a retired or
        # unknown value falls back to the current flagship instead of failing
        # every call. The key prefix no longer selects a model: both Coding
        # Plan (sk-cp-) and regular keys are served by the current generation.
        self.default_model = self._resolve_model(settings.get("minimax_model"))
        self.model = self.default_model
    
    def _resolve_model(self, configured: Optional[str]) -> str:
        """Return a live model ID, falling back to the flagship.
        
        `configured` is the raw value of AI Agent Settings.minimax_model. It is
        honoured only when it names a model MiniMax still serves; a retired ID,
        a typo or a leftover from another provider falls back to
        DEFAULT_MODEL with a warning in the log.
        """
        if configured and configured in self.MODELS:
            return configured
        if configured:
            frappe.logger().warning(
                f"[MiniMax] model {configured!r} is retired or unknown; "
                f"using {self.DEFAULT_MODEL}"
            )
        return self.DEFAULT_MODEL
    
    def chat(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> str:
        """Send chat request to MiniMax API using OpenAI-compatible endpoint"""
        model = model or self.default_model
        
        # Use OpenAI-compatible endpoint (simpler format)
        url = f"{self.BASE_URL}/chat/completions"
        
        # Standard OpenAI format - filter out empty messages
        # MiniMax doesn't support multiple system messages, so merge them
        formatted_messages = []
        system_content = []
        
        for m in messages:
            content = m.get("content", "")
            if not content or not content.strip():
                continue
            
            if m["role"] == "system":
                system_content.append(content)
            else:
                formatted_messages.append({
                    "role": m["role"],
                    "content": content
                })
        
        # Add merged system message at the beginning
        if system_content:
            formatted_messages.insert(0, {
                "role": "system",
                "content": "\n\n".join(system_content)
            })
        
        # Ensure at least one user message exists
        if not any(m["role"] == "user" for m in formatted_messages):
            formatted_messages.append({"role": "user", "content": "Hello"})
        
        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Debug logging
        frappe.logger().debug(f"[MiniMax] Request URL: {url}")
        frappe.logger().debug(f"[MiniMax] Payload: {payload}")
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            
            # Log response for debugging. On 404 MiniMax names the model in
            # the body ("... is no longer available"), so surface that body
            # instead of a bare HTTPStatusError - it is the whole diagnosis.
            if response.status_code != 200:
                frappe.logger().error(f"[MiniMax] Error {response.status_code}: {response.text}")
                if response.status_code == 404:
                    raise Exception(
                        f"MiniMax model {model!r} is not available (HTTP 404): {response.text[:300]}"
                    )
                response.raise_for_status()
            data = response.json()
            
            # Check for API-level errors
            if "error" in data:
                raise Exception(f"MiniMax API error: {data['error']}")
            
            content = data["choices"][0]["message"]["content"]
            import re as _re
            return _re.sub(r"<think>.*?</think>", "", content, flags=_re.S).strip()
    
    def chat_stream(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> Generator[str, None, None]:
        """Stream response from MiniMax using OpenAI-compatible endpoint"""
        model = model or self.default_model
        
        with httpx.Client(timeout=60.0) as client:
            url = f"{self.BASE_URL}/chat/completions"
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
                    "max_completion_tokens": max_tokens,
                    "stream": True
                }
            ) as response:
                # A retired model answers 404 with no SSE body, so without this
                # check the stream yields nothing and the caller sees an empty
                # answer instead of an error.
                if response.status_code != 200:
                    body = response.read().decode("utf-8", "replace")
                    frappe.logger().error(f"[MiniMax] Stream error {response.status_code}: {body}")
                    raise Exception(
                        f"MiniMax model {model!r} is not available "
                        f"(HTTP {response.status_code}): {body[:300]}"
                    )
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        import json
                        chunk = line[6:]
                        if chunk.strip() == "[DONE]":
                            break
                        data = json.loads(chunk)
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
