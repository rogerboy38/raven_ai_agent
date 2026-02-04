# Phase 2 - Orchestrator Questions for Development Team

## Document Purpose

This document contains questions from the Orchestrator (AI Agent) to the Implementation Team regarding Phase 2: BATCH_SELECTOR_AGENT implementation.

**From:** Orchestrator Team (AI Agent)
**To:** Implementation Team
**Date:** 2026-02-03
**Status:** ✅ ANSWERED

---

## Questions

### Question 1: Cost Data Source

> **Q:** Where should the `unit_cost` for each batch be retrieved from?

**Context:**
The `BatchSelection` data class requires a `unit_cost` field for cost optimization. I need to know:
- Is cost stored in `Batch AMB` doctype?
- Should we use `Item Price` doctype?
- Is there a `Valuation Rate` field in `Bin` or `Stock Ledger Entry`?
- Or should we calculate from Purchase Invoice/Receipt?

**Options:**
- A) `Batch AMB.valuation_rate`
- B) `frappe.get_value('Item Price', ...)`
- C) `Stock Ledger Entry` average
- D) Other: _____________

**Answer:** 

**Option C with fallback to A** - Use this priority order:

1. **Primary:** Query `Stock Ledger Entry` for the specific batch to get actual valuation rate:
```python
def get_batch_cost(batch_id, item_code):
    # Get latest valuation rate from Stock Ledger Entry
    sle = frappe.get_value(
        'Stock Ledger Entry',
        filters={
            'batch_no': batch_id,
            'item_code': item_code,
            'actual_qty': ['>', 0]  # Incoming entries
        },
        fieldname='valuation_rate',
        order_by='posting_date desc, posting_time desc'
    )
    if sle:
        return sle
    
    # Fallback to Item's valuation rate
    return frappe.get_value('Item', item_code, 'valuation_rate') or 0
```

2. **Fallback:** If no SLE found, use `Item.valuation_rate`
3. **Last resort:** Return 0 and flag as `cost_unknown: True`

---

### Question 2: Partial Batch Selection

> **Q:** When a batch has more stock than needed, should we allow partial selection?

**Context:**
Example scenario:
- Required: 50 kg
- Batch LOTE040: 120 kg available
- Should we select 50 kg from LOTE040, or only use batches that can be fully consumed?

**Options:**
- A) Yes, allow partial selection (take only what's needed)
- B) No, prefer batches that can be fully consumed (FEFO benefit)
- C) Configurable via parameter

**Answer:** 

**Option A - Allow partial selection**

Rationale:
- FEFO principle means oldest batches should be consumed first
- Leaving stock in oldest batches defeats FEFO purpose
- Partial consumption from oldest batch is correct behavior
- Full consumption preference would violate FEFO when oldest batch has excess stock

Implementation:
```python
allocated_qty = min(batch['available_qty'], remaining_qty)
```

---

### Question 3: Multi-Warehouse Support

> **Q:** Should batch selection span multiple warehouses or be limited to one?

**Context:**
The `select_optimal_batches()` function has an optional `warehouse` parameter. I need clarity on:
- If `warehouse=None`, should we query ALL warehouses?
- Should there be a warehouse priority order?
- Are there transfer costs to consider between warehouses?

**Options:**
- A) Single warehouse only (warehouse parameter required)
- B) Multi-warehouse allowed, no priority
- C) Multi-warehouse with priority list
- D) Multi-warehouse with transfer cost consideration

**Answer:** 

**Option B - Multi-warehouse allowed, no priority**

Rationale:
- If `warehouse=None`, query all warehouses
- FEFO takes priority over warehouse location
- Transfer costs are out of scope for Phase 2 (can be added in optimization phase)
- User can filter by warehouse if needed

Default warehouse for production:
```python
DEFAULT_WAREHOUSE = 'FG to Sell Warehouse - AMB-W'
```

If user needs specific warehouse, they pass it explicitly.

---

### Question 4: TDS Specification Source

> **Q:** What is the exact doctype and field structure for TDS specifications?

**Context:**
The `check_tds_compliance()` function needs TDS specs with min/max values. I need to know:
- Is it `TDS AMB` doctype?
- What are the child table field names? (`parameter`, `min_value`, `max_value`?)
- How is TDS linked to products? By `item_code` or `item_group`?

**Please provide:**
```python
# Example TDS structure
tds_spec = {
    "doctype": "???",
    "link_field": "???",
    "child_table": "???",
    "fields": {
        "parameter": "???",
        "min": "???",
        "max": "???",
        "unit": "???"
    }
}
```

**Answer:** 

Based on Phase 1 analysis, TDS specifications are stored in **COA AMB** (and COA AMB2) doctypes. The structure is:

```python
# TDS/COA Structure
tds_spec = {
    "doctype": "COA AMB",  # or "COA AMB2" as fallback
    "link_field": "lot_number",  # Links to batch via lot_number
    "child_table": None,  # Parameters are in the parent doc
    "fields": {
        "parameter": "specification",  # Parameter name field
        "value": "value",              # Actual measured value
        "min": "minimum",              # Minimum acceptable value
        "max": "maximum",              # Maximum acceptable value
        "unit": "uom"                  # Unit of measure
    }
}

# Query example:
coa_records = frappe.get_all(
    'COA AMB',
    filters={'lot_number': batch_name},
    fields=['specification', 'value', 'minimum', 'maximum', 'uom']
)
```

**Note:** Phase 1 already implemented `get_batch_coa_parameters()` and `check_tds_compliance()` in `formulation_reader/reader.py` - we should reuse those functions.

