PHASE2_BATCH_SELECTOR_AGENT
=====================================
SUB-AGENT INSTRUCTIONS FOR ORCHESTRATOR
=====================================

Document Version: 1.0
Phase: 2 of 6
Previous Phase: Phase 1 (FORMULATION_READER_AGENT)
Next Phase: Phase 3 (TDS_COMPLIANCE_CHECKER)

=====================================
1. MISSION STATEMENT
=====================================

You are the BATCH_SELECTOR_AGENT, a specialized sub-agent responsible for selecting optimal batches of raw materials to fulfill formulation requirements. Your primary objective is to implement intelligent batch selection using FEFO (First Expired, First Out) logic while respecting TDS compliance requirements.

You receive item requirements from the FORMULATION_READER_AGENT (Phase 1) and return ranked batch recommendations with availability status.

=====================================
2. INPUT CONTRACT
=====================================

You will receive data from Phase 1 in this format:


```json
{
  "formulation_request": {
    "finished_item_code": "ALO-200X-PWD-001",
    "finished_item_name": "Aloe 200X Powder",
    "target_quantity_kg": 100,
    "uom": "Kg"
  },
  "required_items": [
    {
      "item_code": "ALO-LEAF-GEL-RAW",
      "item_name": "Aloe Vera Leaf Gel (Raw)",
      "required_qty": 500,
      "uom": "Kg",
      "golden_numbers": {
        "year": 25,
        "week": 03,
        "day": 2,
        "sequence": 1,
        "parsed_date": "2025-01-14"
      }
    }
  ],
  "warehouse": "Main Warehouse - AMB"
}
```

=====================================
3. OUTPUT CONTRACT
=====================================

You must return batch selections in this format:

```json
{
  "batch_selections": [
    {
      "item_code": "ALO-LEAF-GEL-RAW",
      "required_qty": 500,
      "selected_batches": [
        {
          "batch_id": "BATCH-2025-001",
          "batch_no": "ALO-RAW-25032",
          "available_qty": 300,
          "allocated_qty": 300,
          "warehouse": "Main Warehouse - AMB",
          "manufacturing_date": "2025-01-14",
          "expiry_date": "2026-01-14",
          "golden_number": {
            "year": 25,
            "week": 03,
            "day": 2,
            "sequence": 1
          },
          "fefo_rank": 1,
          "tds_status": "pending_check"
        },
        {
          "batch_id": "BATCH-2025-002",
          "batch_no": "ALO-RAW-25041",
          "available_qty": 250,
          "allocated_qty": 200,
          "warehouse": "Main Warehouse - AMB",
          "manufacturing_date": "2025-01-21",
          "expiry_date": "2026-01-21",
          "golden_number": {
            "year": 25,
            "week": 04,
            "day": 1,
            "sequence": 1
          },
          "fefo_rank": 2,
          "tds_status": "pending_check"
        }
      ],
      "total_allocated": 500,
      "fulfillment_status": "COMPLETE"
    }
  ],
  "overall_status": "ALL_ITEMS_FULFILLED"
}
```


=====================================
4. CORE FEFO LOGIC (CRITICAL)
=====================================

IMPORTANT: The manufacturing date in ERPNext Batch doctype may be the MIGRATION DATE, not the actual manufacturing date. For accurate FEFO, you MUST use the GOLDEN NUMBER parsed from the item_code.

4.1 GOLDEN NUMBER PRIORITY SORTING
---------------------------------

When sorting batches, use this priority order:

1. PRIMARY: Parse golden_number from item_code pattern: ITEM_YYWWDS
   - YY = Year (25 = 2025)
   - WW = Week number (01-52)
   - D = Day of week (1=Mon, 7=Sun)
   - S = Sequence (1-9)

2. SECONDARY: Only use batch.manufacturing_date if golden_number cannot be parsed

3. TERTIARY: Use batch.expiry_date if no manufacturing info available

4.2 PYTHON SORTING ALGORITHM
----------------------------

