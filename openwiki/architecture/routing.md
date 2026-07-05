# Architecture: routing layers

Five routing implementations exist. Only two run in production.

| Router | File | Status | Notes |
|---|---|---|---|
| Inline keyword cascade | `api/agent.py` (inside `handle_raven_message`) | **LIVE** | Pre-processors + if/elif keyword lists; first match wins |
| Skills router | `skills/router.py` | **LIVE (partially)** | Directory-scan discovery of `skills/*/skill.py`; invoked only from the two inline pre-processors and from V2 |
| `api/router.py` | 583 lines | **DEAD** | Never imported by live path; also `router.py.bak_bug28` |
| `api/command_router.py` | — | dead/legacy | superseded |
| `api/multi_agent_router.py` + `api/intent_resolver.py` | — | **DEAD on live path** | Designed for V2/coordinator routing; covered by `tests/test_multi_agent.py`, `tests/test_intent_resolver.py` |

## R2 state (branch pipeline-v2-r2) — CONVERGED

`api/dispatcher.py` is the single V2 routing path; stage recorded in every audit row:

1. `skill_exact` — framework SkillRegistry match with confidence >= 0.90 (explicit ids: COA-xx-xxxx, SO-xxxxx patterns, sensor L01…)
2. `multi_agent` — deterministic regex pipelines (workflow run / full status / diagnose and fix)
3. `semantic_pipeline` — Coordinator pattern maps free phrasing to a pipeline key (needs provider)
4. `agent_v2` — RaymondLucyAgentV2.process_query (help, broad-trigger skills, workflows, LLM)

Single skill source of truth: framework `SkillRegistry` (discovery requires `SKILL_CLASS` export
in each skill package `__init__.py`) + `AI Skill Registry` doctype rows (auto-synced; `is_active=0`
disables a skill everywhere). The legacy `skills/router.py` now loads from the same registry.
Dead modules deleted: `api/router.py`, `agent_V1.py`, `perf_test.py`, `*.bak_*`.
`command_router.py` KEPT — it is the live CommandRouterMixin (workflow dispatch), not a router.
Routing regression bar: `tests/test_routing_canaries.py` (bilingual, stage-asserting).

## How routing should converge (target)

One entry (`handle_raven_message`) → enqueue → single resolver:
1. `IntelligenceLayer.classify_complexity` (patterns/intelligence.py) — cheap classification, bilingual
2. Skills router with registered trigger patterns (`AI Skill Registry` doctype as source of truth)
3. Domain agent dispatch via `multi_agent_router` AgentSpecs
4. Fallback: provider LLM with scoped context
Every hop writes `AI Routing Audit Log`.

## Gotchas

- Keyword lists are duplicated EN/ES by hand in `agent.py`; the same intent may appear in three routers with different keyword sets.
- Order matters in the live cascade: DataQualityScanner's `validate` keyword would shadow COA validation — that's why the COA regex runs first (comment `T141` in `agent.py`).
- `.bak_bug*` files in `api/` are snapshots, not imports; ignore them.
