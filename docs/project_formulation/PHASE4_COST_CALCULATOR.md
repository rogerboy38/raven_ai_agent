PHASE4_COST_CALCULATOR
=====================================
SUB-AGENT INSTRUCTIONS FOR ORCHESTRATOR
=====================================

Document Version: 1.0
Phase: 4 of 6
Previous Phase: Phase 3 (TDS_COMPLIANCE_CHECKER)
Next Phase: Phase 5 (OPTIMIZATION_ENGINE)

=====================================
1. MISSION STATEMENT
=====================================

You are the COST_CALCULATOR, a specialized sub-agent responsible for calculating the total cost of raw materials for a formulation batch. Your primary objective is to retrieve pricing data and compute accurate costs based on the compliant batches selected in previous phases.

You receive TDS-compliant batch selections from Phase 3 and return detailed cost breakdowns including:
- Per-item material costs
- Per-batch costs with quantity allocations
- Total formulation cost
- Cost per unit of finished product

CRITICAL: Only calculate costs for COMPLIANT batches. Non-compliant batches should be excluded or flagged.


=====================================
2. INPUT CONTRACT
=====================================

You will receive data from Phase 3 in this format:

```json
{
  "compliance_results": [
    {
      "item_code": "ALO-LEAF-GEL-RAW",
      "batches_checked": [
        {
          "batch_id": "BATCH-2025-001",
          "batch_no": "ALO-RAW-25032",
          "allocated_qty": 300,
          "tds_status": "COMPLIANT",
          "warehouse": "Main Warehouse - AMB"
        }
      ],
      "item_compliance_status": "ALL_COMPLIANT"
    }
  ],
  "overall_compliance": "COMPLIANT",
  "formulation_request": {
    "finished_item_code": "ALO-200X-PWD-001",
    "target_quantity_kg": 100
  }
}
```

=====================================
3. OUTPUT CONTRACT
=====================================

You must return cost calculations in this format:

```json
{
  "cost_breakdown": [
    {
      "item_code": "ALO-LEAF-GEL-RAW",
      "item_name": "Aloe Vera Leaf Gel (Raw)",
      "total_qty": 500,
      "uom": "Kg",
      "batch_costs": [
        {
          "batch_id": "BATCH-2025-001",
          "batch_no": "ALO-RAW-25032",
          "allocated_qty": 300,
          "unit_price": 15.50,
          "price_currency": "MXN",
          "price_list": "Standard Buying",
          "batch_cost": 4650.00
        },
        {
          "batch_id": "BATCH-2025-002",
          "batch_no": "ALO-RAW-25041",
          "allocated_qty": 200,
          "unit_price": 15.50,
          "price_currency": "MXN",
          "price_list": "Standard Buying",
          "batch_cost": 3100.00
        }
      ],
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
  "pricing_sources": [
    {
      "item_code": "ALO-LEAF-GEL-RAW",
      "source": "Item Price",
      "price_list": "Standard Buying",
      "valid_from": "2025-01-01"
    }
  ],
  "warnings": []
}
```


=====================================
4. PRICING DATA MODEL (ERPNext)
=====================================

4.1 ITEM PRICE DOCTYPE
----------------------

The primary source for pricing is the Item Price doctype in ERPNext:

Doctype: Item Price
Key Fields:
- item_code: Link to Item
- price_list: Link to Price List (e.g., "Standard Buying", "Standard Selling")
- price_list_rate: The actual price per UOM
- currency: Price currency (MXN, USD, etc.)
- uom: Unit of Measure for this price
- valid_from: Date price becomes effective
- valid_upto: Date price expires (optional)
- batch_no: Batch-specific pricing (optional)
- min_qty: Minimum quantity for this price (optional)

4.2 PRICE LIST DOCTYPE
----------------------

Doctype: Price List
Key Fields:
- name: Price list identifier (e.g., "Standard Buying")
- buying: 1 if this is for purchasing
- selling: 1 if this is for selling
- currency: Default currency
- enabled: 1 if active

4.3 ITEM DOCTYPE PRICING FIELDS
-------------------------------

The Item doctype may also have:
- standard_rate: Default rate
- valuation_rate: Stock valuation rate
- last_purchase_rate: Most recent purchase price

=====================================
5. PRICE RETRIEVAL LOGIC
=====================================

5.1 PRICE LOOKUP PRIORITY
-------------------------

When looking up price for an item, use this priority order:

1. Batch-specific Item Price (if batch pricing exists)
2. Item Price with valid_from <= today and valid_upto >= today (or null)
3. Item Price for the specified price_list
4. Item's standard_rate field
5. Item's last_purchase_rate field
6. Item's valuation_rate field

