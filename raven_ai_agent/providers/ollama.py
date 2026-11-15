"""
Ollama LLM Provider (local, via OpenAI-compatible /v1 endpoint)
"""
import frappe
from typing import Dict, List, Optional, Generator
from openai import OpenAI
from .base import LLMProvider
from .model_hosts import checked_base_url, model_http_client


class OllamaProvider(LLMProvider):
    """Local Ollama provider through its OpenAI-compatible /v1 API"""
    name = "ollama"
    DEFAULT_BASE_URL = "https://ollama.sysmayal.cloud/v1"
    DEFAULT_MODEL = "qwen2.5:7b"

    def __init__(self, settings: Dict):
        super().__init__(settings)
        # decision 101 (TASKS-350): a model server only on the named list; the built-in default is the programme's own
        # host, which is not on it until it is ruled, so this refuses until then
        base_url = checked_base_url(
            settings.get("ollama_base_url") or frappe.conf.get("ollama_base_url"),
            self.DEFAULT_BASE_URL,
            "the Ollama base URL setting" if (settings.get("ollama_base_url") or frappe.conf.get("ollama_base_url")) else "the Ollama provider's built-in default",
        )
        # Ollama ignores the key, but the OpenAI SDK requires a non-empty string
        api_key = settings.get("ollama_api_key") or "ollama"
        self.client = OpenAI(base_url=base_url, api_key=api_key, http_client=model_http_client())
        self.default_model = (
            settings.get("ollama_model")
            or frappe.conf.get("ollama_model")
            or self.DEFAULT_MODEL
        )

    def chat(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> str:
        model = model or self.default_model
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False
        )
        return response.choices[0].message.content

    def chat_stream(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> Generator[str, None, None]:
        model = model or self.default_model
        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def get_default_model(self) -> str:
        return self.default_model
