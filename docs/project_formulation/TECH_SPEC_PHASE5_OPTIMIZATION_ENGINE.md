# Technical Specification: Phase 5 Optimization Engine

**Document Version:** 1.0  
**Date:** February 4, 2026  
**Author:** Matrix Agent  
**Status:** IMPLEMENTATION COMPLETE

---

## 1. Overview

This document provides the technical specification for implementing the Phase 5 Optimization Engine. This agent is responsible for:
1. Optimizing batch selection using multiple strategies
2. Balancing FEFO compliance with cost efficiency
3. Generating what-if scenarios for decision support
4. Validating constraint satisfaction

---

## 2. Agent Architecture

### 2.1 File Location

```
raven_ai_agent/skills/formulation_orchestrator/agents/optimization_engine.py
```

### 2.2 Class Structure

```python
class OptimizationEngineAgent(BaseSubAgent):
    """
    Optimization Engine Agent (Phase 5 of workflow).
    
    Responsibilities:
    - Optimize batch selections using multiple strategies
    - Generate what-if scenario comparisons
    - Validate constraint satisfaction
    - Integrate with Phase 4 cost data
    """
    
    name = "optimization_engine"
    description = "Batch selection optimization and what-if analysis"
    emoji = "⚡"
    phase = WorkflowPhase.OPTIMIZATION
```

### 2.3 Actions

| Action | Description | Priority |
|--------|-------------|----------|
| `optimize_selection` | Main optimization entry point | HIGH |
| `generate_what_if` | Generate scenario comparisons | HIGH |
| `validate_constraints` | Check constraint satisfaction | MEDIUM |
| `compare_strategies` | Compare multiple strategies | MEDIUM |

---

## 3. Optimization Strategies

### 3.1 Strategy Enum

```python
class OptimizationStrategy(Enum):
    FEFO_COST_BALANCED = "fefo_cost_balanced"
    MINIMIZE_COST = "minimize_cost"
    STRICT_FEFO = "strict_fefo"
    MINIMUM_BATCHES = "minimum_batches"
```

### 3.2 FEFO Cost Balanced (Default)

**Algorithm:**
1. Calculate composite score: `score = (w_fefo * fefo_score) + (w_cost * cost_score)`
2. Default weights: FEFO = 0.6, Cost = 0.4
3. Sort batches by composite score (descending)
4. Allocate from sorted list until quantity fulfilled

**Key Method:**
```python
def _fefo_cost_balanced(self, batches: List[Dict], required_qty: float, 
                        weights: Dict = None) -> Dict:
    """
    Args:
        batches: Available batches with expiry_date, unit_cost, available_qty
        required_qty: Target quantity to fulfill
        weights: Optional {'fefo': 0.6, 'cost': 0.4}
    
    Returns:
        Dict with selected_batches, total_cost, metrics
    """
```

### 3.3 Minimize Cost

**Algorithm:**
1. Sort batches by unit_cost (ascending)
2. Allocate from cheapest first
3. Track FEFO violations

**Warning:** May result in FEFO violations.

### 3.4 Strict FEFO

**Algorithm:**
1. Sort batches by expiry_date (ascending)
2. Allocate from earliest expiring first
3. Zero FEFO violations guaranteed

### 3.5 Minimum Batches

**Algorithm:**
1. Sort batches by available_qty (descending)
2. Allocate from largest batches first
3. Reduces picking complexity

---

## 4. Input/Output Contracts

### 4.1 Input from Phase 4

```python
{
    'cost_data': {
        'cost_breakdown': [...],
        'summary': {...},
        'pricing_sources': [...]
    },
    'available_batches': [
        {
            'batch_id': str,
            'batch_no': str,
            'item_code': str,
            'available_qty': float,
            'allocated_qty': float,
            'unit_cost': float,
            'expiry_date': date,
            'warehouse': str,
            'tds_compliant': bool,
            'fefo_rank': int
        }
    ],
    'required_qty': float,
    'strategy': str,  # Optional, defaults to 'fefo_cost_balanced'
    'constraints': {  # Optional
        'min_remaining_shelf_life': int,
        'max_batches': int,
        'warehouse_filter': List[str],
        'exclude_batches': List[str],
        'require_same_warehouse': bool,
        'max_cost_per_unit': float
    }
}
```

### 4.2 Output to Phase 6

