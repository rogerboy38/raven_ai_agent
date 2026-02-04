# Phase 5: Optimization Engine - Implementation Chat Log

## Session: February 4, 2026
**Participants:** Developer, Orchestrator Agent

---

### Session Start: Phase 5 Requirements Review

**Developer:** Phase 4 Cost Calculator is complete. Let's start Phase 5 - the Optimization Engine.

**Orchestrator:** Phase 5 is the OPTIMIZATION_ENGINE sub-agent responsible for:

1. Analyzing and optimizing formulation batch selections
2. Finding optimal combinations minimizing cost
3. Respecting constraints: FEFO, TDS compliance, availability
4. Providing what-if analysis and batch substitution recommendations

**CRITICAL:** Optimization must never compromise TDS compliance or use expired batches.

---

### Input/Output Contract Review

**Developer:** What data does Phase 5 receive and produce?

**Orchestrator:**

**Input from Phase 4:**
- `cost_data` with cost_breakdown and summary
- `available_batches` with item batches including fefo_rank, tds_compliant, unit_price
- `optimization_goals` array (e.g., minimize_cost, use_oldest_first)
- `constraints` object (max_batches_per_item, prefer_single_warehouse, enforce_fefo)

**Output to Phase 6:**
- `optimization_result` with status, original_cost, optimized_cost, savings
- `optimized_selection` array with selected batches per item
- `what_if_scenarios` for comparison
- `constraints_satisfied` status
- `recommendations` array

---

### Optimization Strategies Discussion

**Developer:** What strategies does Phase 5 support?

**Orchestrator:** Four main strategies:

| Strategy | Description | Use Case |
|----------|-------------|----------|
| FEFO_COST_BALANCED | Balance FEFO with cost | Default - best for production |
| MINIMIZE_COST | Pure cost minimization | When FEFO can be relaxed |
| STRICT_FEFO | Always oldest first | Regulatory requirements |
| SINGLE_BATCH_PREFERENCE | Prefer single batch | Reduce lot complexity |

---

### FEFO_COST_BALANCED Strategy Details

**Developer:** How does the default strategy work?

**Orchestrator:** The balanced approach:

1. Sort batches by FEFO rank first, then by price
2. Allocate from sorted list until quantity fulfilled
3. If multiple batches have same age, prefer cheaper one
4. Allow using newer batches only if significantly cheaper (>10%)

```python
sorted_batches = sorted(batches, key=lambda b: (b['fefo_rank'], b['unit_price']))
```

---

### What-If Scenario Generation

**Developer:** How are what-if scenarios generated?

**Orchestrator:** For each item, we calculate:

1. **STRICT_FEFO** - Cost using oldest batches first (no cost optimization)
2. **MINIMUM_COST** - Cost using cheapest batches first (may violate FEFO)
3. **SELECTED** - Cost of the actually selected strategy

This allows comparison and justification of selections.

---

### Integration with Phase Flow

**Developer:** How does Phase 5 integrate with the workflow?

**Orchestrator:**

```
BATCH_SELECTOR (Phase 2) -> batches_sorted_by_golden_fefo
                              |
                              v
TDS_COMPLIANCE (Phase 3) -> validates batches
                              |
                              v
COST_CALCULATOR (Phase 4) -> adds unit prices
                              |
                              v
OPTIMIZATION_ENGINE (Phase 5) -> optimizes selection
                              |
                              v
REPORT_GENERATOR (Phase 6) -> final output
```

---

### Test Requirements

**Developer:** What tests are needed for Phase 5?

**Orchestrator:** 10 test cases defined:

