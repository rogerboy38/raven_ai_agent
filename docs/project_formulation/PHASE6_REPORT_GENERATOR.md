# PHASE 6: REPORT_GENERATOR - Technical Specification

## Sub-Agent: REPORT_GENERATOR_AGENT

---

## 1. OBJECTIVE

Generate comprehensive, formatted reports from the optimization results produced by the OPTIMIZATION_ENGINE. This final sub-agent consolidates all data from previous phases into actionable output formats suitable for:
- Human review and decision-making
- System logging and audit trails
- Integration with ERPNext workflows
- Export to external systems (PDF, JSON, email)

---

## 2. INPUT REQUIREMENTS

### From OPTIMIZATION_ENGINE (Phase 5):
```python
optimization_result = {
    'optimization_result': {
        'status': 'OPTIMIZED',  # or 'PARTIAL'
        'strategy_used': 'balanced',
        'original_cost': 12500.00,
        'optimized_cost': 11875.00,
        'savings': 625.00,
        'savings_percentage': 5.0
    },
    'optimized_selection': [
        {'batch_id': 'BATCH-2311-001', 'allocated_qty': 100, 'unit_price': 42.50, 'batch_cost': 4250.00},
        {'batch_id': 'BATCH-2311-002', 'allocated_qty': 50, 'unit_price': 45.00, 'batch_cost': 2250.00}
    ],
    'what_if_scenarios': [...],
    'constraints_satisfied': {
        'tds_compliance': True,
        'fefo_respected': True,
        'quantity_fulfilled': True
    },
    'recommendations': []
}
```

### From Previous Phases:
- **Phase 1 (FORMULATION_READER)**: Item details, golden number, required quantity
- **Phase 2 (BATCH_SELECTOR)**: Available batches with FEFO ranking
- **Phase 3 (TDS_COMPLIANCE)**: COA validation results, parameter checks
- **Phase 4 (COST_CALCULATOR)**: Pricing details, price source hierarchy

---

## 3. OUTPUT FORMATS

### 3.1 Summary Report (Human-Readable)
```
================================================================================
                    ALOE POWDER FORMULATION OPTIMIZATION REPORT
================================================================================

Generated: 2024-01-15 14:30:00
Item: POLVO-ALOE-200X-TAN (Golden: 2311)
Required Quantity: 150 kg

--------------------------------------------------------------------------------
                              OPTIMIZATION SUMMARY
--------------------------------------------------------------------------------
Status: OPTIMIZED
Strategy: Balanced (Golden Priority + FEFO + Cost Tolerance)

Original Cost:    $12,500.00
Optimized Cost:   $11,875.00
Savings:          $625.00 (5.0%)

--------------------------------------------------------------------------------
                              BATCH ALLOCATION
--------------------------------------------------------------------------------
| Batch ID        | Quantity | Unit Price | Batch Cost | Expiry Date  | Golden |
|-----------------|----------|------------|------------|--------------|--------|
| BATCH-2311-001  | 100 kg   | $42.50     | $4,250.00  | 2024-06-15   | Yes    |
| BATCH-2311-002  | 50 kg    | $45.00     | $2,250.00  | 2024-08-20   | Yes    |
|-----------------|----------|------------|------------|--------------|--------|
| TOTAL           | 150 kg   |            | $6,500.00  |              |        |

--------------------------------------------------------------------------------
                              COMPLIANCE STATUS
--------------------------------------------------------------------------------
[PASS] TDS Compliance: All parameters within specification
[PASS] FEFO Respected: Oldest batches prioritized
[PASS] Quantity Fulfilled: 100% of required quantity allocated

--------------------------------------------------------------------------------
                              WHAT-IF SCENARIOS
--------------------------------------------------------------------------------
| Scenario      | Total Cost   | Difference | Notes                           |
|---------------|--------------|------------|----------------------------------|
| FEFO_ONLY     | $12,500.00   | +$625.00   | Strict FEFO, no optimization    |
| LOWEST_COST   | $11,500.00   | -$375.00   | WARNING: Violates FEFO          |
| BALANCED      | $11,875.00   | $0.00      | Current selection (recommended) |

================================================================================
                                  END OF REPORT
================================================================================
```


