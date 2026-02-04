# Phase 2 - Implementation Team Questions

## Document Purpose

Questions from the Implementation Team (AI Agent) to the Orchestrator/Parallel Team regarding Phase 2 BATCH_SELECTOR_AGENT implementation.

**From:** Implementation Team (AI Agent)
**To:** Orchestrator/Parallel Team
**Date:** 2026-02-04
**Status:** ✅ ANSWERED

---

## Question 1: Golden Number Pattern Clarification

> **Q:** In Phase 1, we implemented `parse_golden_number()` with pattern `ITEM_PPPPFFYYPS` (product code + folio + year + plant + sequence). The Phase 2 spec shows a different pattern `YYWWDS` (year + week + day + sequence). Which pattern should we use for FEFO sorting?
>
> **Example from Phase 1:** `ITEM_0617027231` → product=0617, folio=27, year=23, plant=1
> **Example from Phase 2:** `ALOE-200X-PWD-250311` → year=25, week=03, day=1, seq=1
>
> Are these two different item code formats that we need to support both?

**Answer:** *(Awaiting response)*

---

## Question 2: Architecture - Standalone vs Orchestrator Integration

> **Q:** In Phase 1, we created a `formulation_orchestrator` skill with sub-agents including a `batch_selector` agent at `skills/formulation_orchestrator/agents/batch_selector.py`. The Phase 2 spec requests a standalone `skills/batch_selector/` skill.
>
> Should we:
> - **Option A:** Create standalone `skills/batch_selector/` as specified (independent skill)
> - **Option B:** Enhance existing `formulation_orchestrator/agents/batch_selector.py` (orchestrator pattern)
> - **Option C:** Both - standalone skill that the orchestrator's sub-agent wraps/calls

**Answer:** *(Awaiting response)*

---

## Question 3: Cost Data Source

> **Q:** The spec mentions cost optimization mode (`optimization_mode: "cost"`), but doesn't specify where batch/item cost data comes from. Which ERPNext doctype contains the cost information?
>
> Possible sources:
> - `Item` doctype → `valuation_rate` field?
> - `Bin` doctype → has cost fields?
> - `Stock Ledger Entry` → historical costs?
> - `Batch` doctype → custom cost field?
> - `Purchase Receipt` → purchase price?

**Answer:** *(Awaiting response)*

---

## Question 4: Default Warehouse

> **Q:** Phase 1 used `'FG to Sell Warehouse - AMB-W'` as the default warehouse. Phase 2 spec shows `'Main Warehouse - AMB'`. Which warehouse should be the default for batch selection?
>
> Or should we query all warehouses by default and let users filter?

**Answer:** *(Awaiting response)*

---

## Question 5: TDS Specification Source

> **Q:** The `select_optimal_batches()` function accepts `tds_specs: dict` parameter. Where do these TDS specifications come from?
>
> - Is there a `TDS Specification` doctype?
> - Are they stored in the `Item` doctype?
> - Should we query from `Quality Inspection Template`?
> - Are they passed from Phase 1 output?

**Answer:** *(Awaiting response)*

---

## Question 6: Raven Channel Integration

> **Q:** In Phase 1, we created `RavenOrchestrator` channel for inter-agent communication (`channels/raven_channel.py`). Should the batch_selector skill:
>
> - **Option A:** Use RavenOrchestrator for communication with other agents
> - **Option B:** Be a standard frappe whitelist function (direct API calls)
> - **Option C:** Support both modes

**Answer:** *(Awaiting response)*

---

## Question 7: Expired Batch Handling

> **Q:** The spec mentions filtering out expired batches. Should we:
>
> - **Option A:** Completely exclude expired batches from selection
> - **Option B:** Include them with a warning flag
> - **Option C:** Make it configurable via parameter (`include_expired: bool`)
>
> Also, should we add a "near expiry" warning for batches expiring within X days?

**Answer:** *(Awaiting response)*

---

## Question 8: Reserved Quantity Handling

> **Q:** The spec shows `available = actual_qty - reserved_qty`. When we allocate batches:
>
> - Should we UPDATE the `reserved_qty` in Bin when batches are selected?
> - Or is reservation handled by a separate process?
> - What happens if same batches are selected by multiple concurrent requests?