| Test ID | Test Case | Purpose |
|---------|-----------|----------|
| OPT-001 | FEFO allocation | Verify oldest-first selection |
| OPT-002 | Single batch preference | Test single batch when possible |
| OPT-003 | Cost tolerance check | Within tolerance selection |
| OPT-004 | Cost tolerance exceeded | Multi-batch when savings high |
| OPT-005 | Golden number priority | Golden batches first |
| OPT-006 | What-if FEFO only | FEFO scenario generation |
| OPT-007 | What-if lowest cost | Cost scenario generation |
| OPT-008 | Savings calculation | Accurate savings percentage |
| OPT-009 | Partial fulfillment | Handle shortages |
| OPT-010 | Constraint satisfaction | TDS/FEFO/qty checks |

---

### Error Handling

**Developer:** What error conditions should we handle?

**Orchestrator:**

| Error Condition | Handling |
|-----------------|----------|
| Empty batch list | Return PARTIAL status |
| All batches expired | Filter out, warn |
| Price data missing | Use fallback, warn |
| Negative quantities | Skip batch, log error |
| Division by zero | Check original_cost > 0 |

---

### Implementation Location

**Developer:** Where should the implementation go?

**Orchestrator:** Per specification:

```
raven_ai_agent/skills/formulation_orchestrator/agents/optimization_engine.py
```

Main function: `optimize_batch_selection(input_data, strategy='fefo_cost_balanced')`
# Phase 5: Optimization Engine

## Overview

This document outlines the Optimization Engine agent, which provides intelligent batch selection optimization for perishable inventory management. The engine implements multiple optimization strategies to balance cost efficiency, FEFO (First Expiry, First Out) compliance, and constraint satisfaction.

## Agent Architecture

### File Location
```
raven_ai_agent/skills/formulation_orchestrator/agents/optimization_engine.py
```

### Core Components

1. **OptimizationEngine Class** - Main orchestrator for batch optimization
2. **Strategy Functions** - Pluggable optimization algorithms
3. **Constraint Validator** - Ensures selections meet business rules
4. **What-If Generator** - Scenario comparison engine

---

## Optimization Strategies

### 1. FEFO Cost Balanced (Default)

Balances expiry priority with cost optimization.

```python
def fefo_cost_balanced(batches, required_qty, weights=None):
    """
    Hybrid strategy balancing FEFO compliance with cost optimization.
    
    Args:
        batches: List of available batch dictionaries
        required_qty: Target quantity needed
        weights: Optional dict with 'expiry' and 'cost' weights (default 0.6/0.4)
    
    Returns:
        dict: Selected batches with quantities and metrics
    """
    weights = weights or {'expiry': 0.6, 'cost': 0.4}
    
    # Calculate composite score for each batch
    scored_batches = []
    for batch in batches:
        days_to_expiry = (batch['expiry_date'] - today()).days
        expiry_score = 1 / max(days_to_expiry, 1)  # Higher = expires sooner
        cost_score = 1 / max(batch['unit_cost'], 0.01)  # Higher = cheaper
        
        composite = (weights['expiry'] * normalize(expiry_score) + 
                    weights['cost'] * normalize(cost_score))
        scored_batches.append((composite, batch))
    
    # Select batches by score until quantity met
    return select_by_score(scored_batches, required_qty)
```

### 2. Minimize Cost

Pure cost optimization - selects cheapest batches first.

```python
def minimize_cost(batches, required_qty):
    """
    Selects batches purely by lowest cost.
    Warning: May result in FEFO violations.
    
    Returns:
        dict: Selected batches optimized for cost
    """
    sorted_batches = sorted(batches, key=lambda b: b['unit_cost'])
    return select_sequential(sorted_batches, required_qty)
```

### 3. Strict FEFO

Pure FEFO compliance - always uses earliest expiring batches.

```python
def strict_fefo(batches, required_qty):
    """
    Strict First Expiry First Out selection.
    Guarantees no FEFO violations but may increase costs.
    
    Returns:
        dict: Selected batches in FEFO order
    """
    sorted_batches = sorted(batches, key=lambda b: b['expiry_date'])
    return select_sequential(sorted_batches, required_qty)
```

### 4. Minimum Batches

Minimizes number of batches used (reduces handling complexity).

