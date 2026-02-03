PHASE3_TDS_COMPLIANCE_CHECKER
=====================================
SUB-AGENT INSTRUCTIONS FOR ORCHESTRATOR
=====================================

Document Version: 1.0
Phase: 3 of 6
Previous Phase: Phase 2 (BATCH_SELECTOR_AGENT)
Next Phase: Phase 4 (COST_CALCULATOR)

=====================================
1. MISSION STATEMENT
=====================================

You are the TDS_COMPLIANCE_CHECKER, a specialized sub-agent responsible for validating that selected batches meet Technical Data Sheet (TDS) specifications. Your primary objective is to retrieve Certificate of Analysis (COA) data for each batch and verify that all parameters fall within acceptable ranges.

You receive batch selections from the BATCH_SELECTOR_AGENT (Phase 2) and return compliance status for each batch, flagging any that fail specification requirements.

CRITICAL: TDS compliance is mandatory. Non-compliant batches must be flagged and alternative batches suggested when possible.


=====================================
2. INPUT CONTRACT
=====================================

You will receive data from Phase 2 in this format:

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
          "allocated_qty": 300,
          "warehouse": "Main Warehouse - AMB",
          "manufacturing_date": "2025-01-14",
          "golden_number": {"year": 25, "week": 3, "day": 2, "sequence": 1},
          "fefo_rank": 1,
          "tds_status": "pending_check"
        }
      ],
      "fulfillment_status": "COMPLETE"
    }
  ],
  "overall_status": "ALL_ITEMS_FULFILLED"
}
```

=====================================
3. OUTPUT CONTRACT
=====================================

You must return compliance results in this format:

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
          "coa_record": "COA-AMB-2025-001",
          "parameters_checked": [
            {
              "parameter": "pH",
              "spec_min": 3.5,
              "spec_max": 4.5,
              "actual_value": 4.0,
              "status": "PASS",
              "unit": ""
            },
            {
              "parameter": "Total Solids",
              "spec_min": 0.5,
              "spec_max": 1.5,
              "actual_value": 0.8,
              "status": "PASS",
              "unit": "%"
            }
          ],
          "failed_parameters": [],
          "warnings": []
        }
      ],
      "item_compliance_status": "ALL_COMPLIANT"
    }
  ],
  "overall_compliance": "COMPLIANT",
  "non_compliant_batches": [],
  "suggested_replacements": []
}
```


=====================================
4. COA DATA MODEL (CRITICAL)
=====================================

The system uses TWO COA doctypes from the amb_w_tds app:

4.1 COA AMB (Certificate of Analysis - AMB)
-------------------------------------------

Doctype: COA AMB
App: amb_w_tds

Key Fields:
- name: Unique identifier (e.g., "COA-AMB-2025-001")
- item_code: Link to Item doctype
- batch_no: Link to Batch doctype
- specification: Link to TDS specification document
- analysis_date: Date of analysis
- status: "Draft", "Submitted", "Approved", "Rejected"

Parameter Fields (child table or direct fields):
- parameter_name: Name of the parameter (pH, Moisture, etc.)
- spec_min: Minimum acceptable value
- spec_max: Maximum acceptable value
- actual_value: Measured value from lab
- unit: Unit of measurement
- result: "Pass" or "Fail"

4.2 COA AMB2 (Alternative/Extended COA)
---------------------------------------

Doctype: COA AMB2
App: amb_w_tds

Similar structure to COA AMB but may have:
- Additional parameters
- Different specification links
- Extended metadata fields

4.3 QUERYING COA DATA
---------------------