### 3.2 JSON Export (System Integration)
```json
{
  "report_metadata": {
    "generated_at": "2024-01-15T14:30:00Z",
    "report_type": "formulation_optimization",
    "version": "1.0"
  },
  "item_details": {
    "item_code": "POLVO-ALOE-200X-TAN",
    "item_name": "Aloe Vera Powder 200X Tan",
    "golden_number": 2311,
    "required_qty": 150,
    "uom": "kg"
  },
  "optimization_summary": {
    "status": "OPTIMIZED",
    "strategy": "balanced",
    "original_cost": 12500.00,
    "optimized_cost": 11875.00,
    "savings": 625.00,
    "savings_percentage": 5.0
  },
  "batch_allocation": [
    {
      "batch_id": "BATCH-2311-001",
      "allocated_qty": 100,
      "unit_price": 42.50,
      "batch_cost": 4250.00,
      "expiry_date": "2024-06-15",
      "is_golden_match": true
    }
  ],
  "compliance": {
    "tds_compliance": true,
    "fefo_respected": true,
    "quantity_fulfilled": true
  },
  "what_if_scenarios": [...]
}
```

---

## 4. CORE FUNCTIONS

### 4.1 build_summary_report()
```python
def build_summary_report(optimization_data, item_info, formulation_info):
    """
    Generate human-readable summary report.
    
    Args:
        optimization_data: Result from OPTIMIZATION_ENGINE
        item_info: Item details from FORMULATION_READER
        formulation_info: Formulation requirements
    
    Returns:
        str: Formatted text report
    """
    report = []
    
    # Header
    report.append("=" * 80)
    report.append("ALOE POWDER FORMULATION OPTIMIZATION REPORT".center(80))
    report.append("=" * 80)
    report.append("")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Item: {item_info['item_code']} (Golden: {item_info['golden_number']})")
    report.append(f"Required Quantity: {formulation_info['required_qty']} {item_info['stock_uom']}")
    report.append("")
    
    # Optimization Summary
    opt = optimization_data['optimization_result']
    report.append("-" * 80)
    report.append("OPTIMIZATION SUMMARY".center(80))
    report.append("-" * 80)
    report.append(f"Status: {opt['status']}")
    report.append(f"Strategy: {opt['strategy_used'].title()}")
    report.append("")
    report.append(f"Original Cost:    ${opt['original_cost']:,.2f}")
    report.append(f"Optimized Cost:   ${opt['optimized_cost']:,.2f}")
    report.append(f"Savings:          ${opt['savings']:,.2f} ({opt['savings_percentage']:.1f}%)")
    
    return "\n".join(report)
```

### 4.2 format_allocation_table()
```python
def format_allocation_table(allocations, golden_number=None):
    """
    Format batch allocations as ASCII table.
    """
    headers = ['Batch ID', 'Quantity', 'Unit Price', 'Batch Cost', 'Expiry Date', 'Golden']
    rows = []
    total_qty = 0
    total_cost = 0
    
    for alloc in allocations:
        batch_golden = extract_golden_from_batch(alloc['batch_id'])
        is_golden = 'Yes' if golden_number and batch_golden == golden_number else 'No'
        
        rows.append([
            alloc['batch_id'],
            f"{alloc['allocated_qty']} kg",
            f"${alloc['unit_price']:.2f}",
            f"${alloc['batch_cost']:.2f}",
            alloc.get('expiry_date', 'N/A'),
            is_golden
        ])
        total_qty += alloc['allocated_qty']
        total_cost += alloc['batch_cost']
    
    # Add totals row
    rows.append(['TOTAL', f"{total_qty} kg", '', f"${total_cost:.2f}", '', ''])
    
    return tabulate(rows, headers=headers, tablefmt='pipe')
```