```python
def minimum_batches(batches, required_qty):
    """
    Minimizes the number of different batches used.
    Useful for reducing picking complexity.
    
    Returns:
        dict: Selection using fewest possible batches
    """
    sorted_batches = sorted(batches, key=lambda b: b['available_qty'], reverse=True)
    return select_sequential(sorted_batches, required_qty)
```

---

## Main Function Interface

```python
def optimize_batch_selection(input_data, strategy='fefo_cost_balanced'):
    """
    Main entry point for batch optimization.
    
    Args:
        input_data: dict containing:
            - item_code: str - Item to optimize
            - required_qty: float - Quantity needed
            - warehouse: str - Source warehouse (optional)
            - min_remaining_shelf_life: int - Minimum days before expiry (optional)
            - exclude_batches: list - Batch IDs to exclude (optional)
            - cost_data: dict - Phase 4 cost analysis output (optional)
        
        strategy: str - One of:
            - 'fefo_cost_balanced' (default)
            - 'minimize_cost'
            - 'strict_fefo'
            - 'minimum_batches'
    
    Returns:
        dict: {
            'success': bool,
            'selected_batches': [
                {
                    'batch_id': str,
                    'item_code': str,
                    'quantity': float,
                    'unit_cost': float,
                    'total_cost': float,
                    'expiry_date': date,
                    'days_to_expiry': int,
                    'warehouse': str
                }
            ],
            'summary': {
                'total_quantity': float,
                'total_cost': float,
                'average_unit_cost': float,
                'batch_count': int,
                'earliest_expiry': date,
                'fefo_violations': int,
                'strategy_used': str
            },
            'warnings': list,
            'alternatives': dict  # What-if scenarios
        }
    """
```

---

## Constraint Satisfaction

### Supported Constraints

| Constraint | Description | Default |
|------------|-------------|----------|
| `min_remaining_shelf_life` | Minimum days before expiry | 7 days |
| `max_batches` | Maximum number of batches to use | None |
| `warehouse_filter` | Restrict to specific warehouse(s) | None |
| `exclude_batches` | Batch IDs to exclude | [] |
| `require_same_warehouse` | All from single warehouse | False |
| `max_cost_per_unit` | Upper cost limit | None |

### Constraint Validation

```python
def validate_constraints(selection, constraints):
    """
    Validates a batch selection against business constraints.
    
    Returns:
        dict: {
            'valid': bool,
            'violations': [
                {
                    'constraint': str,
                    'message': str,
                    'severity': 'error' | 'warning'
                }
            ]
        }
    """
```

---

## What-If Scenario Generator

### Purpose

Generates alternative scenarios to help users make informed decisions by comparing different optimization strategies.

### Implementation

```python
def generate_what_if_scenarios(input_data):
    """
    Generates comparison of all strategies for given input.
    
    Returns:
        dict: {
            'scenarios': {
                'fefo_cost_balanced': {...},
                'minimize_cost': {...},
                'strict_fefo': {...},
                'minimum_batches': {...}
            },
            'comparison': {
                'lowest_cost': str,  # strategy name
                'best_fefo': str,
                'fewest_batches': str,
                'recommended': str,
                'recommendation_reason': str
            }
        }
    """
```

### Example Output

```json
{
  "scenarios": {
    "fefo_cost_balanced": {
      "total_cost": 1250.00,
      "batch_count": 3,
      "fefo_violations": 0,
      "earliest_expiry": "2025-02-15"
    },
    "minimize_cost": {
      "total_cost": 1180.00,
      "batch_count": 4,
      "fefo_violations": 2,
      "earliest_expiry": "2025-03-01"
    },
    "strict_fefo": {
      "total_cost": 1320.00,
      "batch_count": 3,
      "fefo_violations": 0,
      "earliest_expiry": "2025-02-10"
    }
  },
  "comparison": {
    "lowest_cost": "minimize_cost",
    "best_fefo": "strict_fefo",
    "recommended": "fefo_cost_balanced",
    "recommendation_reason": "Best balance of cost savings (5.3% vs strict_fefo) with zero FEFO violations"
  }
}
```