```python
def parse_golden_number(item_code):
    """
    Parse golden number from item_code.
    Pattern: ITEM_YYWWDS where:
    - YY = year (2 digits)
    - WW = week (2 digits)
    - D = day of week (1 digit)
    - S = sequence (1 digit)
    
    Returns dict with parsed values or None if invalid.
    """
    import re
    from datetime import datetime, timedelta
    
    # Match pattern at end of item_code: 6 digits (YYWWDS)
    match = re.search(r'(\d{2})(\d{2})(\d)(\d)$', item_code)
    if not match:
        return None
    
    year = int(match.group(1))
    week = int(match.group(2))
    day = int(match.group(3))
    sequence = int(match.group(4))
    
    # Validate ranges
    if week < 1 or week > 52 or day < 1 or day > 7:
        return None
    
    # Convert to full year
    full_year = 2000 + year if year < 50 else 1900 + year
    
    # Calculate actual date from year, week, day
    # ISO week date: Week 1 contains Jan 4th
    jan4 = datetime(full_year, 1, 4)
    week_start = jan4 - timedelta(days=jan4.weekday())
    target_date = week_start + timedelta(weeks=week-1, days=day-1)
    
    return {
        'year': year,
        'week': week,
        'day': day,
        'sequence': sequence,
        'parsed_date': target_date.strftime('%Y-%m-%d'),
        'sort_key': f"{full_year:04d}{week:02d}{day}{sequence}"
    }


def sort_batches_fefo(batches):
    """
    Sort batches using FEFO logic with golden number priority.
    
    Priority:
    1. Golden number from item_code (earliest first)
    2. Batch manufacturing_date (earliest first)
    3. Batch expiry_date (earliest first)
    """
    def get_sort_key(batch):
        # Try golden number first
        gn = parse_golden_number(batch.get('item_code', ''))
        if gn:
            return (0, gn['sort_key'])  # Priority 0 = highest
        
        # Fall back to manufacturing_date
        if batch.get('manufacturing_date'):
            return (1, batch['manufacturing_date'])
        
        # Fall back to expiry_date
        if batch.get('expiry_date'):
            return (2, batch['expiry_date'])
        
        # No date info - lowest priority
        return (3, '9999-12-31')
    
    return sorted(batches, key=get_sort_key)
```


=====================================
5. DATA QUERIES (FRAPPE API)
=====================================

5.1 GET BATCHES FOR ITEM
------------------------

```python
def get_available_batches(item_code, warehouse=None):
    """
    Get all available batches for an item with stock > 0.
    Joins Batch with Bin to get actual_qty.
    """
    import frappe
    
    filters = {
        'item': item_code,
        'disabled': 0
    }
    
    batches = frappe.get_all(
        'Batch',
        filters=filters,
        fields=[
            'name',
            'batch_id',
            'item',
            'manufacturing_date',
            'expiry_date',
            'batch_qty',
            'stock_uom'
        ]
    )
    
    # Get actual stock from Bin for each batch
    result = []
    for batch in batches:
        bin_filters = {
            'item_code': item_code,
            'batch_no': batch.name
        }
        if warehouse:
            bin_filters['warehouse'] = warehouse
        
        bins = frappe.get_all(
            'Bin',
            filters=bin_filters,
            fields=['warehouse', 'actual_qty', 'reserved_qty']
        )
        
        for bin_record in bins:
            available = bin_record.actual_qty - (bin_record.reserved_qty or 0)
            if available > 0:
                result.append({
                    'batch_id': batch.name,
                    'batch_no': batch.batch_id or batch.name,
                    'item_code': batch.item,
                    'manufacturing_date': str(batch.manufacturing_date) if batch.manufacturing_date else None,
                    'expiry_date': str(batch.expiry_date) if batch.expiry_date else None,
                    'warehouse': bin_record.warehouse,
                    'available_qty': available,
                    'uom': batch.stock_uom
                })
    
    return result
```

5.2 BATCH SELECTION WITH ALLOCATION
-----------------------------------

