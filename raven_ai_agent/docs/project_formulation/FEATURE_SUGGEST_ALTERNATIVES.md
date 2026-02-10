# Feature: Suggest Alternatives for Non-Compliant Batches

**Status:** COMPLETE
**Priority:** High
**Target Module:** tds_compliance (Phase 3 Agent)
**Date:** February 4, 2026
**Last Updated:** February 4, 2026
**Test Commit:** `a9c6f2e`

---

## Implementation Status Update

### What Has Been Implemented

| Feature | Status | Location |
|---------|--------|----------|
| `validate_phase2_compliance` action | ✅ DONE | tds_compliance.py |
| `_transform_phase2_input()` method | ✅ DONE | tds_compliance.py |
| `_validate_coa_status()` method | ✅ DONE | tds_compliance.py |
| `_format_phase3_output()` method | ✅ DONE | tds_compliance.py |
| `suggest_alternatives` action | ✅ DONE | tds_compliance.py |
| TDS auto-fetch | ✅ DONE | `_get_tds_for_item()` |
| Item-level grouping | ✅ DONE | Output grouped by `item_code` |
| Blend recommendations | ✅ DONE | Part of suggest_alternatives |
| FEFO sorting | ✅ DONE | Part of suggest_alternatives |

### Remaining Work

| Feature | Status | Notes |
|---------|--------|-------|
| Unit tests for suggest_alternatives | ✅ DONE | 6 comprehensive tests |
| Integration tests | ✅ DONE | 4 tests covering Phase 2 → 3 → 4 flow |
| formulation_reader integration | ⏳ OPTIONAL | Enhancement for future release |

---

## Overview

This feature provides intelligent suggestions for alternative batches when a selected batch fails TDS compliance validation. The feature is now integrated with the TDS Compliance Agent (Phase 3) to analyze available inventory and recommend compliant alternatives.

---

## Problem Statement

When a batch fails TDS compliance checks, users need:
1. Identification of which batches could be used as alternatives
2. Understanding of which parameters are causing non-compliance
3. Recommendations for batches that could be blended to achieve compliance
4. Suggestions based on FEFO (First Expired, First Out) principles

---

## Implemented Solution

### Integration Point: TDS Compliance Agent

The `tds_compliance` agent has been extended with the `suggest_alternatives` action:

```python
action: "suggest_alternatives"
```

### Workflow

```
┌─────────────────────┐
│  TDS Compliance     │
│    Check FAILS      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  tds_compliance     │
│  .suggest_alternatives()
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Query Available    │
│     Batches         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Filter by COA      │
│    Parameters       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Return Ranked      │
│   Alternatives      │
└─────────────────────┘
```

---

## API Specification

### Request

```json
{
  "action": "suggest_alternatives",
  "payload": {
    "non_compliant_batch": "01-2025-001",
    "item_code": "ALOE-200X-PWD",
    "failed_parameters": [
      {
        "parameter": "Aloin",
        "actual_value": 2.5,
        "spec_min": 0.5,
        "spec_max": 2.0,
        "status": "FAIL_HIGH"
      }
    ],
    "required_quantity": 500,
    "tds_spec_id": "TDS-ALOE-001",
    "options": {
      "include_blends": true,
      "max_alternatives": 5,
      "fefo_priority": true,
      "same_warehouse_only": false
    }
  }
}
```

### Response

```json
{
  "success": true,
  "alternatives": [
    {
      "type": "single_batch",
      "batch_id": "01-2025-003",
      "item_code": "ALOE-200X-PWD",
      "available_qty": 750,
      "compliance_score": 100,
      "parameters": {
        "Aloin": {"value": 1.2, "status": "PASS"}
      },
      "expiry_date": "2027-03-15",
      "warehouse": "WH-001",
      "recommendation": "Direct replacement - all parameters compliant"
    },
    {
      "type": "blend",
      "batches": [
        {"batch_id": "01-2025-001", "proportion": 0.3, "qty": 150},
        {"batch_id": "01-2025-004", "proportion": 0.7, "qty": 350}
      ],
      "blended_parameters": {
        "Aloin": {"value": 1.65, "status": "PASS"}
      },
      "compliance_score": 95,
      "recommendation": "Blend achieves compliance - dilutes high Aloin"
    }
  ],
  "analysis": {
    "total_batches_evaluated": 12,
    "compliant_alternatives_found": 3,
    "blend_options_found": 2,
    "limiting_parameter": "Aloin",
    "suggestion": "Consider batch 01-2025-003 as primary alternative"
  }
}
```

---

## Test Requirements

### Unit Tests - ✅ IMPLEMENTED

| Test Method | Description | Status |
|-------------|-------------|--------|
| `test_fefo_sorting` | Test expiry date sorting | ✅ Done |
| `test_single_batch_alternative` | Test finding replacement batch | ✅ Done |
| `test_blend_recommendation` | Test blend calculation | ✅ Done |
| `test_no_alternatives_found` | Test graceful handling when no alternatives | ✅ Done |
| `test_quantity_constraint` | Test alternatives meet quantity requirements | ✅ Done |
| `test_compliance_score_ranking` | Test ranking by compliance score | ✅ Done |

### Integration Tests - ✅ IMPLEMENTED

| Test Method | Description | Status |
|-------------|-------------|--------|
| `test_phase2_to_phase3_flow` | Test Phase 2 output to Phase 3 | ✅ Done |
| `test_phase3_to_phase4_handoff` | Test Phase 3 to Phase 4 handoff | ✅ Done |
| `test_end_to_end_workflow_data_integrity` | Test data preservation across phases | ✅ Done |
| `test_mixed_compliance_results` | Test handling mixed results | ✅ Done |

**Test Location:** `raven_ai_agent/skills/formulation_orchestrator/tests.py`

---

## Acceptance Criteria

- [x] `suggest_alternatives` action added to tds_compliance
- [x] Returns at least 1 alternative when compliant batches exist
- [x] Blend calculations are mathematically accurate
- [x] FEFO sorting is applied by default
- [x] Response includes compliance scores
- [x] Handles case when no alternatives found gracefully
- [x] Unit tests cover all scenarios (6 tests)
- [x] Integration tests with Phase 2 and Phase 4 (4 tests)

---

## Next Steps

1. ~~**Add Unit Tests**~~ ✅ COMPLETE - 6 comprehensive tests implemented
2. ~~**Add Integration Tests**~~ ✅ COMPLETE - 4 integration tests implemented
3. **Optional: formulation_reader Extension** - Move suggest_alternatives to formulation_reader for better separation of concerns
4. **Documentation** - Update skill documentation with usage examples

---

**Document Version:** 3.0
**Last Updated:** February 4, 2026
**Owner:** Raven AI Agent Team
