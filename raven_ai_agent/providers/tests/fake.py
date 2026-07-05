"""Canonical FakeProvider for tests — R3 of the raven-smarter remake.

Use this instead of ad-hoc MagicMocks so every test exercises the real
LLMProvider contract (signatures, return types, streaming).

    from raven_ai_agent.providers.tests.fake import FakeProvider

    provider = FakeProvider(responses=["first answer", "second answer"])
    provider.chat(messages=[...])          -> "first answer"
    provider.chat(messages=[...])          -> "second answer"  (then repeats last)
    provider.calls                         -> recorded kwargs of every chat call
    FakeProvider(fail_with=RuntimeError("429")).chat(...)  -> raises
"""
from typing import Dict, Generator, List, Optional

from raven_ai_agent.providers.base import LLMProvider


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, settings: Dict = None, responses: List[str] = None,
                 fail_with: BaseException = None):
        super().__init__(settings or {})
        self.responses = list(responses or ["fake response"])
        self.fail_with = fail_with
        self.calls: List[Dict] = []
        self._i = 0

    def _next(self) -> str:
        resp = self.responses[min(self._i, len(self.responses) - 1)]
        self._i += 1
        return resp

    def chat(self, messages: List[Dict], model: Optional[str] = None,
             temperature: float = 0.3, max_tokens: int = 2000,
             stream: bool = False) -> str:
        self.calls.append({
            "messages": messages, "model": model,
            "temperature": temperature, "max_tokens": max_tokens,
        })
        if self.fail_with is not None:
            raise self.fail_with
        return self._next()

    def chat_stream(self, messages: List[Dict], model: Optional[str] = None,
                    temperature: float = 0.3,
                    max_tokens: int = 2000) -> Generator[str, None, None]:
        text = self.chat(messages, model, temperature, max_tokens)
        for token in text.split(" "):
            yield token + " "

    def embed(self, text: str) -> List[float]:
        return [0.0] * 8

    @property
    def call_count(self) -> int:
        return len(self.calls)
