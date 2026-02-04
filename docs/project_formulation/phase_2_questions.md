# Phase 2 - Implementation Team Questions

## Document Purpose

Questions from the Implementation Team (AI Agent) to the Orchestrator/Parallel Team regarding Phase 2 BATCH_SELECTOR_AGENT implementation.

**From:** Implementation Team (AI Agent)
**To:** Orchestrator/Parallel Team
**Date:** 2026-02-04
**Status:** 🟡 AWAITING RESPONSES

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

*Awaiting parallel team responses to proceed with implementation.*