### 4.3 build_json_export()
```python
def build_json_export(optimization_data, item_info, formulation_info):
    """
    Generate JSON export for system integration.
    """
    export = {
        'report_metadata': {
            'generated_at': datetime.now().isoformat(),
            'report_type': 'formulation_optimization',
            'version': '1.0'
        },
        'item_details': {
            'item_code': item_info['item_code'],
            'item_name': item_info['item_name'],
            'golden_number': item_info['golden_number'],
            'required_qty': formulation_info['required_qty'],
            'uom': item_info['stock_uom']
        },
        'optimization_summary': optimization_data['optimization_result'],
        'batch_allocation': optimization_data['optimized_selection'],
        'compliance': optimization_data['constraints_satisfied'],
        'what_if_scenarios': optimization_data['what_if_scenarios']
    }
    
    return json.dumps(export, indent=2, default=str)
```

### 4.4 generate_recommendations()
```python
def generate_recommendations(optimization_data, constraints):
    """
    Generate actionable recommendations based on results.
    """
    recommendations = []
    
    # Check for partial fulfillment
    if optimization_data['optimization_result']['status'] == 'PARTIAL':
        recommendations.append({
            'priority': 'HIGH',
            'category': 'INVENTORY',
            'message': 'Insufficient stock to fulfill complete order.',
            'action': 'Create Purchase Order'
        })
    
    # Check TDS compliance
    if not constraints.get('tds_compliance', True):
        recommendations.append({
            'priority': 'CRITICAL',
            'category': 'COMPLIANCE',
            'message': 'Selected batches do not meet TDS specifications.',
            'action': 'Review COA and select compliant batches'
        })
    
    return recommendations
```


---

## 5. ERPNEXT INTEGRATION

### 5.1 Save Report to ERPNext
```python
def save_report_to_erpnext(report_data, item_code, doctype='Stock Entry'):
    """
    Create a Note or Custom Doctype to store the report.
    """
    import frappe
    
    # Option 1: Create a Note with the report
    note = frappe.new_doc('Note')
    note.title = f"Formulation Report - {item_code} - {frappe.utils.now()}"
    note.content = report_data['text_report']
    note.public = 0
    note.insert()
    
    return note.name
```

### 5.2 Email Report
```python
def email_report(report_data, recipients, item_code):
    """
    Send report via email.
    """
    import frappe
    from frappe.utils import now_datetime
    
    subject = f"Formulation Optimization Report: {item_code}"
    message = f"""
    <h2>Formulation Optimization Report</h2>
    <p>Generated: {now_datetime()}</p>
    <p>Item: {item_code}</p>
    <hr>
    <pre>{report_data['text_report']}</pre>
    """
    
    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        attachments=[{
            'fname': f'optimization_report_{item_code}.json',
            'fcontent': report_data['json_export']
        }]
    )
```

### 5.3 Create Stock Entry from Allocation
```python
def create_stock_entry_from_allocation(allocation, item_code, target_warehouse):
    """
    Create a Material Transfer Stock Entry based on optimized allocation.
    """
    import frappe
    
    se = frappe.new_doc('Stock Entry')
    se.stock_entry_type = 'Material Transfer'
    se.purpose = 'Material Transfer'
    
    for alloc in allocation:
        se.append('items', {
            'item_code': item_code,
            'qty': alloc['allocated_qty'],
            'batch_no': alloc['batch_id'],
            's_warehouse': 'Stores - AMB',  # Source warehouse
            't_warehouse': target_warehouse,
            'basic_rate': alloc['unit_price']
        })
    
    se.insert()
    return se.name
```

---

## 6. BENCH CONSOLE TEST SCRIPTS

