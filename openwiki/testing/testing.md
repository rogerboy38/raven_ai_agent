# Testing

## The golden bar: 43/43 regression suite

The transcript-based V2 regression suite (referenced across project docs as "43/43") lives in `tests/` — driven by `tests/test_utterances.json` + `tests/conftest.py` and the `test_*` modules (multi_agent, intent_resolver, payment_agent, manufacturing_agent, sales_order_followup_agent, workflow_orchestrator, safety_guardrails, truth_hierarchy, e2e_integration). `tests/TEST_PLAN.md` describes scope.

Run (inside a bench):
```sh
bench --site <site> run-tests --app raven_ai_agent
# or targeted:
python -m pytest tests/ -x -q
```

Rule for any routing/agent change: suite must stay 43/43 with the intelligence layer flag both off and on.

## Live vs stale tests

- **Live**: `tests/` (181 test functions across 23 files repo-wide), `patterns/tests/`, `patterns/crm/tests/`, `providers/tests/`, `raven_ai_agent/api/tests/`.
- **Stale — do not run, do not update**: root `test_phase*.py`, `test_memory_enhancement.py`, `test_minimax_direct.py`, `test_standalone_memory.py` (frozen phase-validation snapshots), plus everything under `.git_backup_*`.

## Gaps

- No tests cover `handle_raven_message` end-to-end (the live path!) — the suite exercises the V2 constellation.
- No FakeProvider abstraction; tests mock providers ad hoc. Worth adding one canonical fake in `providers/tests/`.
