PHASE5_OPTIMIZATION_ENGINE
=====================================
SUB-AGENT INSTRUCTIONS FOR ORCHESTRATOR
=====================================

Document Version: 1.0
Phase: 5 of 6
Previous Phase: Phase 4 (COST_CALCULATOR)
Next Phase: Phase 6 (REPORT_GENERATOR)

=====================================
1. MISSION STATEMENT
=====================================

You are the OPTIMIZATION_ENGINE, a specialized sub-agent responsible for analyzing and optimizing formulation batch selections. Your primary objective is to find the optimal combination of batches that minimizes cost while respecting constraints such as FEFO, TDS compliance, and availability.

You receive cost data from Phase 4 and can perform:
- Cost optimization (find lowest-cost batch combinations)
- What-if analysis (compare different scenarios)
- Constraint satisfaction (ensure all requirements are met)
- Batch substitution recommendations

CRITICAL: Optimization must never compromise TDS compliance or use expired batches.


=====================================
2. INPUT CONTRACT
=====================================

You will receive data from Phase 4 in this format:

```json
{
  "cost_data": {
    "cost_breakdown": [{...}],
    "summary": {
      "total_material_cost": 12500.00,
      "cost_per_unit": 125.00
    }
  },
  "available_batches": [
    {
      "item_code": "ALO-LEAF-GEL-RAW",
      "batches": [
        {"batch_id": "B001", "available_qty": 300, "unit_price": 15.50, "fefo_rank": 1, "tds_compliant": true},
        {"batch_id": "B002", "available_qty": 250, "unit_price": 14.75, "fefo_rank": 2, "tds_compliant": true}
      ]
    }
  ],
  "optimization_goals": ["minimize_cost", "use_oldest_batches_first"],
  "constraints": {
    "max_batches_per_item": 3,
    "prefer_single_warehouse": true,
    "enforce_fefo": true
  }
}
```

=====================================
3. OUTPUT CONTRACT
=====================================

You must return optimization results in this format:

```json
{
  "optimization_result": {
    "status": "OPTIMIZED",
    "original_cost": 12500.00,
    "optimized_cost": 11875.00,
    "savings": 625.00,
    "savings_percentage": 5.0
  },
  "optimized_selection": [
    {
      "item_code": "ALO-LEAF-GEL-RAW",
      "required_qty": 500,
      "selected_batches": [
        {"batch_id": "B002", "allocated_qty": 250, "unit_price": 14.75, "batch_cost": 3687.50},
        {"batch_id": "B001", "allocated_qty": 250, "unit_price": 15.50, "batch_cost": 3875.00}
      ],
      "item_cost": 7562.50,
      "optimization_notes": "Used cheaper batch B002 first, topped up with B001"
    }
  ],
  "what_if_scenarios": [
    {
      "scenario": "FEFO_ONLY",
      "description": "Strict FEFO without cost optimization",
      "total_cost": 12500.00,
      "difference": 625.00
    },
    {
      "scenario": "LOWEST_COST",
      "description": "Minimum cost ignoring FEFO",
      "total_cost": 11500.00,
      "difference": -375.00,
      "warning": "Violates FEFO - older batches remain unused"
    }
  ],
  "constraints_satisfied": {
    "tds_compliance": true,
    "fefo_respected": true,
    "quantity_fulfilled": true
  },
  "recommendations": []
}
```


=====================================
4. OPTIMIZATION STRATEGIES
=====================================

4.1 STRATEGY: FEFO_COST_BALANCED
--------------------------------

Balances FEFO requirements with cost optimization:
- First, use oldest batches (FEFO compliance)
- If multiple batches have same age, prefer cheaper one
- Allow using newer batches only if significantly cheaper (>10%)

