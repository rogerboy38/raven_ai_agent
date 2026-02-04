# Feature: Suggest Alternatives for Non-Compliant Batches

**Status:** NOT IMPLEMENTED  
**Priority:** High  
**Target Module:** formulation_reader  
**Date:** February 3, 2026  

---

## Overview

This feature will provide intelligent suggestions for alternative batches when a selected batch fails TDS compliance validation. The feature integrates with the formulation_reader skill to analyze available inventory and recommend compliant alternatives.

---

## Problem Statement

When a batch fails TDS compliance checks, users currently have no automated way to:
1. Identify which batches could be used as alternatives
2. Understand which parameters are causing non-compliance
3. Find batches that could be blended to achieve compliance
4. Get recommendations based on FEFO (First Expired, First Out) principles

---

## Proposed Solution

### Integration Point: formulation_reader

The `formulation_reader` skill will be extended with a new action:

```python
action: "suggest_alternatives"
```

### Workflow

```
┌─────────────────────┐
│  TDS Compliance     │
│  Check FAILS        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  formulation_reader │
│  .suggest_alternatives()
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Query Available    │
│  Batches            │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Filter by COA      │
│  Parameters         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Return Ranked      │
│  Alternatives       │
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

## Implementation Requirements

### 1. formulation_reader Extensions

```python
# New method in formulation_reader skill
def suggest_alternatives(
    non_compliant_batch: str,
    failed_parameters: List[Dict],
    required_quantity: float,
    tds_spec: Dict,
    options: Dict = None
) -> Dict:
    """
    Suggest alternative batches for non-compliant batch.
    
    Args:
        non_compliant_batch: Golden number of failed batch
        failed_parameters: List of parameters that failed
        required_quantity: Quantity needed
        tds_spec: TDS specification to comply with
        options: Configuration options
        
    Returns:
        Dict with alternatives and analysis
    """
    pass
```

### 2. Query Logic

```python
def _find_compliant_batches(
    item_code: str,
    tds_spec: Dict,
    min_quantity: float
) -> List[Dict]:
    """
    Find batches that meet TDS specs.
    
    Query filters:
    - Same item_code
    - Available quantity >= min_quantity
    - Not disabled/expired
    - COA parameters within spec limits
    """
    pass
```

### 3. Blend Calculator

```python
def _calculate_blend_options(
    non_compliant_batch: Dict,
    available_batches: List[Dict],
    target_spec: Dict,
    required_qty: float
) -> List[Dict]:
    """
    Calculate blend ratios to achieve compliance.
    
    Algorithm:
    1. Identify batches with opposite parameter deviations
    2. Calculate weighted average for different ratios
    3. Find optimal blend that meets all specs
    4. Return ranked blend options
    """
    pass
```

---

## Integration with Existing Skills

### Phase Flow

```
Phase 2 (batch_selector)
        │
        ▼
Phase 3 (tds_compliance) ──FAIL──► formulation_reader.suggest_alternatives()
        │                                    │
        │ PASS                               ▼
        ▼                          Return alternatives to user
Phase 4 (cost_calculator)
```

### Skill Dependencies

| Skill | Role |
|-------|------|
| batch_selector | Provides batch inventory data |
| tds_compliance | Identifies non-compliant parameters |
| formulation_reader | **NEW: Suggests alternatives** |
| cost_calculator | Can evaluate cost of alternatives |

---

## Data Requirements

### From Frappe/ERPNext

1. **Batch DocType**
   - batch_id (golden number)
   - item_code
   - batch_qty
   - manufacturing_date
   - expiry_date
   - warehouse

2. **COA (Certificate of Analysis)**
   - Linked to batch
   - Parameter values
   - Test dates

3. **TDS Specification**
   - Parameter limits (min/max)
   - Linked to item/customer

---

## User Stories

### US-1: Find Single Batch Alternative
```
As a production planner,
When a batch fails compliance,
I want to see alternative batches that pass all specs,
So I can quickly substitute without delays.
```

### US-2: Get Blend Recommendations
```
As a formulation specialist,
When no single batch is compliant,
I want to see blend options that achieve compliance,
So I can use existing inventory efficiently.
```

### US-3: FEFO-Prioritized Suggestions
```
As an inventory manager,
I want alternatives sorted by expiry date,
So I can prioritize batches closest to expiration.
```

---

## Acceptance Criteria

- [ ] `suggest_alternatives` action added to formulation_reader
- [ ] Returns at least 1 alternative when compliant batches exist
- [ ] Blend calculations are mathematically accurate
- [ ] FEFO sorting is applied by default
- [ ] Response includes compliance scores
- [ ] Handles case when no alternatives found gracefully
- [ ] Unit tests cover all scenarios
- [ ] Integration tests with tds_compliance

---

## Next Steps

1. **Parallel Team Review** - Review this spec with formulation_reader team
2. **API Finalization** - Confirm request/response format
3. **Implementation** - Add suggest_alternatives to formulation_reader
4. **Testing** - Unit and integration tests
5. **Documentation** - Update skill documentation

---

**Document Version:** 1.0  
**Last Updated:** February 3, 2026  
**Owner:** Raven AI Agent Team