```python
def select_batches_for_requirement(item_code, required_qty, warehouse=None):
    """
    Select batches to fulfill required quantity using FEFO.
    Returns list of batch allocations.
    """
    # Get available batches
    batches = get_available_batches(item_code, warehouse)
    
    # Sort using FEFO with golden number priority
    sorted_batches = sort_batches_fefo(batches)
    
    # Allocate from oldest to newest
    allocations = []
    remaining = required_qty
    
    for rank, batch in enumerate(sorted_batches, start=1):
        if remaining <= 0:
            break
        
        allocate_qty = min(batch['available_qty'], remaining)
        
        # Parse golden number for this batch
        gn = parse_golden_number(batch['item_code'])
        
        allocations.append({
            'batch_id': batch['batch_id'],
            'batch_no': batch['batch_no'],
            'available_qty': batch['available_qty'],
            'allocated_qty': allocate_qty,
            'warehouse': batch['warehouse'],
            'manufacturing_date': batch['manufacturing_date'],
            'expiry_date': batch['expiry_date'],
            'golden_number': gn,
            'fefo_rank': rank,
            'tds_status': 'pending_check'
        })
        
        remaining -= allocate_qty
    
    total_allocated = required_qty - remaining
    fulfillment_status = 'COMPLETE' if remaining <= 0 else 'PARTIAL'
    
    return {
        'item_code': item_code,
        'required_qty': required_qty,
        'selected_batches': allocations,
        'total_allocated': total_allocated,
        'shortfall': max(0, remaining),
        'fulfillment_status': fulfillment_status
    }
```


=====================================
6. RAVEN SKILL IMPLEMENTATION
=====================================

6.1 SKILL: select_batches_for_formulation
-----------------------------------------

File: apps/raven_ai_agent/raven_ai_agent/skills/batch_selector.py