```python
{
    'optimization_result': {
        'status': str,  # 'OPTIMIZED', 'PARTIAL', 'FAILED'
        'strategy_used': str,
        'original_cost': float,
        'optimized_cost': float,
        'savings_amount': float,
        'savings_percent': float
    },
    'selected_batches': [
        {
            'batch_id': str,
            'batch_no': str,
            'item_code': str,
            'allocated_qty': float,
            'unit_cost': float,
            'total_cost': float,
            'expiry_date': str,
            'days_to_expiry': int,
            'warehouse': str,
            'selection_reason': str
        }
    ],
    'summary': {
        'total_quantity': float,
        'total_cost': float,
        'average_unit_cost': float,
        'batch_count': int,
        'earliest_expiry': str,
        'fefo_violations': int,
        'constraints_satisfied': bool
    },
    'what_if_scenarios': {
        'fefo_cost_balanced': {...},
        'minimize_cost': {...},
        'strict_fefo': {...},
        'minimum_batches': {...}
    },
    'comparison': {
        'lowest_cost_strategy': str,
        'best_fefo_strategy': str,
        'recommended_strategy': str,
        'recommendation_reason': str
    },
    'warnings': []
}
```

---

## 5. Constraint Validation

### 5.1 Supported Constraints

| Constraint | Type | Default | Description |
|------------|------|---------|-------------|
| `min_remaining_shelf_life` | int | 7 | Minimum days before expiry |
| `max_batches` | int | None | Maximum number of batches |
| `warehouse_filter` | List[str] | None | Allowed warehouses |
| `exclude_batches` | List[str] | [] | Batch IDs to exclude |
| `require_same_warehouse` | bool | False | All from single warehouse |
| `max_cost_per_unit` | float | None | Upper cost limit |

### 5.2 Validation Method

```python
def _validate_constraints(self, selection: List[Dict], 
                          constraints: Dict) -> Dict:
    """
    Returns:
        {
            'valid': bool,
            'violations': [
                {
                    'constraint': str,
                    'message': str,
                    'severity': 'error' | 'warning',
                    'affected_batches': List[str]
                }
            ]
        }
    """
```

---

## 6. What-If Scenario Generator

### 6.1 Purpose

Generate alternative scenarios to compare optimization strategies and support decision-making.

### 6.2 Implementation

```python
def _generate_what_if_scenarios(self, batches: List[Dict], 
                                 required_qty: float,
                                 constraints: Dict) -> Dict:
    """
    Generates comparison of all strategies.
    
    Returns:
        {
            'scenarios': {
                'fefo_cost_balanced': {
                    'selected_batches': [...],
                    'total_cost': float,
                    'batch_count': int,
                    'fefo_violations': int,
                    'earliest_expiry': str
                },
                'minimize_cost': {...},
                'strict_fefo': {...},
                'minimum_batches': {...}
            },
            'comparison': {
                'lowest_cost_strategy': str,
                'lowest_cost_value': float,
                'best_fefo_strategy': str,
                'fewest_batches_strategy': str,
                'recommended_strategy': str,
                'recommendation_reason': str
            }
        }
    """
```

---

## 7. FEFO Violation Detection

### 7.1 Definition

A FEFO violation occurs when a newer batch is used while an older batch of the same item remains unused.

### 7.2 Detection Algorithm

```python
def _count_fefo_violations(self, selected: List[Dict], 
                           available: List[Dict]) -> int:
    """
    Count FEFO violations in selection.
    
    A violation occurs when:
    - Batch A is selected with expiry_date > Batch B
    - Batch B (same item) is available but not fully used
    """
    violations = 0
    for batch in selected:
        item_code = batch['item_code']
        batch_expiry = batch['expiry_date']
        
        # Find older batches of same item that weren't fully used
        older_unused = [
            b for b in available 
            if b['item_code'] == item_code 
            and b['expiry_date'] < batch_expiry
            and b['available_qty'] > 0
            and b['batch_id'] not in [s['batch_id'] for s in selected]
        ]
        
        violations += len(older_unused)
    
    return violations
```

---

## 8. Enhanced Test Plan

### 8.1 Unit Tests - Strategy Tests

| Test ID | Test Method | Description | Priority |
|---------|-------------|-------------|----------|
| OPT-S01 | `test_fefo_cost_balanced_basic` | Basic balanced selection | HIGH |
| OPT-S02 | `test_fefo_cost_balanced_custom_weights` | Custom weight configuration | HIGH |
| OPT-S03 | `test_minimize_cost_selection` | Cheapest batches first | HIGH |
| OPT-S04 | `test_minimize_cost_fefo_violations` | Detect FEFO violations | HIGH |
| OPT-S05 | `test_strict_fefo_selection` | Oldest batches first | HIGH |
| OPT-S06 | `test_strict_fefo_no_violations` | Zero FEFO violations | HIGH |
| OPT-S07 | `test_minimum_batches_selection` | Fewest batches used | MEDIUM |
| OPT-S08 | `test_strategy_enum_values` | Strategy enum coverage | LOW |

### 8.2 Unit Tests - Constraint Tests