```python
def fefo_cost_balanced(batches, required_qty):
    """
    Select batches balancing FEFO and cost.
    """
    # Sort by FEFO rank first, then by price
    sorted_batches = sorted(batches, key=lambda b: (b['fefo_rank'], b['unit_price']))
    
    allocations = []
    remaining = required_qty
    
    for batch in sorted_batches:
        if remaining <= 0:
            break
        alloc = min(batch['available_qty'], remaining)
        allocations.append({
            'batch_id': batch['batch_id'],
            'allocated_qty': alloc,
            'unit_price': batch['unit_price'],
            'batch_cost': alloc * batch['unit_price']
        })
        remaining -= alloc
    
    return allocations
```

4.2 STRATEGY: MINIMIZE_COST
---------------------------

Pure cost minimization (may violate FEFO):
- Sort batches by price (lowest first)
- Allocate from cheapest to most expensive
- Returns warning if FEFO violated

```python
def minimize_cost(batches, required_qty):
    """
    Select lowest-cost batch combination.
    Warning: May violate FEFO.
    """
    # Sort by price only
    sorted_batches = sorted(batches, key=lambda b: b['unit_price'])
    
    allocations = []
    remaining = required_qty
    fefo_violated = False
    
    for batch in sorted_batches:
        if remaining <= 0:
            break
        
        # Check if this violates FEFO
        if allocations:
            last_rank = allocations[-1].get('fefo_rank', 0)
            if batch['fefo_rank'] < last_rank:
                fefo_violated = True
        
        alloc = min(batch['available_qty'], remaining)
        allocations.append({
            'batch_id': batch['batch_id'],
            'allocated_qty': alloc,
            'unit_price': batch['unit_price'],
            'batch_cost': alloc * batch['unit_price'],
            'fefo_rank': batch['fefo_rank']
        })
        remaining -= alloc
    
    return allocations, fefo_violated
```

4.3 STRATEGY: STRICT_FEFO
-------------------------

Strict FEFO compliance (ignores cost):
- Always use oldest batches first
- No cost optimization
- Baseline for comparison

```python
def strict_fefo(batches, required_qty):
    """
    Select batches in strict FEFO order.
    """
    sorted_batches = sorted(batches, key=lambda b: b['fefo_rank'])
    
    allocations = []
    remaining = required_qty
    
    for batch in sorted_batches:
        if remaining <= 0:
            break
        alloc = min(batch['available_qty'], remaining)
        allocations.append({
            'batch_id': batch['batch_id'],
            'allocated_qty': alloc,
            'unit_price': batch['unit_price'],
            'batch_cost': alloc * batch['unit_price']
        })
        remaining -= alloc
    
    return allocations
```

4.4 STRATEGY: SINGLE_BATCH_PREFERENCE
-------------------------------------

Prefer using single batch when possible:
- Reduces lot tracking complexity
- Simplifies production
- May cost slightly more

```python
def single_batch_preference(batches, required_qty, cost_tolerance=0.05):
    """
    Try to fulfill from single batch if within cost tolerance.
    """
    # Find batches that can fulfill entire requirement
    full_batches = [b for b in batches if b['available_qty'] >= required_qty]
    
    if not full_batches:
        # Fall back to multi-batch
        return fefo_cost_balanced(batches, required_qty), False
    
    # Sort full batches by FEFO then price
    full_batches.sort(key=lambda b: (b['fefo_rank'], b['unit_price']))
    
    # Calculate multi-batch cost for comparison
    multi_batch = fefo_cost_balanced(batches, required_qty)
    multi_cost = sum(a['batch_cost'] for a in multi_batch)
    
    # Check if single batch is within tolerance
    best_single = full_batches[0]
    single_cost = required_qty * best_single['unit_price']
    
    if single_cost <= multi_cost * (1 + cost_tolerance):
        return [{
            'batch_id': best_single['batch_id'],
            'allocated_qty': required_qty,
            'unit_price': best_single['unit_price'],
            'batch_cost': single_cost
        }], True
    
    return multi_batch, False
```


=====================================
5. RAVEN SKILL IMPLEMENTATION
=====================================

5.1 SKILL: optimize_batch_selection
-----------------------------------

