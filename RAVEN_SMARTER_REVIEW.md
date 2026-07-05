# raven_ai_agent — Review & Remake Plan ("one command arrives, we solve it")

Date: 2026-07-04 · Commit reviewed: `b268ff1c` · Companion: `openwiki/` wiki (same commit)

## 1. Diagnosis — why a single chat command isn't handled efficiently

| # | Finding | Evidence | Impact |
|---|---|---|---|
| F1 | **The smart stack is unwired.** `RaymondLucyAgentV2` (multi-provider, fallback chain, cost monitor, skills router, patterns IntelligenceLayer) exists and passes 43/43 — but `hooks.py` routes every message to legacy `handle_raven_message()` in `api/agent.py`. Nothing imports `agent_v2`. | `hooks.py:14-18`; grep: zero imports of `agent_v2` outside itself | The product ships the dumb agent |
| F2 | **Fully synchronous pipeline.** HTML strip → 2 inline pre-processors → keyword cascade → briefing query → ERP context queries → vector search → OpenAI call → insert reply, all inside `Raven Message.after_insert` on the request thread. 10-50 s; no `frappe.enqueue`. | `api/agent.py:408-740` | Slow, fragile, blocks message insert |
| F3 | **Five routing layers, four passes over the query.** Inline cascade (live) + skills router (partial) + `router.py` (dead, 583 lines) + `command_router.py` (dead) + `multi_agent_router.py`/`intent_resolver.py` (built for V2, unwired). Keyword lists duplicated EN/ES by hand, differ per router. | `openwiki/architecture/routing.md` | Intent misses; unmaintainable |
| F4 | **Silent failure.** Both pre-processors wrap skills in `except Exception: pass`; a skill bug degrades to a generic LLM answer with no trace. `AI Routing Audit Log` exists but the live path never writes it. | `api/agent.py:~447-486` | "It answered something dumb" instead of an error you can fix |
| F5 | **Context is unscoped.** Morning briefing + ERP context + memory search run for EVERY generic query (1-5 s) regardless of intent; provider hardcoded to OpenAI on the live path. | `api/agent.py:600-740` | Latency + cost + diluted prompts |
| F6 | **Zero tests on the live path.** The 43/43 suite exercises the V2 constellation; `handle_raven_message` itself has no e2e test. | `tests/`, `openwiki/testing/testing.md` | Refactors are scary, so they don't happen |
| F7 | **Cruft misleads agents & humans.** `.git_backup_*` (~184K), `api/*.bak_bug*`, `agent_V1.py`, root `test_phase*.py`, `docs/legacy/*.py`. | repo root, `api/` | Every new session re-discovers what's dead |

## 2. Target architecture (one command, one path)

```
Raven Message.after_insert
  └─ handle_raven_message()            # thin: guards + HTML strip only (<10 ms)
       ├─ insert "🤔 working…" ack      # instant feedback
       └─ frappe.enqueue(process_command, queue="short")
            └─ Dispatcher (ONE router)
                 1. IntelligenceLayer.classify_complexity   # bilingual, cheap
                 2. SkillRouter (AI Skill Registry–driven triggers)
                 3. Coordinator → domain agent (AgentSpec)
                 4. Fallback: RaymondLucyAgentV2.process_query (provider chain, scoped context)
            └─ every hop → AI Routing Audit Log
            └─ reply inserted via channel_utils (edits/replaces the ack)
```

Design rules: one match pass, first-class confidence + fallthrough; context fetched per-intent, not globally; provider from `AI Agent Settings`, never hardcoded; no bare `except`; failures reply with a short apology + bug fingerprint (`bug_reporter` already exists — use it).

## 3. Remake plan — phased, each phase shippable

### Phase R1 — Wire V2 behind a flag (≈4h) ← highest value/effort ratio
1. Add `agent_pipeline_v2_enabled` (Check, default 0) to `AI Agent Settings`.
2. In `handle_raven_message`, at top of routing: if flag on → enqueue `process_message_v2` path; else legacy. Keep pre-processor COA/DQS behavior by registering them as ordinary skills triggers in the V2 path.
3. Ack message + enqueue (F2 fix) — applies to the V2 branch only.
DoD: 43/43 green flag on/off; live sandbox transcript: `@ai diagnose`, `@ai scan`, `@ai validate coa-26-0431`, 2 EN + 2 ES generic queries; audit-log rows present. Evidence: transcript + `SELECT count(*) FROM \`tabAI Routing Audit Log\``.

### Phase R2 — Router consolidation (≈6h)
1. Move all keyword/intent data out of code into `AI Skill Registry` + AgentSpec examples (bilingual pairs stored once).
2. Delete dead routers: `api/router.py`, `command_router.py`, `*.bak_*`, `agent_V1.py`.
3. `intent_resolver` becomes the single classification entry; cascade in `agent.py` shrinks to guards only.
DoD: grep shows one router import path; suite green; misroute canary set (10 paraphrased utterances per domain, EN+ES) ≥ 90% hit.

### Phase R3 — Live-path tests + FakeProvider (≈4h)
1. Canonical `FakeProvider` in `providers/tests/`.
2. E2E test: insert Raven Message fixture → assert ack + final reply + audit row, flag on and off.
3. Kill silent excepts; assert bug_reporter fingerprint on induced skill failure.
DoD: new tests in CI; coverage on `api/agent.py` dispatch section ≥ 80%.

### Phase R4 — Context scoping + cost (≈4h)
1. Per-intent context builders (briefing only for briefing intents, etc.).
2. `CostMonitor` on every call; per-query cost ledger in audit log.
DoD: median simple-command latency < 4 s in sandbox; cost per simple command < $0.01.

### Phase R5 — Cruft purge + docs automation (≈2h)
1. Delete `.git_backup_*`, `docs/legacy/*.py`, root `test_phase*.py`, `perf_test.py`.
2. Commit `openwiki/` + `AGENTS.md`/`CLAUDE.md` (done in this session's bundle).
3. Add `.github/workflows/openwiki-update.yml` (needs `OPENROUTER_API_KEY` or `ANTHROPIC_API_KEY` secret) so the wiki self-maintains daily.
DoD: fresh clone + `openwiki --update` runs clean; repo root shows only live code.

Total ≈ 20h (~3 working days). R1 alone makes commands land on the smart stack.

## 4. Fit with the Co-Scientist Debate Layer project

- S5-01/S5-02 (classify_complexity "debate" + Coordinator AgentSpec) assume exactly the consolidated router of R2 — doing R1/R2 first makes S5 trivial and testable.
- The plan's regression gate (43/43 flag on/off) is the same harness R1/R3 build; no duplicated effort.
- Recommendation: run R1-R3 before starting S1 of the debate layer, or in parallel with S1 (kernel work is Frappe-free and doesn't collide).

## 5. Keep / Refactor / Delete summary

- **Keep**: patterns/ (all 8), agents/ (10), skills framework + packages, providers/, utils/ memory-context-bus-cost, ai_orchestrator doctypes, bug_reporter.
- **Refactor**: `api/agent.py` (thin hook), task_validator.py (split), manufacturing_agent (extract builders), model IDs out of provider classes into Settings.
- **Delete**: `.git_backup_*`, `api/router.py` + `command_router.py` + `.bak_*` + `agent_V1.py` + `perf_test.py`, root `test_phase*.py` and sibling stale tests, `docs/legacy/*.py`. (`rpi_client/` → move to its own repo.)