### Test 1: Generate Text Report
```python
# Test text report generation
from datetime import datetime

optimization_data = {
    'optimization_result': {
        'status': 'OPTIMIZED',
        'strategy_used': 'balanced',
        'original_cost': 12500.00,
        'optimized_cost': 11875.00,
        'savings': 625.00,
        'savings_percentage': 5.0
    },
    'optimized_selection': [
        {'batch_id': 'BATCH-2311-001', 'allocated_qty': 100, 'unit_price': 42.50, 'batch_cost': 4250.00, 'expiry_date': '2024-06-15'},
        {'batch_id': 'BATCH-2311-002', 'allocated_qty': 50, 'unit_price': 45.00, 'batch_cost': 2250.00, 'expiry_date': '2024-08-20'}
    ],
    'constraints_satisfied': {
        'tds_compliance': True,
        'fefo_respected': True,
        'quantity_fulfilled': True
    }
}

item_info = {
    'item_code': 'POLVO-ALOE-200X-TAN',
    'golden_number': 2311,
    'stock_uom': 'kg'
}

# Generate header
print("=" * 80)
print("ALOE POWDER FORMULATION OPTIMIZATION REPORT".center(80))
print("=" * 80)
print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Item: {item_info['item_code']} (Golden: {item_info['golden_number']})")
print()

# Summary
opt = optimization_data['optimization_result']
print(f"Status: {opt['status']}")
print(f"Original Cost: ${opt['original_cost']:,.2f}")
print(f"Optimized Cost: ${opt['optimized_cost']:,.2f}")
print(f"Savings: ${opt['savings']:,.2f} ({opt['savings_percentage']:.1f}%)")
```

### Test 2: Generate JSON Export
```python
import json
from datetime import datetime

export = {
    'report_metadata': {
        'generated_at': datetime.now().isoformat(),
        'report_type': 'formulation_optimization',
        'version': '1.0'
    },
    'item_details': item_info,
    'optimization_summary': optimization_data['optimization_result'],
    'batch_allocation': optimization_data['optimized_selection'],
    'compliance': optimization_data['constraints_satisfied']
}

print(json.dumps(export, indent=2, default=str))
```

### Test 3: Generate Recommendations
```python
# Test recommendation generation
recommendations = []

# Simulate partial fulfillment
test_data = {'optimization_result': {'status': 'PARTIAL'}}
if test_data['optimization_result']['status'] == 'PARTIAL':
    recommendations.append({
        'priority': 'HIGH',
        'category': 'INVENTORY',
        'message': 'Insufficient stock to fulfill complete order.',
        'action': 'Create Purchase Order'
    })

# Simulate near-expiry batch
from datetime import datetime, timedelta
threshold = datetime.now() + timedelta(days=30)
test_expiry = datetime.strptime('2024-02-01', '%Y-%m-%d')
if test_expiry <= threshold:
    recommendations.append({
        'priority': 'MEDIUM',
        'category': 'EXPIRY',
        'message': 'Batch expires within 30 days',
        'action': 'Prioritize usage'
    })

print("Recommendations:")
for r in recommendations:
    print(f"  [{r['priority']}] {r['category']}: {r['message']}")
    print(f"         Action: {r['action']}")
```

### Test 4: Batch Allocation Table
```python
# Format allocation as table
allocations = optimization_data['optimized_selection']
golden_number = 2311

print("Batch Allocation:")
print("-" * 90)
print(f"{'Batch ID':<20} {'Qty':>10} {'Unit Price':>12} {'Batch Cost':>12} {'Expiry':>12} {'Golden':>8}")
print("-" * 90)

total_qty = 0
total_cost = 0

for alloc in allocations:
    batch_golden = alloc['batch_id'].split('-')[1] if '-' in alloc['batch_id'] else ''
    is_golden = 'Yes' if batch_golden == str(golden_number) else 'No'
    
    print(f"{alloc['batch_id']:<20} {alloc['allocated_qty']:>10} ${alloc['unit_price']:>10.2f} ${alloc['batch_cost']:>10.2f} {alloc['expiry_date']:>12} {is_golden:>8}")
    total_qty += alloc['allocated_qty']
    total_cost += alloc['batch_cost']

print("-" * 90)
print(f"{'TOTAL':<20} {total_qty:>10} {'':<12} ${total_cost:>10.2f}")
```

---

## 7. TEST PLAN

