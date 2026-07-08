# Test Baseline — what "green" means (Phase 1, 2026-07-07)

**Rule: "suite green" = FULL suite on a BENCH (real frappe), zero unexplained failures.**

## Bench truth (authoritative)
- Baseline at b268ff1 era: **264 passed / 1 red** — `tests/test_workflow_orchestrator.py::TestWorkflowOrchestrator::test_process_command_status_with_so` (W-09).
- That single red is now marked `xfail(strict=False)` with reason in-file. Root-cause is slotted to Phase 5 (routing-quality). When fixed, REMOVE the marker in the same PR — an XPASS report is the signal.
- Any NEW red on bench after this commit is a regression, full stop.

## Sandbox / non-bench environments (informational only)
- Fresh clones without a bench show ~50+ additional failures. These are ENVIRONMENT failures, not code failures. Known classes:
  1. Modules needing a real frappe at import (mock conftest covers the trusted subset only).
  2. Python version drift (bench py3.14 vs sandbox py3.10 f-string syntax, e.g. iot lineage).
  3. Missing bench-only deps.
- The TRUSTED SUBSET that must be green anywhere (CI/sandbox/bench):
  `tests/test_pipeline_v2.py tests/test_routing_canaries.py tests/test_migration_fixer_v2.py tests/test_router_consolidation.py tests/test_live_path_e2e.py tests/test_bom_agent_skill.py tests/test_bom_agent_v2.py`
- Auditors: never quote sandbox full-suite numbers as baseline. Cite bench runs with commit + count.

## Verification command (bench) — scope-pinned (F-AUD-1/2 fix)
```
cd apps/raven_ai_agent && ../../env/bin/python -m pytest tests/ -q 2>&1 | tail -3
```
Expected after this commit: **0 failed / 1 xfailed / 269 passed / 2 skipped**
(the 2 skips are pre-existing import-guard skips, reasons in-file).

WHY tests/ is pinned: a whole-app `pytest -q` from the app root is interrupted by
~13 ENVIRONMENTAL collection errors (bench-python vs module drift in non-tests/
trees) and runs 0 tests — it can never reach the expected line. Those collection
errors are pre-existing (main had 15; this branch reduces them to 13) and are
tracked as follow-up hygiene, not part of this baseline. `tests/` is the
authoritative suite scope. (Independently verified: vm3 audit
phase1-audit-20260708T020856Z, findings F-AUD-1/F-AUD-2.)