**Answer:** *(Awaiting response)*

---

## Question 9: Integration with formulation_reader

> **Q:** The spec shows importing from `formulation_reader`:
> ```python
> from raven_ai_agent.skills.formulation_reader import (
>     get_available_batches,
>     get_batch_coa_parameters,
>     check_tds_compliance,
>     parse_golden_number
> )
> ```
>
> Our Phase 1 `formulation_reader` has `parse_golden_number()` with the PPPPFFYYPS pattern. Should we:
> - Update Phase 1 to support both patterns?
> - Create a new parser in batch_selector?
> - Have both parsers and detect which pattern to use?

**Answer:** *(Awaiting response)*

---

## Question 10: Weighted Average Calculation

> **Q:** For `validate_blend_compliance()`, we need to calculate weighted averages of COA parameters when blending multiple batches. Should we:
>
> - Use the `calculate_weighted_average()` from Phase 1?
> - Implement a new calculation specific to batch blending?
> - What's the formula: `sum(param_value * qty) / total_qty`?

**Answer:** *(Awaiting response)*

---

## Implementation Notes

Based on the answers, we will:

1. Create the appropriate skill structure
2. Implement core functions with correct data sources
3. Integrate with Phase 1 as specified
4. Prepare for handoff to Phase 3 (TDS_COMPLIANCE_CHECKER)

---

## Communication Log

| Date | From | To | Message |
|------|------|-----|----------|
| 2026-02-04 | Impl Team | Orchestrator | Created Phase 2 questions document |

---

*All questions answered - ready to proceed with implementation.*

---

## ANSWERS FROM ORCHESTRATOR TEAM

**Date:** 2026-02-04
**Answered by:** Orchestrator/Parallel Team

---

### Answer 1: Golden Number Pattern Clarification

**Support BOTH patterns with auto-detection.**

The system has two item code formats:
1. **Legacy Format (Phase 1):** `ITEM_PPPPFFYYPS` - Product + Folio + Year + Plant + Sequence
2. **New Format (Phase 2):** `ITEM-NAME-YYWWDS` - Year + Week + Day + Sequence

Implementation approach:
```python
def parse_golden_number_universal(item_code):
    """Parse golden number supporting both formats."""
    # Try new format first (YYWWDS at end)
    match_new = re.search(r'(\d{2})(\d{2})(\d)(\d)$', item_code)
    if match_new:
        year, week, day, seq = map(int, match_new.groups())
        if 1 <= week <= 52 and 1 <= day <= 7:
            return {'format': 'YYWWDS', 'year': year, 'week': week, 'day': day, 'sequence': seq}
    
    # Try legacy format (PPPPFFYYPS)
    match_legacy = re.search(r'(\d{4})(\d{2})(\d{2})(\d)(\d?)$', item_code)
    if match_legacy:
        product, folio, year, plant, seq = match_legacy.groups()
        return {'format': 'PPPPFFYYPS', 'product': product, 'folio': int(folio), 
                'year': int(year), 'plant': plant, 'sequence': int(seq or 1)}
    
    return None  # Unable to parse
```

---

### Answer 2: Architecture - Standalone vs Orchestrator Integration

**Option C - Both approaches.**

1. Create standalone `skills/batch_selector/` with core logic
2. The orchestrator's sub-agent (`formulation_orchestrator/agents/batch_selector.py`) calls/wraps the standalone skill
3. This allows:
   - Direct API calls to batch_selector skill
   - Orchestrated calls through formulation_orchestrator
   - Reusability across different contexts

---

### Answer 3: Cost Data Source

**Use Stock Ledger Entry with fallbacks.**

Priority order:
1. `Stock Ledger Entry.valuation_rate` for specific batch
2. `Item.valuation_rate` as fallback
3. Return 0 with `cost_unknown: True` flag if no cost found

```python
def get_batch_cost(batch_id, item_code):
    sle_rate = frappe.db.get_value('Stock Ledger Entry',
        {'batch_no': batch_id, 'item_code': item_code, 'actual_qty': ['>', 0]},
        'valuation_rate', order_by='posting_date desc')
    if sle_rate:
        return flt(sle_rate)
    
    item_rate = frappe.db.get_value('Item', item_code, 'valuation_rate')
    return flt(item_rate) if item_rate else 0
```