| Test ID | Test Case | Input | Expected Output | Pass Criteria |
|---------|-----------|-------|-----------------|---------------|
| RPT-001 | Text report generation | Optimization result | Formatted text | Contains all sections |
| RPT-002 | JSON export | Optimization result | Valid JSON | Parses without error |
| RPT-003 | Allocation table | 3 allocations | ASCII table | Correct totals |
| RPT-004 | Compliance status | All pass | [PASS] markers | Green indicators |
| RPT-005 | Compliance failed | TDS fails | [FAIL] markers | Red indicators |
| RPT-006 | Recommendations - partial | PARTIAL status | Inventory warning | Correct priority |
| RPT-007 | Recommendations - expiry | Near-expiry batch | Expiry warning | 30-day threshold |
| RPT-008 | What-if table | 3 scenarios | Comparison table | Shows differences |
| RPT-009 | Save to ERPNext | Report data | Note created | Returns docname |
| RPT-010 | Email report | Recipients list | Email sent | No errors |

---

## 8. INTEGRATION WITH ORCHESTRATOR

### Complete Pipeline Flow:
```
ORCHESTRATOR receives user request
    |
    v
Phase 1: FORMULATION_READER
    - Extract item_code, golden_number, required_qty
    |
    v
Phase 2: BATCH_SELECTOR  
    - Get available batches sorted by golden + FEFO
    |
    v
Phase 3: TDS_COMPLIANCE_CHECKER
    - Validate batches against TDS specifications
    |
    v
Phase 4: COST_CALCULATOR
    - Get pricing for each batch
    |
    v
Phase 5: OPTIMIZATION_ENGINE
    - Optimize allocation with cost tolerance
    - Generate what-if scenarios
    |
    v
Phase 6: REPORT_GENERATOR (THIS AGENT)
    - Consolidate all results
    - Generate formatted reports
    - Provide recommendations
    - Export/save as needed
    |
    v
Return to user
```

### Orchestrator Prompt Template:
```
You are an AI orchestrator for aloe powder formulation optimization.

User Request: "Optimize batch selection for 150kg of POLVO-ALOE-200X-TAN"

Execute the following sub-agents in sequence:
1. Call FORMULATION_READER to get item details
2. Call BATCH_SELECTOR to get available batches
3. Call TDS_COMPLIANCE_CHECKER to validate batches
4. Call COST_CALCULATOR to get pricing
5. Call OPTIMIZATION_ENGINE to optimize selection
6. Call REPORT_GENERATOR to create final report

Return the final optimization report to the user.
```

---

## 9. RAVEN SKILL REGISTRATION

```python
# skill: report_generator_skill
def report_generator_skill(optimization_result, item_info, output_format='text'):
    """
    Generate optimization reports in various formats.
    
    Args:
        optimization_result: Output from OPTIMIZATION_ENGINE
        item_info: Item details from FORMULATION_READER
        output_format: 'text', 'json', 'both', or 'email'
    
    Returns:
        Generated report(s) in requested format
    """
    result = {}
    
    if output_format in ['text', 'both']:
        result['text_report'] = build_summary_report(
            optimization_result,
            item_info,
            {'required_qty': optimization_result.get('required_qty', 0)}
        )
    
    if output_format in ['json', 'both']:
        result['json_export'] = build_json_export(
            optimization_result,
            item_info,
            {'required_qty': optimization_result.get('required_qty', 0)}
        )
    
    # Always include recommendations
    result['recommendations'] = generate_recommendations(
        optimization_result,
        optimization_result.get('constraints_satisfied', {})
    )
    
    return result
```

---

## 10. ERROR HANDLING

| Error Condition | Handling Strategy | Return Value |
|-----------------|-------------------|---------------|
| Missing optimization data | Return error report | status: 'ERROR' |
| Invalid JSON serialization | Use default=str | Fallback serialization |
| Email send failure | Log error, continue | Warning in result |
| Note creation failure | Log error, continue | Warning in result |
| Missing item info | Use defaults | Partial report |

---

END OF PHASE 6 - REPORT_GENERATOR SPECIFICATION

================================================================================
                    ALL 6 PHASES COMPLETE - AI AGENT READY FOR DEVELOPMENT
================================================================================