5.2 PRICE RETRIEVAL FUNCTION
----------------------------

```python
import frappe
from datetime import date

def get_item_price(item_code, price_list=None, batch_no=None, qty=1):
    """
    Get the best available price for an item.
    
    Args:
        item_code: Item code to price
        price_list: Preferred price list (default: Standard Buying)
        batch_no: Batch for batch-specific pricing
        qty: Quantity for quantity-based pricing
    
    Returns:
        dict with price, currency, source info
    """
    today = date.today()
    price_list = price_list or 'Standard Buying'
    
    # Try batch-specific price first
    if batch_no:
        batch_price = frappe.get_all(
            'Item Price',
            filters={
                'item_code': item_code,
                'price_list': price_list,
                'batch_no': batch_no,
                'valid_from': ['<=', today]
            },
            fields=['price_list_rate', 'currency', 'uom', 'valid_from'],
            order_by='valid_from desc',
            limit=1
        )
        if batch_price:
            return {
                'price': batch_price[0].price_list_rate,
                'currency': batch_price[0].currency,
                'uom': batch_price[0].uom,
                'source': 'Item Price (Batch)',
                'price_list': price_list,
                'valid_from': str(batch_price[0].valid_from)
            }
    
    # Try standard Item Price
    item_price = frappe.get_all(
        'Item Price',
        filters={
            'item_code': item_code,
            'price_list': price_list,
            'valid_from': ['<=', today]
        },
        or_filters={
            'valid_upto': ['>=', today],
            'valid_upto': ['is', 'not set']
        },
        fields=['price_list_rate', 'currency', 'uom', 'valid_from', 'min_qty'],
        order_by='valid_from desc',
        limit=5
    )
    
    # Filter by min_qty if applicable
    for price in item_price:
        min_qty = price.get('min_qty') or 0
        if qty >= min_qty:
            return {
                'price': price.price_list_rate,
                'currency': price.currency,
                'uom': price.uom,
                'source': 'Item Price',
                'price_list': price_list,
                'valid_from': str(price.valid_from)
            }
    
    # Fallback to Item document rates
    item = frappe.get_doc('Item', item_code)
    
    if item.standard_rate:
        return {
            'price': item.standard_rate,
            'currency': frappe.defaults.get_global_default('currency'),
            'uom': item.stock_uom,
            'source': 'Item Standard Rate',
            'price_list': None,
            'valid_from': None
        }
    
    if item.last_purchase_rate:
        return {
            'price': item.last_purchase_rate,
            'currency': frappe.defaults.get_global_default('currency'),
            'uom': item.stock_uom,
            'source': 'Last Purchase Rate',
            'price_list': None,
            'valid_from': None
        }
    
    if item.valuation_rate:
        return {
            'price': item.valuation_rate,
            'currency': frappe.defaults.get_global_default('currency'),
            'uom': item.stock_uom,
            'source': 'Valuation Rate',
            'price_list': None,
            'valid_from': None
        }
    
    # No price found
    return None
```


=====================================
6. RAVEN SKILL IMPLEMENTATION
=====================================

6.1 SKILL: calculate_formulation_cost
-------------------------------------

File: apps/raven_ai_agent/raven_ai_agent/skills/cost_calculator.py