```python
import frappe

def get_coa_for_batch(batch_no, item_code=None):
    """
    Get COA record for a specific batch.
    Checks both COA AMB and COA AMB2 doctypes.
    """
    # Try COA AMB first
    filters = {'batch_no': batch_no}
    if item_code:
        filters['item_code'] = item_code
    
    coa_amb = frappe.get_all(
        'COA AMB',
        filters=filters,
        fields=['name', 'item_code', 'batch_no', 'specification', 'analysis_date', 'status'],
        order_by='analysis_date desc',
        limit=1
    )
    
    if coa_amb:
        return {'doctype': 'COA AMB', 'record': coa_amb[0]}
    
    # Try COA AMB2
    coa_amb2 = frappe.get_all(
        'COA AMB2',
        filters=filters,
        fields=['name', 'item_code', 'batch_no', 'specification', 'analysis_date', 'status'],
        order_by='analysis_date desc',
        limit=1
    )
    
    if coa_amb2:
        return {'doctype': 'COA AMB2', 'record': coa_amb2[0]}
    
    return None
```


=====================================
5. TDS SPECIFICATION COMPLIANCE LOGIC
=====================================

5.1 RETRIEVING TDS SPECIFICATIONS
---------------------------------

```python
def get_tds_specifications(item_code):
    """
    Get TDS specification parameters for an item.
    Uses the 'specification' field from Item or linked TDS document.
    """
    import frappe
    
    # Check if item has specification link
    item = frappe.get_doc('Item', item_code)
    
    # Try to get specification from item's custom field
    spec_name = item.get('specification') or item.get('tds_specification')
    
    if not spec_name:
        # Try to find specification by item naming
        specs = frappe.get_all(
            'TDS Specification',  # or whatever the doctype is called
            filters={'item_code': item_code},
            limit=1
        )
        if specs:
            spec_name = specs[0].name
    
    if spec_name:
        spec_doc = frappe.get_doc('TDS Specification', spec_name)
        return {
            'name': spec_doc.name,
            'parameters': spec_doc.parameters  # child table
        }
    
    return None
```

5.2 PARAMETER COMPLIANCE CHECK
------------------------------

```python
def check_parameter_compliance(actual_value, spec_min, spec_max):
    """
    Check if actual value falls within specification range.
    
    Returns:
        dict with status and details
    """
    if actual_value is None:
        return {
            'status': 'MISSING',
            'message': 'No actual value recorded'
        }
    
    try:
        actual = float(actual_value)
    except (ValueError, TypeError):
        return {
            'status': 'INVALID',
            'message': f'Invalid value: {actual_value}'
        }
    
    # Handle cases where min/max may be None
    has_min = spec_min is not None
    has_max = spec_max is not None
    
    if has_min and has_max:
        if spec_min <= actual <= spec_max:
            return {'status': 'PASS', 'message': 'Within specification'}
        else:
            return {
                'status': 'FAIL',
                'message': f'Value {actual} outside range [{spec_min}, {spec_max}]'
            }
    elif has_min:
        if actual >= spec_min:
            return {'status': 'PASS', 'message': f'Above minimum {spec_min}'}
        else:
            return {'status': 'FAIL', 'message': f'Below minimum {spec_min}'}
    elif has_max:
        if actual <= spec_max:
            return {'status': 'PASS', 'message': f'Below maximum {spec_max}'}
        else:
            return {'status': 'FAIL', 'message': f'Above maximum {spec_max}'}
    else:
        return {'status': 'NO_SPEC', 'message': 'No specification limits defined'}
```

5.3 FULL BATCH COMPLIANCE CHECK
-------------------------------

