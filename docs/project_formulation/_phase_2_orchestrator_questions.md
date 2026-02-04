# Phase 2 - Orchestrator Questions for Development Team

## Document Purpose

This document contains questions from the Orchestrator (AI Agent) to the Implementation Team regarding Phase 2: BATCH_SELECTOR_AGENT implementation.

**From:** Orchestrator Team (AI Agent)
**To:** Implementation Team
**Date:** 2026-02-03
**Status:** ❓ AWAITING ANSWERS

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

**Answer:** *(Implementation team please respond)*

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

**Answer:** *(Implementation team please respond)*

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

**Answer:** *(Implementation team please respond)*

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

**Answer:** *(Implementation team please respond)*

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

**Answer:** *(Implementation team please respond)*

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

**Answer:** *(Implementation team please respond)*

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

**Answer:** *(Implementation team please respond)*

---

## Summary Table

| # | Question | Priority | Status |
|---|----------|----------|--------|
| 1 | Cost Data Source | HIGH | ⏳ PENDING |
| 2 | Partial Batch Selection | HIGH | ⏳ PENDING |
| 3 | Multi-Warehouse Support | MEDIUM | ⏳ PENDING |
| 4 | TDS Specification Source | HIGH | ⏳ PENDING |
| 5 | Blend Calculation Precision | MEDIUM | ⏳ PENDING |
| 6 | Error Handling Strategy | MEDIUM | ⏳ PENDING |
| 7 | Raven Channel Integration | LOW | ⏳ PENDING |

---

## Response Instructions

Please respond to each question by:
1. Editing this file directly
2. Replacing "*(Implementation team please respond)*" with your answer
3. Updating the Status column in the Summary Table to "✅ ANSWERED"
4. Committing with message: "Phase 2: Answer orchestrator questions"

---

*Awaiting implementation team responses to proceed with Phase 2 development.*