```python
import frappe
import json
from datetime import date


def get_item_price(item_code, price_list='Standard Buying', batch_no=None, qty=1):
    """Get price for an item with fallback logic."""
    today = date.today()
    
    # Try batch-specific price
    if batch_no:
        batch_price = frappe.get_all(
            'Item Price',
            filters={
                'item_code': item_code,
                'price_list': price_list,
                'batch_no': batch_no,
                'valid_from': ['<=', today]
            },
            fields=['price_list_rate', 'currency', 'uom', 'valid_from'],
            order_by='valid_from desc',
            limit=1
        )
        if batch_price:
            return {
                'price': float(batch_price[0].price_list_rate),
                'currency': batch_price[0].currency,
                'uom': batch_price[0].uom,
                'source': 'Item Price (Batch)',
                'price_list': price_list,
                'valid_from': str(batch_price[0].valid_from)
            }
    
    # Try standard Item Price
    item_price = frappe.get_all(
        'Item Price',
        filters={
            'item_code': item_code,
            'price_list': price_list,
            'valid_from': ['<=', today]
        },
        fields=['price_list_rate', 'currency', 'uom', 'valid_from', 'min_qty'],
        order_by='valid_from desc',
        limit=5
    )
    
    for price in item_price:
        min_qty = price.get('min_qty') or 0
        if qty >= min_qty:
            return {
                'price': float(price.price_list_rate),
                'currency': price.currency,
                'uom': price.uom,
                'source': 'Item Price',
                'price_list': price_list,
                'valid_from': str(price.valid_from)
            }
    
    # Fallback to Item rates
    try:
        item = frappe.get_doc('Item', item_code)
        default_currency = frappe.defaults.get_global_default('currency') or 'MXN'
        
        if item.standard_rate:
            return {
                'price': float(item.standard_rate),
                'currency': default_currency,
                'uom': item.stock_uom,
                'source': 'Item Standard Rate',
                'price_list': None,
                'valid_from': None
            }
        
        if item.last_purchase_rate:
            return {
                'price': float(item.last_purchase_rate),
                'currency': default_currency,
                'uom': item.stock_uom,
                'source': 'Last Purchase Rate',
                'price_list': None,
                'valid_from': None
            }
        
        if item.valuation_rate:
            return {
                'price': float(item.valuation_rate),
                'currency': default_currency,
                'uom': item.stock_uom,
                'source': 'Valuation Rate',
                'price_list': None,
                'valid_from': None
            }
    except Exception as e:
        frappe.log_error(f'Error getting item rates: {str(e)}')
    
    return None


@frappe.whitelist()
def calculate_formulation_cost(compliance_results, price_list=None, formulation_request=None):
    """
    Raven AI Skill: Calculate costs for compliant batches.
    
    Args:
        compliance_results: JSON string or dict from Phase 3
        price_list: Price list to use (default: Standard Buying)
        formulation_request: Optional formulation details
    
    Returns:
        dict with cost breakdown and summary
    """
    if isinstance(compliance_results, str):
        compliance_results = json.loads(compliance_results)
    
    # Handle nested input from Phase 3
    if isinstance(compliance_results, dict) and 'compliance_results' in compliance_results:
        formulation_request = compliance_results.get('formulation_request', formulation_request)
        compliance_results = compliance_results['compliance_results']
    
    price_list = price_list or 'Standard Buying'
    
    cost_breakdown = []
    pricing_sources = []
    warnings = []
    total_material_cost = 0
    total_items = 0
    total_batches = 0
    currency = None
    
    for item_result in compliance_results:
        item_code = item_result.get('item_code')
        batches = item_result.get('batches_checked', [])
        
        # Skip non-compliant items
        if item_result.get('item_compliance_status') != 'ALL_COMPLIANT':
            warnings.append(f"Skipping {item_code}: not fully compliant")
            continue
        
        # Get item name
        try:
            item_doc = frappe.get_doc('Item', item_code)
            item_name = item_doc.item_name
            uom = item_doc.stock_uom
        except:
            item_name = item_code
            uom = 'Kg'
        
        batch_costs = []
        item_total_qty = 0
        item_total_cost = 0
        
        for batch in batches:
            # Only cost compliant batches
            if batch.get('tds_status') != 'COMPLIANT':
                warnings.append(f"Skipping batch {batch.get('batch_id')}: {batch.get('tds_status')}")
                continue
            
            batch_id = batch.get('batch_id')
            batch_no = batch.get('batch_no')
            allocated_qty = float(batch.get('allocated_qty', 0))
            
            # Get price for this batch
            price_info = get_item_price(item_code, price_list, batch_no, allocated_qty)
            
            if not price_info:
                warnings.append(f"No price found for {item_code} batch {batch_no}")
                price_info = {
                    'price': 0,
                    'currency': 'MXN',
                    'uom': uom,
                    'source': 'Not Found',
                    'price_list': None,
                    'valid_from': None
                }
            
            batch_cost = allocated_qty * price_info['price']
            
            if currency is None:
                currency = price_info['currency']
            
            batch_costs.append({
                'batch_id': batch_id,
                'batch_no': batch_no,
                'allocated_qty': allocated_qty,
                'unit_price': price_info['price'],
                'price_currency': price_info['currency'],
                'price_list': price_info['price_list'],
                'batch_cost': round(batch_cost, 2)
            })
            
            item_total_qty += allocated_qty
            item_total_cost += batch_cost
            total_batches += 1
        
        if batch_costs:
            cost_breakdown.append({
                'item_code': item_code,
                'item_name': item_name,
                'total_qty': item_total_qty,
                'uom': uom,
                'batch_costs': batch_costs,
                'item_total_cost': round(item_total_cost, 2)
            })
            
            # Record pricing source
            if batch_costs:
                pricing_sources.append({
                    'item_code': item_code,
                    'source': batch_costs[0].get('price_list') or 'Item Rate',
                    'price_list': batch_costs[0].get('price_list'),
                    'unit_price': batch_costs[0].get('unit_price')
                })
            
            total_material_cost += item_total_cost
            total_items += 1
    
    # Calculate cost per unit of finished product
    finished_qty = 1
    finished_uom = 'Kg'
    if formulation_request:
        finished_qty = float(formulation_request.get('target_quantity_kg', 1))
        finished_uom = formulation_request.get('uom', 'Kg')
    
    cost_per_unit = total_material_cost / finished_qty if finished_qty > 0 else 0
    
    return {
        'cost_breakdown': cost_breakdown,
        'summary': {
            'total_material_cost': round(total_material_cost, 2),
            'currency': currency or 'MXN',
            'finished_qty': finished_qty,
            'finished_uom': finished_uom,
            'cost_per_unit': round(cost_per_unit, 2),
            'items_costed': total_items,
            'batches_costed': total_batches
        },
        'pricing_sources': pricing_sources,
        'warnings': warnings
    }
```