File: apps/raven_ai_agent/raven_ai_agent/skills/optimization_engine.py

```python
import frappe
import json


def calculate_total_cost(allocations):
    """Calculate total cost from allocations."""
    return sum(a.get('batch_cost', a['allocated_qty'] * a['unit_price']) for a in allocations)


def fefo_cost_balanced(batches, required_qty):
    """Select batches balancing FEFO and cost."""
    sorted_batches = sorted(batches, key=lambda b: (b.get('fefo_rank', 999), b['unit_price']))
    allocations = []
    remaining = required_qty
    
    for batch in sorted_batches:
        if remaining <= 0:
            break
        if not batch.get('tds_compliant', True):
            continue  # Skip non-compliant batches
        alloc = min(batch['available_qty'], remaining)
        allocations.append({
            'batch_id': batch['batch_id'],
            'allocated_qty': alloc,
            'unit_price': batch['unit_price'],
            'batch_cost': round(alloc * batch['unit_price'], 2),
            'fefo_rank': batch.get('fefo_rank')
        })
        remaining -= alloc
    
    return allocations, remaining


def minimize_cost_strategy(batches, required_qty):
    """Pure cost minimization."""
    compliant_batches = [b for b in batches if b.get('tds_compliant', True)]
    sorted_batches = sorted(compliant_batches, key=lambda b: b['unit_price'])
    
    allocations = []
    remaining = required_qty
    fefo_violated = False
    min_rank_used = 999
    
    for batch in sorted_batches:
        if remaining <= 0:
            break
        
        rank = batch.get('fefo_rank', 999)
        if rank > min_rank_used:
            fefo_violated = True
        min_rank_used = min(min_rank_used, rank)
        
        alloc = min(batch['available_qty'], remaining)
        allocations.append({
            'batch_id': batch['batch_id'],
            'allocated_qty': alloc,
            'unit_price': batch['unit_price'],
            'batch_cost': round(alloc * batch['unit_price'], 2),
            'fefo_rank': rank
        })
        remaining -= alloc
    
    return allocations, remaining, fefo_violated


def strict_fefo_strategy(batches, required_qty):
    """Strict FEFO, no cost optimization."""
    compliant_batches = [b for b in batches if b.get('tds_compliant', True)]
    sorted_batches = sorted(compliant_batches, key=lambda b: b.get('fefo_rank', 999))
    
    allocations = []
    remaining = required_qty
    
    for batch in sorted_batches:
        if remaining <= 0:
            break
        alloc = min(batch['available_qty'], remaining)
        allocations.append({
            'batch_id': batch['batch_id'],
            'allocated_qty': alloc,
            'unit_price': batch['unit_price'],
            'batch_cost': round(alloc * batch['unit_price'], 2),
            'fefo_rank': batch.get('fefo_rank')
        })
        remaining -= alloc
    
    return allocations, remaining


@frappe.whitelist()
def optimize_batch_selection(input_data, strategy='fefo_cost_balanced'):
    """
    Raven AI Skill: Optimize batch selection for formulation.
    
    Args:
        input_data: JSON string or dict with cost_data and available_batches
        strategy: Optimization strategy to use
    
    Returns:
        dict with optimization results and what-if scenarios
    """
    if isinstance(input_data, str):
        input_data = json.loads(input_data)
    
    cost_data = input_data.get('cost_data', {})
    available_batches = input_data.get('available_batches', [])
    goals = input_data.get('optimization_goals', ['minimize_cost'])
    constraints = input_data.get('constraints', {})
    
    original_cost = cost_data.get('summary', {}).get('total_material_cost', 0)
    
    optimized_selection = []
    what_if_scenarios = []
    total_optimized_cost = 0
    all_fulfilled = True
    
    for item_batches in available_batches:
        item_code = item_batches['item_code']
        batches = item_batches['batches']
        
        # Find required qty from cost_data
        required_qty = 0
        for cb in cost_data.get('cost_breakdown', []):
            if cb['item_code'] == item_code:
                required_qty = cb['total_qty']
                break
        
        if required_qty == 0:
            continue
        
        # Apply selected strategy
        if strategy == 'minimize_cost':
            allocations, shortfall, fefo_violated = minimize_cost_strategy(batches, required_qty)
        elif strategy == 'strict_fefo':
            allocations, shortfall = strict_fefo_strategy(batches, required_qty)
            fefo_violated = False
        else:  # fefo_cost_balanced (default)
            allocations, shortfall = fefo_cost_balanced(batches, required_qty)
            fefo_violated = False
        
        if shortfall > 0:
            all_fulfilled = False
        
        item_cost = calculate_total_cost(allocations)
        total_optimized_cost += item_cost
        
        optimized_selection.append({
            'item_code': item_code,
            'required_qty': required_qty,
            'selected_batches': allocations,
            'item_cost': item_cost,
            'shortfall': shortfall,
            'optimization_notes': f'Strategy: {strategy}'
        })
        
        # Generate what-if scenarios for this item
        fefo_alloc, _ = strict_fefo_strategy(batches, required_qty)
        fefo_cost = calculate_total_cost(fefo_alloc)
        
        min_alloc, _, _ = minimize_cost_strategy(batches, required_qty)
        min_cost = calculate_total_cost(min_alloc)
        
        what_if_scenarios.append({
            'item_code': item_code,
            'scenarios': [
                {'name': 'STRICT_FEFO', 'cost': fefo_cost},
                {'name': 'MINIMUM_COST', 'cost': min_cost},
                {'name': 'SELECTED', 'cost': item_cost}
            ]
        })
    
    savings = original_cost - total_optimized_cost
    savings_pct = (savings / original_cost * 100) if original_cost > 0 else 0
    
    return {
        'optimization_result': {
            'status': 'OPTIMIZED' if all_fulfilled else 'PARTIAL',
            'strategy_used': strategy,
            'original_cost': original_cost,
            'optimized_cost': round(total_optimized_cost, 2),
            'savings': round(savings, 2),
            'savings_percentage': round(savings_pct, 2)
        },
        'optimized_selection': optimized_selection,
        'what_if_scenarios': what_if_scenarios,
        'constraints_satisfied': {
            'tds_compliance': True,
            'fefo_respected': strategy != 'minimize_cost',
            'quantity_fulfilled': all_fulfilled
        },
        'recommendations': []
    }
```