```python
import frappe
import json
import re
from datetime import datetime, timedelta


def parse_golden_number(item_code):
    """Parse golden number from item_code pattern YYWWDS."""
    match = re.search(r'(\d{2})(\d{2})(\d)(\d)$', item_code)
    if not match:
        return None
    
    year = int(match.group(1))
    week = int(match.group(2))
    day = int(match.group(3))
    sequence = int(match.group(4))
    
    if week < 1 or week > 52 or day < 1 or day > 7:
        return None
    
    full_year = 2000 + year if year < 50 else 1900 + year
    jan4 = datetime(full_year, 1, 4)
    week_start = jan4 - timedelta(days=jan4.weekday())
    target_date = week_start + timedelta(weeks=week-1, days=day-1)
    
    return {
        'year': year,
        'week': week,
        'day': day,
        'sequence': sequence,
        'parsed_date': target_date.strftime('%Y-%m-%d'),
        'sort_key': f"{full_year:04d}{week:02d}{day}{sequence}"
    }


def get_batch_sort_key(batch):
    """Get sort key for FEFO ordering."""
    gn = parse_golden_number(batch.get('item_code', ''))
    if gn:
        return (0, gn['sort_key'])
    if batch.get('manufacturing_date'):
        return (1, str(batch['manufacturing_date']))
    if batch.get('expiry_date'):
        return (2, str(batch['expiry_date']))
    return (3, '9999-12-31')


@frappe.whitelist()
def select_batches_for_formulation(required_items, warehouse=None):
    """
    Raven AI Skill: Select optimal batches for formulation items.
    
    Args:
        required_items: JSON string or list of items with required_qty
        warehouse: Optional warehouse filter
    
    Returns:
        dict with batch_selections and overall_status
    """
    if isinstance(required_items, str):
        required_items = json.loads(required_items)
    
    batch_selections = []
    all_fulfilled = True
    
    for item in required_items:
        item_code = item.get('item_code')
        required_qty = float(item.get('required_qty', 0))
        
        # Get available batches
        batch_filters = {'item': item_code, 'disabled': 0}
        batches = frappe.get_all(
            'Batch',
            filters=batch_filters,
            fields=['name', 'batch_id', 'item', 'manufacturing_date', 'expiry_date', 'stock_uom']
        )
        
        # Get stock from Bin for each batch
        available_batches = []
        for batch in batches:
            bin_filters = {'item_code': item_code, 'batch_no': batch.name}
            if warehouse:
                bin_filters['warehouse'] = warehouse
            
            bins = frappe.get_all(
                'Bin',
                filters=bin_filters,
                fields=['warehouse', 'actual_qty', 'reserved_qty']
            )
            
            for bin_rec in bins:
                available = (bin_rec.actual_qty or 0) - (bin_rec.reserved_qty or 0)
                if available > 0:
                    available_batches.append({
                        'batch_id': batch.name,
                        'batch_no': batch.batch_id or batch.name,
                        'item_code': batch.item,
                        'manufacturing_date': str(batch.manufacturing_date) if batch.manufacturing_date else None,
                        'expiry_date': str(batch.expiry_date) if batch.expiry_date else None,
                        'warehouse': bin_rec.warehouse,
                        'available_qty': available,
                        'uom': batch.stock_uom
                    })
        
        # Sort by FEFO with golden number priority
        sorted_batches = sorted(available_batches, key=get_batch_sort_key)
        
        # Allocate
        allocations = []
        remaining = required_qty
        
        for rank, batch in enumerate(sorted_batches, start=1):
            if remaining <= 0:
                break
            
            allocate_qty = min(batch['available_qty'], remaining)
            gn = parse_golden_number(batch['item_code'])
            
            allocations.append({
                'batch_id': batch['batch_id'],
                'batch_no': batch['batch_no'],
                'available_qty': batch['available_qty'],
                'allocated_qty': allocate_qty,
                'warehouse': batch['warehouse'],
                'manufacturing_date': batch['manufacturing_date'],
                'expiry_date': batch['expiry_date'],
                'golden_number': gn,
                'fefo_rank': rank,
                'tds_status': 'pending_check'
            })
            
            remaining -= allocate_qty
        
        total_allocated = required_qty - max(0, remaining)
        status = 'COMPLETE' if remaining <= 0 else 'PARTIAL'
        
        if remaining > 0:
            all_fulfilled = False
        
        batch_selections.append({
            'item_code': item_code,
            'item_name': item.get('item_name', ''),
            'required_qty': required_qty,
            'selected_batches': allocations,
            'total_allocated': total_allocated,
            'shortfall': max(0, remaining),
            'fulfillment_status': status
        })
    
    return {
        'batch_selections': batch_selections,
        'overall_status': 'ALL_ITEMS_FULFILLED' if all_fulfilled else 'SOME_ITEMS_SHORT'
    }
```


=====================================
7. EXAMPLE PROMPTS FOR AGENT
=====================================

7.1 BASIC BATCH SELECTION
-------------------------

User: "Select batches for 500 kg of Aloe Leaf Gel (ALO-LEAF-GEL-RAW)"

Expected behavior:
1. Query all batches for item ALO-LEAF-GEL-RAW
2. Get stock levels from Bin
3. Sort by golden number (FEFO)
4. Allocate 500 kg starting from oldest
5. Return batch list with allocations

7.2 MULTI-ITEM SELECTION
------------------------

User: "I need batches for this formulation: 500kg Aloe Gel, 50kg Maltodextrin, 10kg Citric Acid"

Expected behavior:
1. Process each item sequentially
2. Apply FEFO logic to each
3. Report any shortfalls
4. Return consolidated batch selections

7.3 WAREHOUSE-SPECIFIC SELECTION
--------------------------------

User: "Select batches from Main Warehouse - AMB for 200kg of ALOE-200X-PWD-250511"

Expected behavior:
1. Filter by specific warehouse
2. Only consider stock in that warehouse
3. Parse golden number 250511 -> Year 25, Week 05, Day 1, Seq 1

7.4 AVAILABILITY CHECK
----------------------

User: "Do we have enough stock to make 100kg of Aloe 200X Powder?"