=====================================
7. EXAMPLE PROMPTS FOR AGENT
=====================================

7.1 BASIC COST CALCULATION
--------------------------

User: "Calculate the cost for 500kg of Aloe Leaf Gel from batches ALOE-RAW-25032 and ALOE-RAW-25041"

Expected behavior:
1. Look up Item Price for ALO-LEAF-GEL-RAW
2. Calculate cost for each batch's allocated quantity
3. Return total cost and cost per kg

7.2 FORMULATION COST
--------------------

User: "What's the total material cost to produce 100kg of Aloe 200X Powder?"

Expected behavior:
1. Get compliant batch selections from Phase 3
2. Look up prices for each raw material
3. Calculate per-item costs and total
4. Calculate cost per kg of finished product

7.3 PRICE COMPARISON
--------------------

User: "Compare costs using Standard Buying vs Supplier XYZ price list"

Expected behavior:
1. Calculate costs using first price list
2. Calculate costs using second price list
3. Show comparison with savings

7.4 COST BREAKDOWN
------------------

User: "Show me a detailed cost breakdown for the aloe powder formulation"

Expected behavior:
1. List each raw material with quantities
2. Show per-batch costs
3. Show item subtotals
4. Show grand total and cost per unit

=====================================
8. ERROR HANDLING
=====================================

8.1 NO PRICE FOUND
------------------

```python
if not price_info:
    warnings.append({
        'item_code': item_code,
        'batch_no': batch_no,
        'error': 'NO_PRICE',
        'message': f'No price found for {item_code}. Using zero cost.',
        'action_required': 'Define Item Price or set standard_rate on Item'
    })
    price_info = {'price': 0, 'currency': 'MXN', 'source': 'Not Found'}
```

8.2 CURRENCY MISMATCH
---------------------

```python
if currency and price_info['currency'] != currency:
    warnings.append({
        'item_code': item_code,
        'warning': 'CURRENCY_MISMATCH',
        'message': f'{item_code} priced in {price_info["currency"]}, expected {currency}',
        'action_required': 'Currency conversion may be needed'
    })
```

8.3 EXPIRED PRICE
-----------------

```python
if price_info.get('valid_upto') and price_info['valid_upto'] < today:
    warnings.append({
        'item_code': item_code,
        'warning': 'EXPIRED_PRICE',
        'message': f'Price expired on {price_info["valid_upto"]}',
        'action_required': 'Update Item Price with current rates'
    })
```

=====================================
9. TEST CASES
=====================================

9.1 TEST: Price Lookup
----------------------

Test Script (bench console):
```python
import frappe
from datetime import date

# Test Item Price lookup
item_code = 'ALOE-200X-PWD-250311'  # Replace with real item

prices = frappe.get_all(
    'Item Price',
    filters={'item_code': item_code},
    fields=['name', 'price_list', 'price_list_rate', 'currency', 'valid_from', 'valid_upto']
)

print(f"Prices for {item_code}:")
for p in prices:
    print(f"  {p.price_list}: {p.price_list_rate} {p.currency} (valid: {p.valid_from} - {p.valid_upto})")

# Test Item rates
item = frappe.get_doc('Item', item_code)
print(f"\nItem rates:")
print(f"  standard_rate: {item.standard_rate}")
print(f"  last_purchase_rate: {item.last_purchase_rate}")
print(f"  valuation_rate: {item.valuation_rate}")
```