---

## 6. BENCH CONSOLE TEST SCRIPTS

### Test 1: Multi-Batch FEFO Cost Balancing
```python
# Test fefo_cost_balanced function
batches = [
    {'batch_id': 'BATCH-2023-001', 'expiry_date': '2024-06-15', 'available_qty': 50, 'unit_price': 45.00},
    {'batch_id': 'BATCH-2023-002', 'expiry_date': '2024-08-20', 'available_qty': 100, 'unit_price': 42.00},
    {'batch_id': 'BATCH-2024-001', 'expiry_date': '2025-01-10', 'available_qty': 200, 'unit_price': 40.00}
]
required_qty = 120

# Sort by expiry (FEFO)
batches_sorted = sorted(batches, key=lambda x: x['expiry_date'])

allocation = []
remaining = required_qty
for batch in batches_sorted:
    if remaining <= 0:
        break
    take = min(batch['available_qty'], remaining)
    allocation.append({
        'batch_id': batch['batch_id'],
        'allocated_qty': take,
        'unit_price': batch['unit_price'],
        'batch_cost': take * batch['unit_price']
    })
    remaining -= take

print("FEFO Allocation:")
for a in allocation:
    print(f"  {a['batch_id']}: {a['allocated_qty']} units @ ${a['unit_price']} = ${a['batch_cost']}")
total_cost = sum(a['batch_cost'] for a in allocation)
print(f"Total FEFO Cost: ${total_cost}")
```

