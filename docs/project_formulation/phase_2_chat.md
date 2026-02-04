# Phase 2 - BATCH_SELECTOR_AGENT Communication

## Document Purpose

This document establishes the communication channel between the Orchestrator Team (AI Agent) and the Implementation Team for Phase 2 of the Formulation Orchestration project.

**From:** Orchestrator Team (AI Agent)
**To:** Implementation Team
**Date:** 2026-02-03
**Status:** 🟡 IN PROGRESS

---

## 1. Phase 2 Overview

### 1.1 Objective

Implement the **BATCH_SELECTOR_AGENT** skill that intelligently selects batches for formulations based on:
- FEFO (First Expired, First Out) ordering
- TDS compliance matching
- Cost optimization
- Quantity requirements

### 1.2 Dependencies

| Dependency | Status | Location |
|------------|--------|----------|
| Phase 1: formulation_reader | ✅ COMPLETE | `skills/formulation_reader/` |
| Bin doctype queries | ✅ AVAILABLE | ERPNext |
| COA AMB/AMB2 doctypes | ✅ AVAILABLE | ERPNext |
| TDS specifications | ✅ AVAILABLE | ERPNext |

### 1.3 Expected Deliverable

```
skills/batch_selector/
├── __init__.py
├── selector.py          # Main batch selection logic
├── optimizer.py         # Cost/FEFO optimization
├── SKILL.md             # Documentation
└── tests.py             # Unit tests
```

---

## 2. Technical Specification

### 2.1 Core Functions

#### Function 1: `select_optimal_batches()`

```python
def select_optimal_batches(
    product_code: str,
    required_qty: float,
    tds_specs: dict,
    warehouse: str = None,
    optimization_mode: str = "fefo"  # fefo | cost | balanced
) -> List[BatchSelection]:
    """
    Select optimal batches for a formulation ingredient.
    
    Args:
        product_code: Item code (e.g., '0612' for Aloe Vera)
        required_qty: Required quantity in kg
        tds_specs: TDS specification dict with min/max values
        warehouse: Optional warehouse filter
        optimization_mode: Selection strategy
        
    Returns:
        List of BatchSelection objects with batch_id, qty, cost, fefo_key
    """
```

#### Function 2: `validate_blend_compliance()`

```python
def validate_blend_compliance(
    selected_batches: List[BatchSelection],
    tds_specs: dict
) -> ComplianceResult:
    """
    Validate that selected batch blend meets TDS specifications.
    
    Uses weighted average calculation from formulation_reader.
    
    Returns:
        ComplianceResult with pass/fail status and parameter details
    """
```

#### Function 3: `calculate_blend_cost()`

```python
def calculate_blend_cost(
    selected_batches: List[BatchSelection]
) -> CostBreakdown:
    """
    Calculate total cost and cost breakdown for selected batches.
    
    Returns:
        CostBreakdown with total_cost, per_kg_cost, batch_costs
    """
```

#### Function 4: `find_alternative_batches()`

```python
def find_alternative_batches(
    product_code: str,
    excluded_batches: List[str],
    tds_specs: dict
) -> List[BatchInfo]:
    """
    Find alternative batches when primary selection fails compliance.
    
    Returns:
        List of alternative batch options sorted by suitability
    """
```

### 2.2 Data Classes

```python
@dataclass
class BatchSelection:
    batch_id: str
    item_code: str
    quantity: float
    available_qty: float
    fefo_key: str
    unit_cost: float
    coa_parameters: dict
    warehouse: str

@dataclass
class ComplianceResult:
    is_compliant: bool
    parameter_results: List[ParameterResult]
    weighted_averages: dict
    failed_parameters: List[str]

@dataclass
class CostBreakdown:
    total_cost: float
    total_quantity: float
    per_kg_cost: float
    batch_costs: List[dict]
```

### 2.3 Optimization Modes

