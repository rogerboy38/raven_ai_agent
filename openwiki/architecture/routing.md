# Architecture: routing layers

Five routing implementations exist. Only two run in production.

| Router | File | Status | Notes |
|---|---|---|---|
| Inline keyword cascade | `api/agent.py` (inside `handle_raven_message`) | **LIVE** | Pre-processors + if/elif keyword lists; first match wins |
| Skills router | `skills/router.py` | **LIVE (partially)** | Directory-scan discovery of `skills/*/skill.py`; invoked only from the two inline pre-processors and from V2 |
| `api/router.py` | 583 lines | **DEAD** | Never imported by live path; also `router.py.bak_bug28` |
| `api/command_router.py` | — | dead/legacy | superseded |
| `api/multi_agent_router.py` + `api/intent_resolver.py` | — | **DEAD on live path** | Designed for V2/coordinator routing; covered by `tests/test_multi_agent.py`, `tests/test_intent_resolver.py` |

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