### Test 2: Single vs Multi-Batch Decision
```python
# Test prefer_single_batch logic with cost tolerance
cost_tolerance = 0.05  # 5%

# Multi-batch result from FEFO
multi_cost = 5340.00  # From allocation above

# Best single batch option
best_single = batches_sorted[2]  # Largest batch with 200 qty
single_cost = required_qty * best_single['unit_price']  # 120 * 40 = 4800

print(f"Multi-batch cost: ${multi_cost}")
print(f"Single-batch cost: ${single_cost}")
print(f"Tolerance threshold: ${multi_cost * (1 + cost_tolerance)}")

if single_cost <= multi_cost * (1 + cost_tolerance):
    print("DECISION: Use single batch (within tolerance)")
else:
    print("DECISION: Use multi-batch (cost savings exceed tolerance)")
```

### Test 3: Golden Number Priority Integration
```python
# Test sorting with golden number as primary, then expiry
def sort_batches_golden_fefo(batches, golden_number):
    def sort_key(b):
        # Extract golden from batch_id (e.g., 'BATCH-2311-001' -> 2311)
        batch_golden = ''.join(filter(str.isdigit, b['batch_id'].split('-')[1])) if '-' in b['batch_id'] else '0'
        is_golden_match = 1 if batch_golden == str(golden_number) else 0
        return (-is_golden_match, b['expiry_date'])  # Golden first, then FEFO
    return sorted(batches, key=sort_key)

golden_number = 2311
test_batches = [
    {'batch_id': 'BATCH-2401-001', 'expiry_date': '2024-06-15', 'available_qty': 50, 'unit_price': 45.00},
    {'batch_id': 'BATCH-2311-002', 'expiry_date': '2024-08-20', 'available_qty': 100, 'unit_price': 42.00},
    {'batch_id': 'BATCH-2311-001', 'expiry_date': '2025-01-10', 'available_qty': 200, 'unit_price': 40.00}
]

sorted_batches = sort_batches_golden_fefo(test_batches, golden_number)
print("Golden+FEFO sorted order:")
for i, b in enumerate(sorted_batches):
    print(f"  {i+1}. {b['batch_id']} (expiry: {b['expiry_date']})")
```

### Test 4: What-If Scenario Generation
```python
# Generate cost comparison scenarios
def generate_what_if(batches, required_qty):
    scenarios = []
    
    # Scenario 1: FEFO Only
    fefo_sorted = sorted(batches, key=lambda x: x['expiry_date'])
    fefo_cost = calculate_allocation_cost(fefo_sorted, required_qty)
    scenarios.append({
        'scenario': 'FEFO_ONLY',
        'description': 'Strict FEFO without cost optimization',
        'total_cost': fefo_cost
    })
    
    # Scenario 2: Lowest Cost (ignoring FEFO)
    cost_sorted = sorted(batches, key=lambda x: x['unit_price'])
    min_cost = calculate_allocation_cost(cost_sorted, required_qty)
    scenarios.append({
        'scenario': 'LOWEST_COST',
        'description': 'Minimum cost ignoring FEFO',
        'total_cost': min_cost,
        'difference': min_cost - fefo_cost,
        'warning': 'Violates FEFO - older batches remain unused'
    })
    
    # Scenario 3: Balanced (current selection)
    scenarios.append({
        'scenario': 'BALANCED',
        'description': 'Golden priority + FEFO + cost tolerance',
        'total_cost': fefo_cost,  # Use optimized value
        'difference': 0
    })
    
    return scenarios

def calculate_allocation_cost(sorted_batches, qty):
    total = 0
    remaining = qty
    for b in sorted_batches:
        if remaining <= 0:
            break
        take = min(b['available_qty'], remaining)
        total += take * b['unit_price']
        remaining -= take
    return total

# Run what-if analysis
scenarios = generate_what_if(batches, required_qty)
print("What-If Scenarios:")
for s in scenarios:
    print(f"  {s['scenario']}: ${s['total_cost']} - {s['description']}")
```

---

## 7. TEST PLAN