---

## Integration with Phase 4

### Using Cost Data

The optimization engine can leverage Phase 4 cost analysis for enhanced decision-making:

```python
def optimize_with_cost_context(input_data, cost_analysis):
    """
    Enhanced optimization using Phase 4 cost data.
    
    Uses cost trends, valuation methods, and variance analysis
    to make more informed batch selections.
    """
    # Extract relevant cost insights
    valuation_method = cost_analysis.get('valuation_method', 'moving_average')
    cost_trend = cost_analysis.get('trend', {}).get('direction', 'stable')
    
    # Adjust strategy weights based on cost trends
    if cost_trend == 'increasing':
        # Favor older (cheaper) inventory when costs are rising
        weights = {'expiry': 0.5, 'cost': 0.5}
    elif cost_trend == 'decreasing':
        # Favor FEFO when costs are dropping (newer stock is cheaper)
        weights = {'expiry': 0.7, 'cost': 0.3}
    else:
        weights = {'expiry': 0.6, 'cost': 0.4}
    
    return optimize_batch_selection(
        input_data, 
        strategy='fefo_cost_balanced',
        weights=weights
    )
```

---

## Unit Tests

### Test Cases (OPT-001 through OPT-010)

| Test ID | Description | Input | Expected |
|---------|-------------|-------|----------|
| OPT-001 | Basic FEFO selection | 3 batches, need 100 | Earliest expiry first |
| OPT-002 | Cost minimization | 3 batches, varying costs | Cheapest selected |
| OPT-003 | Insufficient stock | Need 1000, have 500 | Partial + warning |
| OPT-004 | Shelf life filter | min_shelf_life=30 | Excludes near-expiry |
| OPT-005 | Multi-warehouse | 2 warehouses | Respects filter |
| OPT-006 | FEFO violation detection | Mixed selection | Correct violation count |
| OPT-007 | What-if generation | Standard input | All 4 scenarios |
| OPT-008 | Constraint validation | max_batches=2 | Enforces limit |
| OPT-009 | Empty batch list | No stock | Graceful error |
| OPT-010 | Cost integration | With Phase 4 data | Adjusted weights |

---

## Error Handling

```python
class OptimizationError(Exception):
    """Base exception for optimization errors."""
    pass

class InsufficientStockError(OptimizationError):
    """Raised when available stock cannot meet requirement."""
    def __init__(self, required, available):
        self.required = required
        self.available = available
        self.shortage = required - available

class NoValidBatchesError(OptimizationError):
    """Raised when no batches meet constraints."""
    pass

class ConstraintViolationError(OptimizationError):
    """Raised when selection violates hard constraints."""
    def __init__(self, violations):
        self.violations = violations
```

---

## Session Summary

**Status:** Ready for Implementation

**Key Components:**
- Four optimization strategies implemented
- What-if scenario generation
- Constraint satisfaction checking
- Integration with Phase 4 cost data

**Next Steps:**
1. Implement `optimization_engine.py` agent
2. Add strategy functions (fefo_cost_balanced, minimize_cost, strict_fefo)
3. Implement what-if scenario generator
4. Add unit tests (OPT-001 through OPT-010)
5. Test integration with Phase 4 output

---

*Document created as part of the Raven AI Agent project formulation process.*---

### Session Summary

**Status:** Ready for Implementation

**Key Components:**
- Four optimization strategies implemented
- What-if scenario generation
- Constraint satisfaction checking
- Integration with Phase 4 cost data

**Next Steps:**
1. Implement `optimization_engine.py` agent
2. Add strategy functions (fefo_cost_balanced, minimize_cost, strict_fefo)
3. Implement what-if scenario generator
4. Add unit tests (OPT-001 through OPT-010)
5. Test integration with Phase 4 output

---

**Document Version:** 1.0
**Date:** February 4, 2026
**Status:** READY FOR IMPLEMENTATION
