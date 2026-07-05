# Architecture: agent stacks, providers, patterns, skills

## V1 — `api/agent.py` (live)

Monolithic handler: routing + context building + hardcoded OpenAI call + response insert in one file. Also contains morning-briefing and ERP-context helpers. Treat as legacy; do not extend.

## V2 — `api/agent_v2.py` (built, unwired)

`RaymondLucyAgentV2(user, provider_override=None)`:
- Provider from `AI Agent Settings` (`default_provider`, `fallback_provider`), via `providers.get_provider()`
- `CostMonitor` (utils/cost_monitor.py) per-call cost tracking
- Skills via `skills.get_router()`
- Optional patterns `IntelligenceLayer` (import-guarded, `PATTERNS_AVAILABLE`)
- `process_query(query, conversation_history)` at line 170; whitelisted `process_message_v2` at line 411

## Providers (`providers/`)

`base.py` abstraction; implementations: `openai_provider.py`, `deepseek.py`, `claude.py`, `minimax.py` (+ Ollama stub). Model IDs currently hardcoded per provider class; selection via `AI Agent Settings`. Secrets via `_secrets.py`.

## Patterns (`patterns/`, ~2.4K LOC, all importable and used by V2)

| Module | Role |
|---|---|
| `intelligence.py` | Facade; `classify_complexity` (simple/complex/debate-style labels), orchestrates the rest |
| `planner.py` | Multi-step plan generation |
| `coordinator.py` | Dispatch to domain agents (AgentSpec registry) |
| `reflection.py` | Self-critique pass |
| `guardrails.py` | Input/output safety checks |
| `rag_retriever.py` | Retrieval over vector store |
| `crm/` | CRM-specific planner + guardrails with autonomy ladder 0-4 (`AI Action Policy` doctype) |

## Domain agents (`agents/`, ~9.4K LOC, 10 agents)

task_validator (pipeline diagnosis — largest, refactor candidate), sales_order_followup, manufacturing, payment, workflow_orchestrator, executive, rnd, bom_creator, batch_orchestrator, iot. Self-contained; no duplication; invoked from routing branches and whitelisted APIs.

## Skills (`skills/`)

Framework: `framework.py` (base class), `router.py` (directory scan + trigger matching). Packages: coa_validator, data_quality_scanner, crm_agent, formulation_advisor, formulation_orchestrator, formulation_reader, batch_selector, iot_* (humidity/motion/temperature/sensor_manager), migration_fixer, skill_creator, skill_sync. Registry doctype: `AI Skill Registry` (ai_orchestrator module). External apps (e.g. rnd_nutrition2 `raven_tools.py`) bridge by registering additional tools/skills.