Expected behavior:
1. Get BOM items for Aloe 200X Powder
2. Check batch availability for each
3. Report fulfillment status
4. List any shortfalls

=====================================
8. ERROR HANDLING
=====================================

8.1 NO BATCHES FOUND
--------------------

```python
if not available_batches:
    return {
        'item_code': item_code,
        'required_qty': required_qty,
        'selected_batches': [],
        'total_allocated': 0,
        'shortfall': required_qty,
        'fulfillment_status': 'NO_STOCK',
        'error': f'No batches found for item {item_code}'
    }
```

8.2 INSUFFICIENT STOCK
----------------------

```python
if remaining > 0:
    return {
        'item_code': item_code,
        'required_qty': required_qty,
        'selected_batches': allocations,
        'total_allocated': total_allocated,
        'shortfall': remaining,
        'fulfillment_status': 'PARTIAL',
        'warning': f'Only {total_allocated} of {required_qty} available'
    }
```

8.3 INVALID ITEM CODE
---------------------

```python
if not frappe.db.exists('Item', item_code):
    return {
        'error': f'Item {item_code} does not exist',
        'fulfillment_status': 'ERROR'
    }
```

8.4 EXPIRED BATCHES
-------------------

```python
from datetime import date

# Filter out expired batches
available_batches = [
    b for b in available_batches
    if not b.get('expiry_date') or 
       datetime.strptime(b['expiry_date'], '%Y-%m-%d').date() > date.today()
]
```


=====================================
9. TEST CASES
=====================================

9.1 TEST: Golden Number Parsing
-------------------------------

Test Script (bench console):
```python
# Test golden number parsing
from datetime import datetime, timedelta
import re

def parse_golden_number(item_code):
    match = re.search(r'(\d{2})(\d{2})(\d)(\d)$', item_code)
    if not match:
        return None
    year, week, day, seq = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
    if week < 1 or week > 52 or day < 1 or day > 7:
        return None
    full_year = 2000 + year
    jan4 = datetime(full_year, 1, 4)
    week_start = jan4 - timedelta(days=jan4.weekday())
    target_date = week_start + timedelta(weeks=week-1, days=day-1)
    return {'year': year, 'week': week, 'day': day, 'sequence': seq, 'parsed_date': target_date.strftime('%Y-%m-%d')}

# Test cases
test_codes = [
    'ALOE-200X-PWD-250311',  # Year 25, Week 03, Day 1, Seq 1
    'ALO-GEL-RAW-250521',    # Year 25, Week 05, Day 2, Seq 1
    'MALTO-PWD-241252',      # Year 24, Week 12, Day 5, Seq 2
    'INVALID-CODE',          # Should return None
]

for code in test_codes:
    result = parse_golden_number(code)
    print(f"{code}: {result}")
```

Expected Output:
- 250311 -> 2025-01-13 (Monday of Week 3)
- 250521 -> 2025-01-28 (Tuesday of Week 5)
- 241252 -> 2024-03-22 (Friday of Week 12)
- INVALID-CODE -> None

9.2 TEST: FEFO Sorting
----------------------

Test Script:
```python
# Test FEFO sorting with golden numbers
test_batches = [
    {'item_code': 'ALOE-250521', 'manufacturing_date': '2025-01-28'},  # Week 5
    {'item_code': 'ALOE-250311', 'manufacturing_date': '2025-01-13'},  # Week 3 (older)
    {'item_code': 'ALOE-250411', 'manufacturing_date': '2025-01-20'},  # Week 4
    {'item_code': 'ALOE-LEGACY', 'manufacturing_date': '2024-12-01'},  # No golden number
]

def get_sort_key(batch):
    gn = parse_golden_number(batch.get('item_code', ''))
    if gn:
        return (0, f"{2000+gn['year']:04d}{gn['week']:02d}{gn['day']}{gn['sequence']}")
    if batch.get('manufacturing_date'):
        return (1, batch['manufacturing_date'])
    return (3, '9999-12-31')

sorted_batches = sorted(test_batches, key=get_sort_key)
for b in sorted_batches:
    print(f"{b['item_code']}: {b['manufacturing_date']}")
```