---

### Question 5: Blend Calculation Precision

> **Q:** What decimal precision should be used for weighted average calculations?

**Context:**
When calculating weighted averages for blend compliance:
- COA parameters may have varying precision (e.g., Aloin: 0.5 mg/L, Solids: 1.2%)
- Should we round to a specific decimal place?
- Should we use `flt()` with precision parameter?

**Options:**
- A) Use 2 decimal places for all
- B) Use 4 decimal places for all
- C) Match precision to TDS specification
- D) Use Frappe's default float precision

**Answer:** 

**Option D - Use Frappe's default float precision with flt()**

Rationale:
- Frappe's `flt()` function handles precision consistently
- Default precision is typically 9 decimal places internally
- For display/comparison, use 4 decimal places

Implementation:
```python
from frappe.utils import flt

def calculate_weighted_average(batch_params_list):
    """Calculate weighted average for each parameter."""
    total_qty = flt(sum(b['quantity'] for b in batch_params_list))
    
    # Get all unique parameters
    all_params = set()
    for b in batch_params_list:
        all_params.update(b['coa_params'].keys())
    
    weighted_avgs = {}
    for param in all_params:
        weighted_sum = flt(0)
        for b in batch_params_list:
            if param in b['coa_params']:
                value = flt(b['coa_params'][param].get('value', 0))
                qty = flt(b['quantity'])
                weighted_sum += value * qty
        
        weighted_avgs[param] = flt(weighted_sum / total_qty, 4)  # 4 decimal places
    
    return weighted_avgs
```

---

### Question 6: Error Handling Strategy

> **Q:** How should the batch selector handle edge cases?

**Context:**
I need guidance on error handling for:

| Scenario | Proposed Behavior |
|----------|-------------------|
| No batches available | Return empty list? Raise exception? |
| Insufficient total stock | Return partial? Raise exception? |
| No compliant batches | Return best effort? Raise exception? |
| COA missing for batch | Skip batch? Use defaults? |

**Answer:** 

**Return structured responses with status codes - NEVER raise exceptions for business logic**

| Scenario | Behavior | Status Code |
|----------|----------|-------------|
| No batches available | Return empty list with status | `NO_STOCK` |
| Insufficient total stock | Return partial selection with shortfall | `PARTIAL` |
| No compliant batches | Return best available with warning | `NON_COMPLIANT_WARNING` |
| COA missing for batch | Include batch with `coa_status: 'MISSING'` | `COA_INCOMPLETE` |

Implementation:
```python
def select_optimal_batches(...):
    result = {
        'status': 'COMPLETE',  # or PARTIAL, NO_STOCK, etc.
        'selected_batches': [],
        'total_allocated': 0,
        'shortfall': 0,
        'warnings': [],
        'errors': []
    }
    
    if not available_batches:
        result['status'] = 'NO_STOCK'
        result['errors'].append(f'No batches found for {product_code}')
        return result
    
    # ... selection logic ...
    
    if remaining > 0:
        result['status'] = 'PARTIAL'
        result['shortfall'] = remaining
        result['warnings'].append(f'Only {total_allocated} of {required_qty} available')
    
    return result
```

---

### Question 7: Raven Channel Integration

> **Q:** Should the BATCH_SELECTOR_AGENT send notifications via Raven channel?

**Context:**
Based on the `RAVEN_CHANNEL_COMMUNICATION_SPEC.md`, we proposed using Raven channels. Should this skill:
- Send selection results to a channel?
- Notify on compliance failures?
- Request human approval for large orders?

**Options:**
- A) No Raven integration in Phase 2
- B) Basic notifications only
- C) Full integration with approval workflow

**Answer:** 

**Option A - No Raven integration in Phase 2**

Rationale:
- Phase 2 should focus on core batch selection logic
- Raven integration is orchestrator-level concern
- The `RavenOrchestrator` channel created in Phase 1 will be used by the main orchestrator
- Individual skills should be pure functions that return data

The `formulation_orchestrator` (created in Phase 1) will:
1. Call `batch_selector` skill
2. Send notifications via `RavenOrchestrator` if needed
3. Handle approval workflows at orchestration level

This keeps skills modular and testable.

---

## Summary Table

| # | Question | Priority | Status |
|---|----------|----------|--------|
| 1 | Cost Data Source | HIGH | ✅ ANSWERED |
| 2 | Partial Batch Selection | HIGH | ✅ ANSWERED |
| 3 | Multi-Warehouse Support | MEDIUM | ✅ ANSWERED |
| 4 | TDS Specification Source | HIGH | ✅ ANSWERED |
| 5 | Blend Calculation Precision | MEDIUM | ✅ ANSWERED |
| 6 | Error Handling Strategy | MEDIUM | ✅ ANSWERED |
| 7 | Raven Channel Integration | LOW | ✅ ANSWERED |

---

## Response Instructions

~~Please respond to each question by:~~
~~1. Editing this file directly~~
~~2. Replacing "*(Implementation team please respond)*" with your answer~~
~~3. Updating the Status column in the Summary Table to "✅ ANSWERED"~~
~~4. Committing with message: "Phase 2: Answer orchestrator questions"~~

**COMPLETED:** All questions answered by Implementation Team on 2026-02-04.

---

## Next Steps

With these questions answered, we can proceed with Phase 2 implementation:

1. ✅ Questions answered
2. ⏳ Create `skills/batch_selector/` structure
3. ⏳ Implement core functions
4. ⏳ Write unit tests
5. ⏳ Integration testing with Phase 1

---

*Ready to proceed with Phase 2 implementation.*
