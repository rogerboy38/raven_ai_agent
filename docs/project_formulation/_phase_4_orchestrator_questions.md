# Phase 4: Cost Calculator - Orchestrator Questions

## Document Purpose
This document contains questions for the orchestrator regarding Phase 4 (Cost Calculator) implementation, review, and integration.

---

## Questions & Answers

### Q1: What is the current state of the Cost Calculator implementation?

**Answer:** The implementation exists at `raven_ai_agent/skills/formulation_orchestrator/agents/cost_calculator.py` with basic functionality:
- Basic cost calculation (`calculate_costs`)
- Single batch estimation (`estimate_batch_cost`)
- Scenario comparison (`compare_scenarios`)
- Cost breakdown by category (`get_cost_breakdown`)

However, there are gaps identified in the Implementation Report that need to be addressed.

---

### Q2: What are the HIGH PRIORITY gaps that need to be addressed?

**Answer:** Three high-priority gaps were identified:

1. **Gap 1: Phase 3 Input Transformation**
   - Issue: Implementation doesn't accept Phase 3 output format
   - Solution: Add `_transform_phase3_input()` method

2. **Gap 2: Price Lookup Priority**
   - Issue: Only uses valuation_rate, missing Item Price lookup
   - Solution: Implement `_get_item_price()` with full fallback logic

3. **Gap 3: Output Format Restructuring**
   - Issue: Output doesn't match contract specification
   - Solution: Restructure return format to match Phase 4 contract

---

### Q3: What is the pricing lookup priority order?

**Answer:** Per PHASE4_COST_CALCULATOR.md specification:

1. Batch-specific Item Price (if batch pricing exists)
2. Item Price with valid_from <= today and valid_upto >= today (or null)
3. Item Price for the specified price_list
4. Item's standard_rate field
5. Item's last_purchase_rate field
6. Item's valuation_rate field

---

### Q4: What ERPNext doctypes are involved in cost calculation?

**Answer:**

| Doctype | Purpose | Key Fields |
|---------|---------|------------|
| Item Price | Primary pricing source | item_code, price_list, price_list_rate, currency, valid_from, valid_upto, batch_no |
| Price List | Price list definitions | name, buying, selling, currency, enabled |
| Item | Fallback pricing | standard_rate, valuation_rate, last_purchase_rate |

---

### Q5: How does Phase 4 integrate with the workflow?

**Answer:**

**Input from Phase 3:**
- Receives `compliance_results` with TDS-validated batches
- Only processes batches with `tds_status = "COMPLIANT"`
- Uses `allocated_qty` for cost calculation

**Output to Phase 5:**
- Cost data enables cost-based optimization
- Supports finding lowest-cost batch combinations
- Enables what-if analysis for different scenarios

---

### Q6: What tests are required for Phase 4?

**Answer:**

**HIGH PRIORITY:**
- `test_price_lookup_priority` - Verify price fallback logic
- `test_phase3_input_transformation` - Test input format handling
- `test_compliant_batch_filtering` - Only cost COMPLIANT batches

**MEDIUM PRIORITY:**
- `test_output_format_compliance` - Validate output matches contract
- `test_currency_tracking` - Verify currency handling
- `test_warnings_generation` - Verify warnings are generated

**INTEGRATION:**
- `test_phase3_to_phase4_flow` - End-to-end Phase 3 to 4
- `test_phase4_to_phase5_handoff` - Verify output format for Phase 5

---

### Q7: What is the expected output format from Phase 4?

**Answer:**

```json
{
  "cost_breakdown": [
    {
      "item_code": "ALO-LEAF-GEL-RAW",
      "item_name": "Aloe Vera Leaf Gel (Raw)",
      "total_qty": 500,
      "uom": "Kg",
      "batch_costs": [...],
      "item_total_cost": 7750.00
    }
  ],
  "summary": {
    "total_material_cost": 12500.00,
    "currency": "MXN",
    "finished_qty": 100,
    "finished_uom": "Kg",
    "cost_per_unit": 125.00,
    "items_costed": 3,
    "batches_costed": 5
  },
  "pricing_sources": [...],
  "warnings": []
}
```

---

### Q8: What are the success criteria for Phase 4?

**Answer:** Phase 4 is complete when:

- [ ] Can query Item Price by item_code and price_list
- [ ] Price lookup respects valid_from and valid_upto dates
- [ ] Batch-specific pricing is supported
- [ ] Fallback to Item rates (standard_rate, last_purchase_rate, valuation_rate)
- [ ] Cost calculation is accurate (qty * unit_price)
- [ ] Currency is tracked correctly
- [ ] Non-compliant batches are skipped with warnings
- [ ] Cost per unit of finished product is calculated
- [ ] Missing prices generate appropriate warnings
- [ ] Output format matches contract specification
- [ ] Integration test with Phase 3 output passes

---

### Q9: What error handling is required?

**Answer:**

| Error Type | Handling |
|------------|----------|
| NO_PRICE | Use zero cost, add warning with action_required |
| CURRENCY_MISMATCH | Add warning, suggest conversion may be needed |
| EXPIRED_PRICE | Add warning with expiration date |
| NON_COMPLIANT_BATCH | Skip batch, add warning |

---

### Q10: What is the implementation priority?

**Answer:**

| Priority | Improvement | Effort | Impact |
|----------|-------------|--------|--------|
| 1 | Phase 3 Input Transformation | Medium | High |
| 2 | Price Lookup Priority Logic | High | High |
| 3 | Output Format Restructure | Medium | High |
| 4 | Warnings Array | Low | Medium |
| 5 | Pricing Sources Tracking | Low | Medium |
| 6 | Item Name Lookup | Low | Low |

---

## Status

**Document Status:** ACTIVE
**Phase Status:** IMPLEMENTATION IN PROGRESS
**Last Updated:** February 3, 2026
**Next Action:** Implement high-priority gaps