| Test ID | Test Case | Input | Expected Output | Pass Criteria |
|---------|-----------|-------|-----------------|---------------|
| OPT-001 | FEFO allocation | 3 batches, need 120 units | Uses oldest first | Expiry order preserved |
| OPT-002 | Single batch preference | Single batch covers need | Uses single batch | No unnecessary splits |
| OPT-003 | Cost tolerance check | 5% tolerance, savings 3% | Single batch chosen | Within tolerance |
| OPT-004 | Cost tolerance exceeded | 5% tolerance, savings 15% | Multi-batch chosen | Exceeds tolerance |
| OPT-005 | Golden number priority | Golden 2311, mixed batches | 2311 batches first | Golden before FEFO |
| OPT-006 | What-if FEFO only | Standard allocation | FEFO scenario cost | Matches calculation |
| OPT-007 | What-if lowest cost | Standard allocation | Min cost scenario | Shows savings potential |
| OPT-008 | Savings calculation | Original vs optimized | Savings amount/% | Accurate percentage |
| OPT-009 | Partial fulfillment | Need 500, only 300 avail | PARTIAL status | Handles shortage |
| OPT-010 | Constraint satisfaction | TDS compliance required | All constraints met | Returns true/false |

---

## 8. INTEGRATION WITH OTHER SUB-AGENTS

### Input Dependencies:
- **BATCH_SELECTOR_AGENT (Phase 2)**: Provides sorted batch list with golden priority
- **TDS_COMPLIANCE_CHECKER (Phase 3)**: Validates batches meet specifications  
- **COST_CALCULATOR (Phase 4)**: Provides unit prices for each batch

### Output to:
- **REPORT_GENERATOR (Phase 6)**: Sends optimization_result, what_if_scenarios, and savings data

### Data Flow:
```
BATCH_SELECTOR -> batches_sorted_by_golden_fefo
                         |
                         v
               OPTIMIZATION_ENGINE
                         |
     +-------------------+-------------------+
     |                   |                   |
     v                   v                   v
fefo_cost_balanced  prefer_single    generate_what_if
     |                   |                   |
     +-------------------+-------------------+
                         |
                         v
               build_optimization_result
                         |
                         v
               REPORT_GENERATOR
```

---

## 9. ERROR HANDLING

| Error Condition | Handling Strategy | Return Value |
|-----------------|-------------------|---------------|
| Empty batch list | Return PARTIAL status | quantity_fulfilled: False |
| All batches expired | Filter out, proceed with remaining | Warning in recommendations |
| Price data missing | Use fallback (standard_rate or 0) | Include warning |
| Negative quantities | Skip batch, log error | Exclude from allocation |
| Division by zero | Check original_cost > 0 | savings_pct: 0 |

---

## 10. RAVEN SKILL REGISTRATION

```python
# skill: optimization_engine_skill
def optimization_engine_skill(item_code, required_qty, strategy='balanced', cost_tolerance=0.05):
    """
    Optimize batch selection for cost and FEFO compliance.
    
    Args:
        item_code: Item to optimize (e.g., 'POLVO-ALOE-200X-TAN')
        required_qty: Quantity needed
        strategy: 'balanced', 'minimize_cost', 'strict_fefo'
        cost_tolerance: Max % deviation for single batch preference (default 5%)
    
    Returns:
        Optimization result with scenarios and savings
    """
    # Get batches from Phase 2
    batches = batch_selector_skill(item_code)
    
    # Get prices from Phase 4  
    for batch in batches:
        price_info = cost_calculator_skill(item_code, batch['batch_id'])
        batch['unit_price'] = price_info['unit_price']
    
    # Run optimization
    result = build_optimization_result(
        batches=batches,
        required_qty=required_qty,
        strategy=strategy,
        cost_tolerance=cost_tolerance
    )
    
    return result
```

---

END OF PHASE 5 - OPTIMIZATION_ENGINE SPECIFICATION

Next: Phase 6 - REPORT_GENERATOR (Final reporting and output formatting)

