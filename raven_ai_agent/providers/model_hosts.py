"""TASKS-350 decision 101: the agent sends a prompt only to a model server on a NAMED list in the code.

A host that comes from a setting, the site config or an environment variable and is not on the list is refused, in a chat
turn and outside one (a background job, a direct web call), because the check sits where the address is taken and on
every request the model clients make, not only in the guard of a chat turn.

The list is a literal. It is changed by a ruling and a commit, never by a setting. The programme's own model server is NOT
on it until Hugh approves it (decision 101): the Ollama provider's built-in default points there, so that provider refuses
until the list is ruled.
"""

from urllib.parse import urlparse

import httpx

# The six public provider hosts the code already names (the provider classes' BASE_URL constants, the OpenAI/Anthropic SDK
# defaults), and nothing else (decision 104, TASKS-351): the loopback names `localhost`, `127.0.0.1`, `::1` are NOT on
# it, so a model server on this machine (the default address of the IoT bot's Ollama) is refused too. The programme's
# own model server is added later, by name, by a new ruling.
MODEL_SERVER_HOSTS = frozenset({
    "api.openai.com", "api.deepseek.com", "api.anthropic.com", "api.minimax.io", "api.minimaxi.chat", "api.minimax.chat",
})


class ModelHostRefused(Exception):
    """Raised when a model client would send a request to a host that is not on `MODEL_SERVER_HOSTS`."""


def host_of(url) -> str:
    try:
        return (urlparse(str(url)).hostname or "").lower()
    except Exception:
        return ""


def check_model_url(url, source: str = ""):
    """Refuse `url` unless its host is on the list. `source` names where the address came from (a message for the person)."""
    h = host_of(url)
    if h not in MODEL_SERVER_HOSTS:
        where = f" (from {source})" if source else ""
        raise ModelHostRefused(
            f"The agent sends prompts only to the model servers on its approved list; "
            f"{h or 'this address'}{where} is not on it."
        )
    return url


def checked_base_url(candidate, default, source: str):
    """The base URL a client will use: `candidate` when set, else `default`; refused when its host is not listed."""
    url = candidate or default
    check_model_url(url, source)
    return url


def _hop_hook(request):
    check_model_url(request.url, "a request of a model client")


def model_http_client(**kw) -> "httpx.Client":
    """An httpx client for the model SDKs: every request it makes, each redirect hop included, is checked against the list
    (httpx runs the `request` hooks once per hop). Redirects are followed, as the SDKs' own default client does."""
    hooks = kw.pop("event_hooks", None) or {}
    hooks = {**hooks, "request": [*hooks.get("request", []), _hop_hook]}
    kw.setdefault("follow_redirects", True)
    return httpx.Client(event_hooks=hooks, **kw)
