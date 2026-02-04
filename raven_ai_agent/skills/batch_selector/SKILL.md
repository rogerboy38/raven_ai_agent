# BATCH_SELECTOR_AGENT Skill

## Overview

Phase 2 skill for the Formulation Orchestration Project. Provides intelligent batch selection for raw materials using FEFO (First Expired, First Out) logic.

**Version:** 1.0.0
**Author:** Raven AI Agent
**Date:** 2026-02-04

## Features

- Universal golden number parsing (YYWWDS and PPPPFFYYPS formats)
- FEFO sorting with configurable fallbacks
- Cost-based optimization mode
- Expired batch handling with near-expiry warnings
- Weighted average calculation for batch blending
- TDS compliance validation

## Installation

This skill is part of the `raven_ai_agent` package.

```python
from raven_ai_agent.skills.batch_selector import (
    select_batches_for_formulation,
    select_optimal_batches,
    parse_golden_number_universal
)
```

## API Reference

### Main Functions

#### `select_batches_for_formulation(required_items, warehouse=None, optimization_mode='fefo')`

Main Raven AI skill entry point. Frappe whitelist function.

**Args:**
- `required_items`: List of dicts with `item_code` and `required_qty`
- `warehouse`: Optional warehouse filter
- `optimization_mode`: 'fefo' (default) or 'cost'

**Returns:**
```python
{
    'batch_selections': [...],
    'overall_status': 'ALL_ITEMS_FULFILLED' | 'SOME_ITEMS_SHORT'
}
```

#### `select_optimal_batches(item_code, required_qty, ...)`

Select optimal batches for a single item.

**Args:**
- `item_code`: Item to select batches for
- `required_qty`: Quantity needed
- `warehouse`: Optional warehouse filter
- `optimization_mode`: 'fefo' or 'cost'
- `include_expired`: Include expired batches (default: False)
- `near_expiry_days`: Days threshold for warning (default: 30)

### Parser Functions

#### `parse_golden_number_universal(item_code)`

Parse golden number from item code, supporting both formats.

**Formats:**
- YYWWDS: `ALOE-200X-PWD-250311` -> year=25, week=03, day=1, seq=1
- PPPPFFYYPS: `ITEM_0617027231` -> product=0617, folio=27, year=23

### Optimizer Functions

#### `sort_batches_fefo(batches)`

Sort batches using FEFO logic with golden number priority.

#### `sort_batches_cost(batches, ascending=True)`

Sort batches by cost.

#### `filter_batches_by_expiry(batches, include_expired=False, near_expiry_days=30)`

Filter and flag batches based on expiry status.

## Usage Examples

### Basic Selection

```python
from raven_ai_agent.skills.batch_selector import select_batches_for_formulation

result = select_batches_for_formulation(
    required_items=[
        {'item_code': 'ALO-LEAF-GEL-RAW', 'required_qty': 500},
        {'item_code': 'MALTO-PWD-001', 'required_qty': 50}
    ],
    warehouse='FG to Sell Warehouse - AMB-W',
    optimization_mode='fefo'
)
```

### Cost Optimization

```python
result = select_batches_for_formulation(
    required_items=[{'item_code': 'ALOE-200X-PWD', 'required_qty': 100}],
    optimization_mode='cost'
)
```

### Including Expired Batches

```python
from raven_ai_agent.skills.batch_selector import select_optimal_batches

result = select_optimal_batches(
    item_code='ALO-LEAF-GEL-RAW',
    required_qty=500,
    include_expired=True,
    near_expiry_days=60
)
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `DEFAULT_WAREHOUSE` | 'FG to Sell Warehouse - AMB-W' | Default warehouse for queries |
| `DEFAULT_NEAR_EXPIRY_DAYS` | 30 | Days threshold for near-expiry warning |
| `DEFAULT_OPTIMIZATION_MODE` | 'fefo' | Default optimization mode |

## Integration

### Phase 1 Input

Receives output from FORMULATION_READER_AGENT:

```python
{
    'formulation_request': {...},
    'required_items': [
        {'item_code': '...', 'required_qty': 500}
    ]
}
```

### Phase 3 Output

Sends to TDS_COMPLIANCE_CHECKER:

```python
{
    'batch_selections': [
        {
            'item_code': '...',
            'selected_batches': [...],
            'fulfillment_status': 'COMPLETE'
        }
    ]
}
```

## Files

| File | Description |
|------|-------------|
| `__init__.py` | Module exports and configuration |
| `parsers.py` | Golden number parsing functions |
| `optimizer.py` | FEFO/cost sorting and filtering |
| `selector.py` | Core batch selection logic |