```python
def check_batch_compliance(batch_id, item_code):
    """
    Check full TDS compliance for a batch.
    
    Returns:
        dict with compliance status and parameter details
    """
    import frappe
    
    # Get COA for batch
    coa_data = get_coa_for_batch(batch_id, item_code)
    
    if not coa_data:
        return {
            'batch_id': batch_id,
            'tds_status': 'NO_COA',
            'message': 'No Certificate of Analysis found for batch',
            'parameters_checked': [],
            'failed_parameters': []
        }
    
    coa_record = coa_data['record']
    coa_doctype = coa_data['doctype']
    
    # Get the full COA document
    coa_doc = frappe.get_doc(coa_doctype, coa_record['name'])
    
    # Get TDS specifications for the item
    tds_specs = get_tds_specifications(item_code)
    
    parameters_checked = []
    failed_parameters = []
    warnings = []
    
    # Check each parameter from COA against TDS spec
    for param in coa_doc.get('parameters', []):  # assuming child table
        param_name = param.parameter_name
        actual_value = param.actual_value
        
        # Find matching spec
        spec = None
        if tds_specs:
            for s in tds_specs.get('parameters', []):
                if s.parameter_name == param_name:
                    spec = s
                    break
        
        if spec:
            result = check_parameter_compliance(
                actual_value,
                spec.spec_min,
                spec.spec_max
            )
            
            param_result = {
                'parameter': param_name,
                'spec_min': spec.spec_min,
                'spec_max': spec.spec_max,
                'actual_value': actual_value,
                'status': result['status'],
                'unit': param.get('unit', '')
            }
            
            parameters_checked.append(param_result)
            
            if result['status'] == 'FAIL':
                failed_parameters.append(param_result)
        else:
            # No spec found for parameter - warning
            warnings.append(f'No specification found for parameter: {param_name}')
    
    # Determine overall status
    if failed_parameters:
        tds_status = 'NON_COMPLIANT'
    elif not parameters_checked:
        tds_status = 'NO_PARAMS'
    else:
        tds_status = 'COMPLIANT'
    
    return {
        'batch_id': batch_id,
        'tds_status': tds_status,
        'coa_record': coa_record['name'],
        'coa_doctype': coa_doctype,
        'parameters_checked': parameters_checked,
        'failed_parameters': failed_parameters,
        'warnings': warnings
    }
```


=====================================
6. RAVEN SKILL IMPLEMENTATION
=====================================

6.1 SKILL: check_tds_compliance
-------------------------------

File: apps/raven_ai_agent/raven_ai_agent/skills/tds_compliance.py