9.2 TEST: Cost Calculation
--------------------------

Test Script:
```python
# Test cost calculation logic
def calculate_batch_cost(qty, unit_price):
    return round(qty * unit_price, 2)

# Test cases
test_cases = [
    (300, 15.50, 4650.00),  # 300 kg @ 15.50 = 4650
    (200, 15.50, 3100.00),  # 200 kg @ 15.50 = 3100
    (100, 125.00, 12500.00), # 100 kg @ 125 = 12500
    (0, 15.50, 0.00),       # 0 kg = 0
]

for qty, price, expected in test_cases:
    result = calculate_batch_cost(qty, price)
    status = 'OK' if result == expected else 'ERROR'
    print(f"{status}: {qty} x {price} = {result} (expected {expected})")
```

9.3 TEST: Integration with Phase 3
----------------------------------

Test Script:
```python
import json

# Simulate Phase 3 output
phase3_output = {
    'compliance_results': [
        {
            'item_code': 'ALOE-200X-PWD-250311',
            'batches_checked': [
                {
                    'batch_id': 'BATCH-001',
                    'batch_no': 'ALOE-RAW-25032',
                    'allocated_qty': 300,
                    'tds_status': 'COMPLIANT'
                },
                {
                    'batch_id': 'BATCH-002',
                    'batch_no': 'ALOE-RAW-25041',
                    'allocated_qty': 200,
                    'tds_status': 'COMPLIANT'
                }
            ],
            'item_compliance_status': 'ALL_COMPLIANT'
        }
    ],
    'formulation_request': {
        'finished_item_code': 'ALO-200X-PWD-001',
        'target_quantity_kg': 100
    }
}

# Call cost calculator
from raven_ai_agent.skills.cost_calculator import calculate_formulation_cost
result = calculate_formulation_cost(json.dumps(phase3_output))

print(json.dumps(result, indent=2))
```

=====================================
10. SUCCESS CRITERIA
=====================================

Phase 4 is complete when:

[ ] Can query Item Price by item_code and price_list
[ ] Price lookup respects valid_from and valid_upto dates
[ ] Batch-specific pricing is supported
[ ] Fallback to Item rates (standard_rate, last_purchase_rate, valuation_rate)
[ ] Cost calculation is accurate (qty * unit_price)
[ ] Currency is tracked correctly
[ ] Non-compliant batches are skipped with warnings
[ ] Cost per unit of finished product is calculated
[ ] Missing prices generate appropriate warnings
[ ] Output format matches contract specification
[ ] Integration test with Phase 3 output passes

=====================================
11. INTEGRATION WITH PHASE 3 & PHASE 5
=====================================

Phase 4 receives output from Phase 3 (TDS_COMPLIANCE_CHECKER):
- Only processes batches with tds_status = "COMPLIANT"
- Uses allocated_qty for cost calculation

Phase 4 output goes to Phase 5 (OPTIMIZATION_ENGINE):
- Cost data enables cost-based optimization
- Can find lowest-cost batch combinations
- Supports what-if analysis

```python
# Pass cost data to Phase 5
phase5_input = {
    'cost_data': phase4_output,
    'optimization_goals': [
        'minimize_cost',
        'use_oldest_batches_first',
        'prefer_single_supplier'
    ]
}
```

=====================================
12. DATA DISCOVERY SCRIPTS
=====================================

Run these in bench console to understand pricing data:

```python
import frappe

# 1. List all Price Lists
print("=== Price Lists ===")
price_lists = frappe.get_all('Price List', fields=['name', 'buying', 'selling', 'currency', 'enabled'])
for pl in price_lists:
    print(f"  {pl.name}: buying={pl.buying}, selling={pl.selling}, currency={pl.currency}")

# 2. Sample Item Prices
print("\n=== Sample Item Prices ===")
prices = frappe.get_all('Item Price', limit=10, 
    fields=['item_code', 'price_list', 'price_list_rate', 'currency'])
for p in prices:
    print(f"  {p.item_code}: {p.price_list_rate} {p.currency} ({p.price_list})")

# 3. Items with valuation_rate
print("\n=== Items with Valuation Rates ===")
items = frappe.get_all('Item', 
    filters={'valuation_rate': ['>', 0]},
    fields=['name', 'valuation_rate', 'stock_uom'],
    limit=10)
for i in items:
    print(f"  {i.name}: {i.valuation_rate} per {i.stock_uom}")
```

=====================================
END OF PHASE 4 SUB-AGENT INSTRUCTIONS
=====================================