---

### Answer 4: Default Warehouse

**Query all warehouses by default, use `FG to Sell Warehouse - AMB-W` as suggested default.**

- If `warehouse=None`: Query all warehouses
- If user needs specific warehouse: Pass explicitly
- Default constant for convenience: `DEFAULT_WAREHOUSE = 'FG to Sell Warehouse - AMB-W'`

---

### Answer 5: TDS Specification Source

**TDS specs come from COA AMB / COA AMB2 doctypes.**

The `tds_specs` parameter should contain the target specification ranges. These can be:
1. Passed from Phase 1 based on the finished product's specification
2. Queried from a `Quality Inspection Template` linked to the item
3. Provided by the user/caller

For Phase 2, assume `tds_specs` is passed as input (from orchestrator or API call).

---

### Answer 6: Raven Channel Integration

**Option B - Standard frappe whitelist function.**

The standalone skill should be a pure function (frappe whitelist). The orchestrator handles Raven channel communication at a higher level.

---

### Answer 7: Expired Batch Handling

**Option C - Configurable with sensible defaults.**

```python
def select_optimal_batches(
    ...
    include_expired: bool = False,
    near_expiry_days: int = 30
):
    # Filter expired batches unless explicitly included
    if not include_expired:
        batches = [b for b in batches if not is_expired(b)]
    
    # Flag batches near expiry
    for batch in selected:
        if is_near_expiry(batch, near_expiry_days):
            batch['warnings'].append(f'Expires within {near_expiry_days} days')
```

---

### Answer 8: Reserved Quantity Handling

**DO NOT update reserved_qty during selection - this is read-only.**

- Batch selection is a QUERY operation, not a TRANSACTION
- Reservation should happen when a Work Order or Stock Entry is created
- Concurrent request handling is managed by ERPNext's transactional system
- Return `available_qty = actual_qty - reserved_qty` as read-only value

---

### Answer 9: Integration with formulation_reader

**Support both patterns with universal parser.**

Update the standalone `batch_selector` skill to include a universal parser that handles both formats. Keep Phase 1's parser as-is for backward compatibility.

The batch_selector will have its own `parse_golden_number_universal()` that supports both formats.

---

### Answer 10: Weighted Average Calculation

**Yes, use the formula: `sum(param_value * qty) / total_qty`**

```python
def calculate_weighted_average(batches_with_params):
    """
    Calculate weighted average for blend compliance.
    
    batches_with_params: List of {quantity: float, coa_params: {param: {value: float}}}
    """
    total_qty = sum(b['quantity'] for b in batches_with_params)
    if total_qty == 0:
        return {}
    
    all_params = set()
    for b in batches_with_params:
        all_params.update(b['coa_params'].keys())
    
    weighted_avgs = {}
    for param in all_params:
        weighted_sum = sum(
            b['coa_params'].get(param, {}).get('value', 0) * b['quantity']
            for b in batches_with_params
        )
        weighted_avgs[param] = flt(weighted_sum / total_qty, 4)
    
    return weighted_avgs
```

---

## Implementation Ready

All questions have been answered. The Implementation Team can now proceed with Phase 2 development:

| Step | Task | Status |
|------|------|--------|
| 1 | Create `skills/batch_selector/` folder structure | ⏳ PENDING |
| 2 | Implement `selector.py` with core functions | ⏳ PENDING |
| 3 | Implement `optimizer.py` for FEFO/cost modes | ⏳ PENDING |
| 4 | Write unit tests in `tests.py` | ⏳ PENDING |
| 5 | Create `SKILL.md` documentation | ⏳ PENDING |
| 6 | Integration test with Phase 1 | ⏳ PENDING |

---

## Communication Log

| Date | From | To | Message |
|------|------|-----|----------|
| 2026-02-04 | Impl Team | Orchestrator | Created Phase 2 questions document |
| 2026-02-04 | Orchestrator | Impl Team | Answered all 10 questions |

---

*Ready to proceed with Phase 2 implementation.*
