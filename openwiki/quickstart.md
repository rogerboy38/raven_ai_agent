---
type: "Reference"
title: "raven_ai_agent — OpenWiki Quickstart"
description: "Entry point for the raven_ai_agent repository wiki, covering the live Raven/Frappe AI agent stack, major architecture and workflow pages, and maintenance guidance for future updates."
tags: [openwiki, quickstart, raven-ai-agent]
---

# raven_ai_agent — OpenWiki Quickstart

> Generated 2026-07-04 at commit `b268ff1c`. Maintained via `openwiki --update`.

The repository also includes a scheduled/manual GitHub Actions workflow at `.github/workflows/openwiki-update.yml` that runs `openwiki --update --print` and opens an `openwiki/update` pull request for generated wiki changes.

## What this repository is

`raven_ai_agent` is a Frappe app that embeds an AI agent ("Raymond/Lucy") into Raven chat on an ERPNext site. Users type `@ai <command>` (bilingual EN/ES) in any channel; the agent answers with ERP data, runs diagnostics, validates documents, and orchestrates domain workflows (sales, manufacturing, payments, R&D formulation, IoT).

Production host: `erp.sysmayal2.cloud`.

## The one thing you must know first

There are **two agent stacks** in this repo, and only the older one is live:

| Stack | Entry | Status |
|---|---|---|
| **V1 monolith** | `raven_ai_agent/api/agent.py` → `handle_raven_message()` | **LIVE** — wired in `hooks.py:14-18` (`Raven Message.after_insert`) |
| **V2 modern** | `raven_ai_agent/api/agent_v2.py` → `RaymondLucyAgentV2.process_query()` | Built, tested (43/43 regression suite), **never imported by the live path** |

Every incoming chat message goes through the V1 synchronous keyword cascade on the HTTP request thread. The V2 stack (multi-provider, skills router, patterns intelligence layer) is a drop-in replacement that was never dropped in. Most "why is this slow/dumb" questions trace back to this fact. See [workflows/message-pipeline.md](workflows/message-pipeline.md).

## Repository map (live code only)

```
raven_ai_agent/
├── hooks.py                     # doc_events: Raven Message.after_insert → api.agent.handle_raven_message
├── api/
│   ├── agent.py                 # LIVE V1 pipeline: keyword routing + inline pre-processors + OpenAI call
│   ├── agent_v2.py              # RaymondLucyAgentV2 — multi-provider + skills + patterns (NOT wired)
│   ├── agent_supervisor.py      # supervisor helpers
│   ├── router.py / command_router.py / multi_agent_router.py / intent_resolver.py
│   │                            # four additional routing layers, partially dead — see architecture/routing.md
│   └── ...40+ modules           # webhooks, uploads, utils; see architecture/api-surface.md
├── agents/                      # 10 domain agents (task_validator, manufacturing, payment, executive, rnd, ...)
├── skills/                      # 9+ skill packages + framework.py + router.py (directory-scan discovery)
├── patterns/                    # Agentic patterns: intelligence, planner, coordinator, reflection,
│                                # guardrails, rag_retriever (+ crm/ subpackage with autonomy ladder)
├── providers/                   # OpenAI, DeepSeek, Claude, MiniMax (+ Ollama stub); base.py abstraction
├── utils/                       # memory.py, vector_store.py, context_manager.py, agent_bus.py, cost_monitor.py
├── raven_ai_agent/doctype/      # AI Agent Settings, AI Memory, Raven Agent Bug, IoT readings, ...
├── ai_orchestrator/doctype/     # AI Bot Persona, AI Routing Audit Log, AI Skill Registry
└── crm_patterns/doctype/        # AI Action Policy
```

Cruft to ignore (candidates for deletion): `.git_backup_*/`, `docs/legacy/*.py`, root `test_phase*.py` (frozen snapshots), `api/*.bak_bug*`, `rpi_client/` (Raspberry Pi scale client — separate deployable), `api/agent_V1.py`.

## Sections

- [Architecture: routing layers](architecture/routing.md) — the five routers and which ones actually run
- [Architecture: agent stacks](architecture/agent-stacks.md) — V1 vs V2, providers, patterns, skills
- [Architecture: API surface](architecture/api-surface.md) — the 40+ `api/` modules classified live/dead
- [Workflow: message pipeline](workflows/message-pipeline.md) — full runtime trace of `@ai <command>`, with timings
- [Workflow: memory & context](workflows/memory-and-context.md) — AI Memory, vector store, context manager, agent bus
- [Testing](testing/testing.md) — the 43/43 golden suite, live vs stale tests, how to run

## Change-oriented guidance for agents

- **Adding a new command/intent**: today requires editing the keyword cascade in `api/agent.py` (fragile). Prefer adding a skill package under `skills/` with trigger patterns, and route via `skills/router.py`. Check `AI Skill Registry` doctype.
- **Changing providers/models**: `providers/` + `AI Agent Settings` doctype. Note the live V1 path hardcodes OpenAI and does not consult the provider abstraction.
- **Anything touching the hook path** (`api/agent.py`): it runs synchronously inside `Raven Message.after_insert`. Exceptions here can break message inserts; long calls block the request. Keep changes fast and wrapped.
- **Never** auto-submit ERP documents from agent code; insert as draft (`docstatus=0`).
- Run the regression suite before merging anything that touches routing (see [testing](testing/testing.md)). The bar is 43/43.
