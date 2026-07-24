---
type: "Reference"
title: "Workflow: memory & context"
openwiki_generated: true
---

# Workflow: memory & context

Four live systems in `utils/`:

- **`memory.py`** — `AI Memory` doctype; scheduled daily summaries + cleanup (see `hooks.py` scheduler_events). Long-term conversational memory.
- **`vector_store.py`** — OpenAI-embedding semantic search over memories/docs; used by the live pipeline's memory search step and by `patterns/rag_retriever.py`.
- **`context_manager.py`** — session-aware state per user/channel (conversation history windows).
- **`agent_bus.py`** — in-process pub/sub between agents (used by orchestrators).

Context build on the live path (`api/agent.py:600+`): morning briefing + ERPNext context queries + memory vector search happen on EVERY generic query — 1-5 s before the LLM is even called. Scope them per-intent when refactoring.

`cost_monitor.py` tracks per-call provider cost (used by V2 only today).