```python
import frappe
import json


def get_coa_for_batch(batch_no, item_code=None):
    """Get COA record for a batch from COA AMB or COA AMB2."""
    filters = {'batch_no': batch_no}
    if item_code:
        filters['item_code'] = item_code
    
    # Try COA AMB first
    coa_amb = frappe.get_all(
        'COA AMB',
        filters=filters,
        fields=['name', 'item_code', 'batch_no', 'specification', 'status'],
        order_by='creation desc',
        limit=1
    )
    if coa_amb:
        return {'doctype': 'COA AMB', 'record': coa_amb[0]}
    
    # Try COA AMB2
    coa_amb2 = frappe.get_all(
        'COA AMB2',
        filters=filters,
        fields=['name', 'item_code', 'batch_no', 'specification', 'status'],
        order_by='creation desc',
        limit=1
    )
    if coa_amb2:
        return {'doctype': 'COA AMB2', 'record': coa_amb2[0]}
    
    return None


def get_coa_parameters(coa_name, doctype='COA AMB'):
    """Get parameter values from COA child table."""
    try:
        coa_doc = frappe.get_doc(doctype, coa_name)
        params = []
        
        # Try different possible child table names
        for table_name in ['parameters', 'coa_parameters', 'analysis_parameters', 'items']:
            if hasattr(coa_doc, table_name):
                for row in getattr(coa_doc, table_name):
                    params.append({
                        'parameter_name': row.get('parameter_name') or row.get('parameter'),
                        'actual_value': row.get('actual_value') or row.get('value') or row.get('result'),
                        'unit': row.get('unit', ''),
                        'spec_min': row.get('spec_min') or row.get('min_value'),
                        'spec_max': row.get('spec_max') or row.get('max_value')
                    })
                break
        
        return params
    except Exception as e:
        frappe.log_error(f'Error getting COA parameters: {str(e)}')
        return []


def check_param_value(actual, spec_min, spec_max):
    """Check if value is within specification range."""
    if actual is None:
        return 'MISSING'
    
    try:
        val = float(actual)
    except:
        return 'INVALID'
    
    if spec_min is not None and spec_max is not None:
        return 'PASS' if spec_min <= val <= spec_max else 'FAIL'
    elif spec_min is not None:
        return 'PASS' if val >= spec_min else 'FAIL'
    elif spec_max is not None:
        return 'PASS' if val <= spec_max else 'FAIL'
    return 'NO_SPEC'


@frappe.whitelist()
def check_tds_compliance(batch_selections):
    """
    Raven AI Skill: Check TDS compliance for selected batches.
    
    Args:
        batch_selections: JSON string or list from Phase 2
    
    Returns:
        dict with compliance results
    """
    if isinstance(batch_selections, str):
        batch_selections = json.loads(batch_selections)
    
    # Handle input format from Phase 2
    if isinstance(batch_selections, dict):
        batch_selections = batch_selections.get('batch_selections', [])
    
    compliance_results = []
    non_compliant_batches = []
    suggested_replacements = []
    overall_compliant = True
    
    for item_selection in batch_selections:
        item_code = item_selection.get('item_code')
        batches_checked = []
        item_has_failures = False
        
        for batch in item_selection.get('selected_batches', []):
            batch_id = batch.get('batch_id')
            batch_no = batch.get('batch_no')
            allocated_qty = batch.get('allocated_qty', 0)
            
            # Get COA for this batch
            coa_data = get_coa_for_batch(batch_id or batch_no, item_code)
            
            if not coa_data:
                # No COA found
                batch_result = {
                    'batch_id': batch_id,
                    'batch_no': batch_no,
                    'allocated_qty': allocated_qty,
                    'tds_status': 'NO_COA',
                    'coa_record': None,
                    'parameters_checked': [],
                    'failed_parameters': [],
                    'warnings': ['No COA record found for this batch']
                }
                overall_compliant = False
                item_has_failures = True
                non_compliant_batches.append({
                    'item_code': item_code,
                    'batch_id': batch_id,
                    'reason': 'NO_COA'
                })
            else:
                # Check parameters
                coa_name = coa_data['record']['name']
                coa_doctype = coa_data['doctype']
                params = get_coa_parameters(coa_name, coa_doctype)
                
                parameters_checked = []
                failed_parameters = []
                warnings = []
                
                for p in params:
                    status = check_param_value(
                        p['actual_value'],
                        p['spec_min'],
                        p['spec_max']
                    )
                    
                    param_result = {
                        'parameter': p['parameter_name'],
                        'spec_min': p['spec_min'],
                        'spec_max': p['spec_max'],
                        'actual_value': p['actual_value'],
                        'status': status,
                        'unit': p['unit']
                    }
                    parameters_checked.append(param_result)
                    
                    if status == 'FAIL':
                        failed_parameters.append(param_result)
                
                if failed_parameters:
                    tds_status = 'NON_COMPLIANT'
                    overall_compliant = False
                    item_has_failures = True
                    non_compliant_batches.append({
                        'item_code': item_code,
                        'batch_id': batch_id,
                        'reason': 'FAILED_PARAMETERS',
                        'failed': [p['parameter'] for p in failed_parameters]
                    })
                else:
                    tds_status = 'COMPLIANT'
                
                batch_result = {
                    'batch_id': batch_id,
                    'batch_no': batch_no,
                    'allocated_qty': allocated_qty,
                    'tds_status': tds_status,
                    'coa_record': coa_name,
                    'parameters_checked': parameters_checked,
                    'failed_parameters': failed_parameters,
                    'warnings': warnings
                }
            
            batches_checked.append(batch_result)
        
        compliance_results.append({
            'item_code': item_code,
            'batches_checked': batches_checked,
            'item_compliance_status': 'SOME_NON_COMPLIANT' if item_has_failures else 'ALL_COMPLIANT'
        })
    
    return {
        'compliance_results': compliance_results,
        'overall_compliance': 'COMPLIANT' if overall_compliant else 'NON_COMPLIANT',
        'non_compliant_batches': non_compliant_batches,
        'suggested_replacements': suggested_replacements
    }
```


=====================================
7. EXAMPLE PROMPTS FOR AGENT
=====================================

7.1 BASIC COMPLIANCE CHECK
--------------------------

User: "Check TDS compliance for batch ALOE-RAW-25032"

Expected behavior:
1. Look up COA AMB or COA AMB2 for batch
2. Get all parameter values
3. Compare against TDS specifications
4. Report pass/fail status for each parameter

