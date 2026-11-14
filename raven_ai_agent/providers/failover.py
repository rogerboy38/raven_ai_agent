"""A provider with a fallback (TASKS-344 ruling 79).

`get_provider(name, settings)` returns a FailoverProvider when AI Agent Settings names a `fallback_provider` that is
not the primary: a failed call (404 retired model, 429, timeout, any exception) is retried ONCE on the fallback, so
every caller (the semantic stage, V1, V2, skills) gets the same behaviour. When both fail the caller gets a
`ProviderFailure` (an Exception with `fallback_tried = True`), never a partial answer and never a second try.
Only the model call is retried: nothing here writes.
"""

from typing import Callable, Dict, Generator, List, Optional

from .base import LLMProvider

try:
    import frappe
except Exception:  # pragma: no cover
    frappe = None


class ProviderFailure(Exception):
    """Both the primary and the fallback provider failed."""

    fallback_tried = True

    def __init__(self, primary_error, fallback_error):
        super().__init__(f"primary: {type(primary_error).__name__}: {primary_error} | "
                         f"fallback: {type(fallback_error).__name__}: {fallback_error}")
        self.primary_error = primary_error
        self.fallback_error = fallback_error


def _log(msg):
    try:
        frappe.logger().warning(msg)
    except Exception:
        pass


class FailoverProvider(LLMProvider):
    def __init__(self, primary: LLMProvider, fallback_name: str, build_fallback: Callable[[], LLMProvider]):
        super().__init__(primary.settings)
        self.primary = primary
        self.fallback_name = fallback_name
        self._build_fallback = build_fallback
        self._fallback = None
        self.used_fallback = False

    @property
    def name(self):                                 # callers compare provider names
        return self.primary.name

    def __getattr__(self, item):                     # voice, embeddings... stay the primary's
        return getattr(self.primary, item)

    def get_default_model(self) -> str:
        return self.primary.get_default_model()

    def _fallback_provider(self, primary_error):
        if self._fallback is None:
            try:
                self._fallback = self._build_fallback()
            except Exception as exc:
                raise ProviderFailure(primary_error, exc) from exc
        return self._fallback

    def chat(self, messages: List[Dict], model: Optional[str] = None, temperature: float = 0.3,
             max_tokens: int = 2000, stream: bool = False) -> str:
        try:
            return self.primary.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, stream=stream)
        except Exception as primary_error:
            _log(f"[providers] {self.primary.name} failed ({type(primary_error).__name__}); trying {self.fallback_name}")
            fb = self._fallback_provider(primary_error)
            try:
                answer = fb.chat(messages, temperature=temperature, max_tokens=max_tokens)  # the primary's model name does not apply
            except Exception as fallback_error:
                raise ProviderFailure(primary_error, fallback_error) from fallback_error
            self.used_fallback = True
            return answer

    def chat_stream(self, messages: List[Dict], model: Optional[str] = None, temperature: float = 0.3,
                    max_tokens: int = 2000) -> Generator[str, None, None]:
        started = False
        try:
            for chunk in self.primary.chat_stream(messages, model=model, temperature=temperature, max_tokens=max_tokens):
                started = True
                yield chunk
            return
        except Exception as primary_error:
            if started:                              # half an answer was already delivered: do not splice
                raise
            _log(f"[providers] {self.primary.name} stream failed; trying {self.fallback_name}")
            fb = self._fallback_provider(primary_error)
            try:
                yield from fb.chat_stream(messages, temperature=temperature, max_tokens=max_tokens)
            except Exception as fallback_error:
                raise ProviderFailure(primary_error, fallback_error) from fallback_error
            self.used_fallback = True
