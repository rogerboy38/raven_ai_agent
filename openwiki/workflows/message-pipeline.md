---
type: "Reference"
title: "Workflow: `@ai` message pipeline (live V1 path)"
openwiki_generated: true
---

# Workflow: `@ai` message pipeline (live V1 path)

What actually happens when a user types `@ai diagnose SO-00752` in a Raven channel.

## Call chain

1. **Ingress** — Raven inserts a `Raven Message`; Frappe fires `after_insert` → `raven_ai_agent.api.agent.handle_raven_message` (`hooks.py:14-18`). **Synchronous, on the HTTP request thread. No `frappe.enqueue`.**
2. **Sanitize** — bot-message guard, empty-text guard, BeautifulSoup HTML strip (`api/agent.py:408-435`).
3. **Pre-processor: COA validator** — regex for `COA-xx-xxxx` / "validate coa" → `skills.router.SkillRouter().route(query)`; on success inserts reply and returns (`api/agent.py:~447-470`). Failure is swallowed by `except: pass`.
4. **Pre-processor: Data Quality Scanner** — keyword list (`scan`, `validate`, `repair`, ...) → `DataQualityScannerSkill().handle()`; same insert-and-return pattern, same silent `except` (`api/agent.py:~471-486`).
5. **Main keyword cascade** — long if/elif over keyword lists (analytics, agent domains, etc.), `api/agent.py:~490-600`. Each branch re-lowercases and re-scans the query. First match wins; no confidence, no audit, no fallthrough ranking.
6. **Context build** — morning briefing query, ERPNext context queries, memory vector search (~1-5 s of DB/embedding work), then **hardcoded OpenAI** chat completion (5-30 s), `api/agent.py:600-740`.
7. **Respond** — insert bot `Raven Message` + `frappe.publish_realtime` (`api/channel_utils.py:47`).

## Measured shape of the problem

Everything (steps 2-7) blocks the original message-insert request: typically 10-50 s wall time, four+ passes over the query text, no early exit caching, no typing indicator, no partial responses.

## Failure characteristics

- Silent `except Exception: pass` around both pre-processors — skill bugs vanish; the query falls through to a generic (often wrong) LLM answer.
- An exception late in the cascade can surface as a failed message insert for the *user's own message*.
- No routing audit trail on this path (`AI Routing Audit Log` doctype exists but the live path doesn't write it).
- Intent misses: any phrasing not in the keyword lists gets the generic LLM path with ERP context — slow and unfocused. Bilingual coverage is manual keyword duplication (EN + ES per list).

## Pipeline V2 (Phase R1 — branch `pipeline-v2-r1`)

`api/pipeline_v2.py` + a feature-flagged diversion at the top of `handle_raven_message`:
`AI Agent Settings.agent_pipeline_v2_enabled=1` → instant ack message → `frappe.enqueue` →
`RaymondLucyAgentV2.process_query` (skills-first, patterns, provider fallback) → reply + ack cleanup →
`AI Routing Audit Log` row (request_id, intent, skill, latency_ms, error_text). Failures reply with an
apology + request_id and are captured by `bug_reporter`. Flag off = legacy path byte-identical.
Tests: `tests/test_pipeline_v2.py`.

## The unused fix that already exists

`api/agent_v2.py` (`RaymondLucyAgentV2.process_query`, line 170) already implements: provider abstraction with fallback chain (`providers/`), cost monitoring, skills router integration, and the opt-in patterns `IntelligenceLayer` (classification → planner → coordinator → reflection → guardrails). `process_message_v2()` (line 411) is a whitelisted entry. Nothing in `hooks.py` or `agent.py` calls it.

## When changing this area

- Test file bar: the 43/43 regression suite (see [testing](../testing/testing.md)) with the intelligence layer both enabled and disabled.
- Do not add more keyword branches to `agent.py` — add skills or extend `IntelligenceLayer.classify_complexity`.
- Any latency-adding step must be moved behind `frappe.enqueue` with an immediate "working on it" reply.