| Test ID | Test Method | Description | Priority |
|---------|-------------|-------------|----------|
| OPT-C01 | `test_min_shelf_life_filter` | Exclude near-expiry batches | HIGH |
| OPT-C02 | `test_max_batches_limit` | Enforce batch count limit | HIGH |
| OPT-C03 | `test_warehouse_filter` | Warehouse restriction | MEDIUM |
| OPT-C04 | `test_exclude_batches` | Batch exclusion list | MEDIUM |
| OPT-C05 | `test_same_warehouse_constraint` | Single warehouse enforcement | MEDIUM |
| OPT-C06 | `test_max_cost_per_unit` | Cost ceiling enforcement | LOW |
| OPT-C07 | `test_multiple_constraints` | Combined constraints | HIGH |
| OPT-C08 | `test_constraint_violation_detection` | Violation reporting | HIGH |

### 8.3 Unit Tests - What-If Tests

| Test ID | Test Method | Description | Priority |
|---------|-------------|-------------|----------|
| OPT-W01 | `test_what_if_all_strategies` | Generate all 4 scenarios | HIGH |
| OPT-W02 | `test_what_if_comparison` | Strategy comparison metrics | HIGH |
| OPT-W03 | `test_what_if_recommendation` | Recommendation generation | MEDIUM |
| OPT-W04 | `test_what_if_cost_savings` | Savings calculation accuracy | HIGH |

### 8.4 Unit Tests - Edge Cases

| Test ID | Test Method | Description | Priority |
|---------|-------------|-------------|----------|
| OPT-E01 | `test_empty_batch_list` | Handle no batches | HIGH |
| OPT-E02 | `test_insufficient_stock` | Partial fulfillment | HIGH |
| OPT-E03 | `test_single_batch_available` | Only one batch | MEDIUM |
| OPT-E04 | `test_all_batches_expired` | All expired | HIGH |
| OPT-E05 | `test_zero_required_quantity` | Zero qty request | LOW |
| OPT-E06 | `test_negative_quantities` | Invalid qty handling | MEDIUM |
| OPT-E07 | `test_missing_expiry_dates` | Null expiry handling | MEDIUM |
| OPT-E08 | `test_missing_cost_data` | No price information | HIGH |

### 8.5 Integration Tests

| Test ID | Test Method | Description | Priority |
|---------|-------------|-------------|----------|
| OPT-I01 | `test_phase4_to_phase5_flow` | Phase 4 output processing | HIGH |
| OPT-I02 | `test_phase5_to_phase6_handoff` | Output format for Phase 6 | HIGH |
| OPT-I03 | `test_end_to_end_optimization` | Full workflow integration | HIGH |
| OPT-I04 | `test_cost_data_integration` | Use Phase 4 pricing | HIGH |
| OPT-I05 | `test_compliance_data_integration` | Use Phase 3 TDS status | MEDIUM |

### 8.6 Performance Tests

| Test ID | Test Method | Description | Priority |
|---------|-------------|-------------|----------|
| OPT-P01 | `test_large_batch_list` | 1000+ batches | LOW |
| OPT-P02 | `test_what_if_performance` | 4 strategies < 1s | LOW |

---

## 9. Implementation Checklist

- [x] Create `optimization_engine.py` with class structure
- [x] Implement `OptimizationStrategy` enum
- [x] Implement `_fefo_cost_balanced()` strategy
- [x] Implement `_minimize_cost()` strategy
- [x] Implement `_strict_fefo()` strategy
- [x] Implement `_minimum_batches()` strategy
- [x] Implement `_validate_constraints()` method
- [x] Implement `_generate_what_if_scenarios()` method
- [x] Implement `_count_fefo_violations()` method
- [x] Add `optimize_selection` action to process()
- [x] Add `generate_what_if` action to process()
- [x] Add unit tests (24+ tests)
- [x] Add integration tests (5 tests)
- [x] Update agent imports in `__init__.py`
- [x] Update documentation

---

## 10. Success Criteria

Implementation is complete when:

- [x] All 4 optimization strategies implemented and tested
- [x] FEFO violation detection is accurate
- [x] Constraint validation works for all constraint types
- [x] What-if scenarios generate correct comparisons
- [x] Phase 4 cost data is correctly integrated
- [x] Output format matches Phase 6 expectations
- [x] All unit tests pass (24+)
- [x] All integration tests pass (5)
- [x] Performance acceptable for 100+ batches

---

## 11. Error Handling

### 11.1 Custom Exceptions

```python
class OptimizationError(Exception):
    """Base exception for optimization errors."""
    pass

class InsufficientStockError(OptimizationError):
    """Raised when available stock cannot meet requirement."""
    def __init__(self, required, available, item_code=None):
        self.required = required
        self.available = available
        self.shortage = required - available
        self.item_code = item_code

class NoValidBatchesError(OptimizationError):
    """Raised when no batches meet constraints."""
    def __init__(self, item_code, constraint_failures):
        self.item_code = item_code
        self.constraint_failures = constraint_failures

class ConstraintViolationError(OptimizationError):
    """Raised when selection violates hard constraints."""
    def __init__(self, violations):
        self.violations = violations
```

---

**Document Version:** 1.0  
**Last Updated:** February 4, 2026  
**Status:** IMPLEMENTATION COMPLETE