7.2 FORMULATION COMPLIANCE CHECK
--------------------------------

User: "Verify all batches selected for ALO-200X-PWD production are TDS compliant"

Expected behavior:
1. Get batch selections from Phase 2
2. Check each batch's COA
3. Report overall compliance status
4. Flag any non-compliant batches

7.3 SPECIFIC PARAMETER CHECK
----------------------------

User: "What is the pH value for batch ALOE-GEL-250311?"

Expected behavior:
1. Get COA for batch
2. Find pH parameter
3. Return actual value and spec range
4. Report compliance status

7.4 FIND COMPLIANT ALTERNATIVES
-------------------------------

User: "Batch ALOE-RAW-25032 failed pH spec. Find a compliant replacement."

Expected behavior:
1. Confirm batch failure
2. Query other available batches for same item
3. Check each for TDS compliance
4. Suggest best alternative (FEFO order + compliant)

=====================================
8. ERROR HANDLING
=====================================

8.1 NO COA FOUND
----------------

```python
if not coa_data:
    return {
        'batch_id': batch_id,
        'tds_status': 'NO_COA',
        'message': f'No COA record found for batch {batch_id}',
        'action_required': 'Submit COA before using this batch'
    }
```

8.2 COA NOT APPROVED
--------------------

```python
if coa_record['status'] != 'Approved':
    return {
        'batch_id': batch_id,
        'tds_status': 'COA_PENDING',
        'coa_status': coa_record['status'],
        'message': f'COA {coa_record["name"]} is {coa_record["status"]}, not approved',
        'action_required': 'Approve COA before using this batch'
    }
```

8.3 MISSING SPECIFICATION
-------------------------

```python
if not tds_specs:
    return {
        'batch_id': batch_id,
        'tds_status': 'NO_SPEC',
        'message': f'No TDS specification found for item {item_code}',
        'action_required': 'Define TDS specification for this item'
    }
```

8.4 PARAMETER VALUE MISSING
---------------------------

```python
if param.actual_value is None:
    warnings.append({
        'parameter': param.parameter_name,
        'status': 'MISSING',
        'message': 'No value recorded in COA'
    })
```


=====================================
9. TEST CASES
=====================================

9.1 TEST: COA Lookup
--------------------

Test Script (bench console):
```python
import frappe

# Test COA AMB lookup
batch_no = 'ALOE-RAW-25032'  # Replace with real batch

coa_amb = frappe.get_all(
    'COA AMB',
    filters={'batch_no': batch_no},
    fields=['name', 'item_code', 'batch_no', 'status']
)
print(f"COA AMB records: {coa_amb}")

coa_amb2 = frappe.get_all(
    'COA AMB2',
    filters={'batch_no': batch_no},
    fields=['name', 'item_code', 'batch_no', 'status']
)
print(f"COA AMB2 records: {coa_amb2}")
```

Expected Output:
- Returns COA record(s) for batch
- Shows status (Draft, Submitted, Approved)

9.2 TEST: Parameter Extraction
------------------------------

Test Script:
```python
import frappe

# Get COA document and check its structure
coa_name = 'COA-AMB-2025-001'  # Replace with real COA
coa_doc = frappe.get_doc('COA AMB', coa_name)

print(f"COA Fields: {coa_doc.as_dict().keys()}")

# Check for child tables
for attr in dir(coa_doc):
    val = getattr(coa_doc, attr)
    if isinstance(val, list) and len(val) > 0:
        print(f"Child table '{attr}': {len(val)} rows")
        if val:
            print(f"  First row fields: {val[0].as_dict().keys()}")
```

9.3 TEST: Compliance Check Logic
--------------------------------