Expected Order:
1. ALOE-250311 (Week 3 - oldest golden number)
2. ALOE-250411 (Week 4)
3. ALOE-250521 (Week 5)
4. ALOE-LEGACY (no golden number, falls back to mfg date)

9.3 TEST: Batch Selection with Real Data
----------------------------------------

Test Script:
```python
import frappe

# Get real batches from system
item_code = 'ALOE-200X-PWD-250311'  # Replace with actual item
batches = frappe.get_all('Batch', filters={'item': item_code}, fields=['name', 'item', 'manufacturing_date'])

print(f"Found {len(batches)} batches for {item_code}")
for b in batches:
    gn = parse_golden_number(b.item)
    print(f"  {b.name}: mfg={b.manufacturing_date}, golden={gn}")

# Get stock from Bin
for batch in batches[:3]:  # First 3
    bins = frappe.get_all('Bin', filters={'batch_no': batch.name}, fields=['warehouse', 'actual_qty'])
    print(f"  Stock for {batch.name}: {bins}")
```

9.4 TEST: Allocation Logic
--------------------------

Test Script:
```python
# Test allocation with shortfall
test_batches = [
    {'batch_id': 'B001', 'available_qty': 100},
    {'batch_id': 'B002', 'available_qty': 150},
    {'batch_id': 'B003', 'available_qty': 75},
]

required_qty = 400
allocations = []
remaining = required_qty

for batch in test_batches:
    if remaining <= 0:
        break
    alloc = min(batch['available_qty'], remaining)
    allocations.append({'batch_id': batch['batch_id'], 'allocated': alloc})
    remaining -= alloc

print(f"Required: {required_qty}")
print(f"Allocated: {allocations}")
print(f"Total: {sum(a['allocated'] for a in allocations)}")
print(f"Shortfall: {max(0, remaining)}")
```

Expected Output:
- Allocated: B001=100, B002=150, B003=75
- Total: 325
- Shortfall: 75


=====================================
10. SUCCESS CRITERIA
=====================================

Phase 2 is complete when:

[ ] Can query batches for any valid item code
[ ] Can get stock levels from Bin doctype correctly
[ ] Golden number parsing works for all valid patterns (YYWWDS)
[ ] FEFO sorting prioritizes golden number over manufacturing_date
[ ] Allocation logic correctly handles partial fulfillment
[ ] Shortfall calculation is accurate
[ ] Multi-item selection works correctly
[ ] Warehouse filtering works correctly
[ ] Expired batches are excluded from selection
[ ] Error handling returns proper status codes
[ ] Output format matches contract specification
[ ] Integration test with Phase 1 output passes

=====================================
11. INTEGRATION WITH PHASE 1
=====================================

Phase 2 receives output from Phase 1 (FORMULATION_READER_AGENT):

```python
# Phase 1 output (example)
phase1_output = {
    'formulation_request': {
        'finished_item_code': 'ALOE-200X-PWD-001',
        'target_quantity_kg': 100
    },
    'required_items': [
        {'item_code': 'ALO-LEAF-GEL-RAW', 'required_qty': 500},
        {'item_code': 'MALTO-PWD-001', 'required_qty': 50}
    ]
}

# Phase 2 processes this
phase2_output = select_batches_for_formulation(
    required_items=phase1_output['required_items'],
    warehouse=None  # Or specific warehouse
)

# Phase 2 output goes to Phase 3 (TDS_COMPLIANCE_CHECKER)
```

=====================================
12. HANDOFF TO PHASE 3
=====================================

Phase 2 output is sent to Phase 3 (TDS_COMPLIANCE_CHECKER) which will:

1. Take each selected batch
2. Look up COA AMB / COA AMB2 records
3. Check TDS specification compliance
4. Flag any non-compliant batches
5. Return compliance status for each batch

=====================================
END OF PHASE 2 SUB-AGENT INSTRUCTIONS
=====================================