| Mode | Priority | Description |
|------|----------|-------------|
| `fefo` | Expiry date | Select batches expiring soonest first |
| `cost` | Lowest cost | Select cheapest batches first |
| `balanced` | Combined | Balance between FEFO and cost |

---

## 3. Integration with Phase 1

The BATCH_SELECTOR_AGENT must use functions from `formulation_reader`:

```python
from raven_ai_agent.skills.formulation_reader import (
    get_available_batches,
    get_batch_coa_parameters,
    check_tds_compliance,
    parse_golden_number
)

# Example usage
batches = get_available_batches(product_code='0612', warehouse='AMB-W')
for batch in batches:
    params = get_batch_coa_parameters(batch['batch_id'])
    compliance = check_tds_compliance(params, tds_specs)
```

---

## 4. Test Cases Required

### 4.1 Unit Tests

| Test | Description | Priority |
|------|-------------|----------|
| `test_select_single_batch` | Select one batch that meets requirements | HIGH |
| `test_select_multiple_batches` | Combine batches to meet quantity | HIGH |
| `test_fefo_ordering` | Verify FEFO priority selection | HIGH |
| `test_cost_optimization` | Verify cost mode selects cheapest | MEDIUM |
| `test_compliance_validation` | Validate blend meets TDS | HIGH |
| `test_insufficient_stock` | Handle when stock < required | MEDIUM |
| `test_no_compliant_batches` | Handle when no batches meet TDS | MEDIUM |
| `test_alternative_suggestions` | Suggest alternatives on failure | LOW |

### 4.2 Golden Test

```python
def test_aloe_vera_batch_selection():
    """
    Golden test: Select batches for Aloe Vera 200X formulation.
    
    Given:
        - Product: 0612 (Aloe Vera 200X)
        - Required: 100 kg
        - TDS: Aloin 0.5-2.0 mg/L, Solids 0.8-1.5%
        
    Expected:
        - Batches selected in FEFO order
        - Total quantity >= 100 kg
        - Blend meets TDS specifications
    """
```

---

## 5. Questions for Orchestrator

*Implementation team: Add your questions below*

### Question 1: [Your question here]
> **Q:** 

**Answer:** *(Orchestrator will respond)*

### Question 2: [Your question here]
> **Q:** 

**Answer:** *(Orchestrator will respond)*

---

## 6. Implementation Checklist

| Task | Status | Owner |
|------|--------|-------|
| Create `skills/batch_selector/` folder | ⏳ PENDING | Impl Team |
| Implement `select_optimal_batches()` | ⏳ PENDING | Impl Team |
| Implement `validate_blend_compliance()` | ⏳ PENDING | Impl Team |
| Implement `calculate_blend_cost()` | ⏳ PENDING | Impl Team |
| Implement `find_alternative_batches()` | ⏳ PENDING | Impl Team |
| Write unit tests | ⏳ PENDING | Impl Team |
| Create SKILL.md documentation | ⏳ PENDING | Impl Team |
| Integration testing with Phase 1 | ⏳ PENDING | Impl Team |

---

## 7. Communication Log

| Date | From | To | Message |
|------|------|-----|----------|
| 2026-02-03 | Orchestrator | Impl Team | Created Phase 2 spec |

---

## 8. Reference Documents

- [PHASE2_BATCH_SELECTOR_AGENT.md](./PHASE2_BATCH_SELECTOR_AGENT.md) - Full technical spec
- [PHASE1_IMPLEMENTATION_REPORT.md](./PHASE1_IMPLEMENTATION_REPORT.md) - Phase 1 completion report
- [phase_1_additional_questions.md](./phase_1_additional_questions.md) - Phase 1 closure document
- [RAVEN_CHANNEL_COMMUNICATION_SPEC.md](./RAVEN_CHANNEL_COMMUNICATION_SPEC.md) - Raven channel proposal

---

*Awaiting implementation team acknowledgment to begin Phase 2.*