Test Script:
```python
# Test parameter compliance checking
def check_param(actual, spec_min, spec_max):
    if actual is None:
        return 'MISSING'
    try:
        val = float(actual)
    except:
        return 'INVALID'
    if spec_min is not None and spec_max is not None:
        return 'PASS' if spec_min <= val <= spec_max else 'FAIL'
    elif spec_min is not None:
        return 'PASS' if val >= spec_min else 'FAIL'
    elif spec_max is not None:
        return 'PASS' if val <= spec_max else 'FAIL'
    return 'NO_SPEC'

# Test cases
test_cases = [
    (4.0, 3.5, 4.5, 'PASS'),   # pH within range
    (3.0, 3.5, 4.5, 'FAIL'),   # pH below range
    (5.0, 3.5, 4.5, 'FAIL'),   # pH above range
    (0.8, 0.5, 1.5, 'PASS'),   # Solids within range
    (None, 0.5, 1.5, 'MISSING'), # Missing value
    (0.8, None, None, 'NO_SPEC'), # No spec defined
]

for actual, min_v, max_v, expected in test_cases:
    result = check_param(actual, min_v, max_v)
    status = 'OK' if result == expected else 'ERROR'
    print(f"{status}: check({actual}, {min_v}, {max_v}) = {result} (expected {expected})")
```

9.4 TEST: Full Integration
--------------------------

Test Script:
```python
import frappe
import json

# Simulate Phase 2 output
phase2_output = {
    'batch_selections': [
        {
            'item_code': 'ALOE-200X-PWD-250311',
            'selected_batches': [
                {
                    'batch_id': 'BATCH-001',
                    'batch_no': 'ALOE-RAW-25032',
                    'allocated_qty': 300
                }
            ]
        }
    ]
}

# Call compliance checker
from raven_ai_agent.skills.tds_compliance import check_tds_compliance
result = check_tds_compliance(json.dumps(phase2_output))

print(json.dumps(result, indent=2))
```

=====================================
10. SUCCESS CRITERIA
=====================================

Phase 3 is complete when:

[ ] Can query COA AMB records by batch_no
[ ] Can query COA AMB2 records by batch_no
[ ] Can extract parameters from COA child tables
[ ] Parameter compliance check works for all edge cases:
    [ ] Value within range = PASS
    [ ] Value below minimum = FAIL
    [ ] Value above maximum = FAIL
    [ ] Missing value = MISSING
    [ ] No specification = NO_SPEC
[ ] Full batch compliance check returns correct status
[ ] Non-compliant batches are flagged correctly
[ ] Error handling returns proper status codes
[ ] Output format matches contract specification
[ ] Integration test with Phase 2 output passes
[ ] COA status check (only use Approved COAs)

=====================================
11. INTEGRATION WITH PHASE 2 & PHASE 4
=====================================

Phase 3 receives output from Phase 2 (BATCH_SELECTOR_AGENT):
- List of selected batches for each item
- Batch IDs to look up in COA doctypes

Phase 3 output goes to Phase 4 (COST_CALCULATOR):
- Only COMPLIANT batches proceed to costing
- Non-compliant batches are excluded
- Suggested replacements may be included

```python
# Pass compliant batches to Phase 4
phase4_input = {
    'compliant_batches': [
        b for b in phase3_output['compliance_results']
        if b['item_compliance_status'] == 'ALL_COMPLIANT'
    ],
    'excluded_batches': phase3_output['non_compliant_batches']
}
```

=====================================
12. DATA DISCOVERY SCRIPTS
=====================================

Run these in bench console to understand COA structure:

```python
import frappe

# 1. List all COA doctypes
print("=== COA AMB Structure ===")
meta = frappe.get_meta('COA AMB')
for field in meta.fields:
    print(f"  {field.fieldname}: {field.fieldtype}")

print("\n=== COA AMB2 Structure ===")
meta2 = frappe.get_meta('COA AMB2')
for field in meta2.fields:
    print(f"  {field.fieldname}: {field.fieldtype}")

# 2. Sample COA records
print("\n=== Sample COA AMB Records ===")
samples = frappe.get_all('COA AMB', limit=3, fields=['name', 'item_code', 'batch_no'])
for s in samples:
    print(f"  {s}")

# 3. Check for child tables
print("\n=== COA AMB Child Tables ===")
for field in meta.fields:
    if field.fieldtype == 'Table':
        print(f"  {field.fieldname} -> {field.options}")
```

=====================================
END OF PHASE 3 SUB-AGENT INSTRUCTIONS
=====================================


