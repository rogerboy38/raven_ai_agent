# Phase 2 Input Format Support Report
## TDS Compliance Agent Integration

**Status:** IMPLEMENTATION REQUIRED  
**Date:** February 4, 2026  
**Author:** Matrix Agent  
**Related:** PHASE3_IMPLEMENTATION_REPORT.md, _phase_3_orchestrator_questions.md

---

## 1. Problem Statement

The TDS Compliance Agent (Phase 3) currently expects a different input format than what the Batch Selector Agent (Phase 2) produces. This creates a contract mismatch that prevents seamless workflow integration.

---

## 2. Format Comparison

### 2.1 Phase 2 Output Format (What We Receive)

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
            "week": 3,
            "day": 2,
            "sequence": 1
          },
          "fefo_rank": 1,
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

### 2.2 Current Phase 3 Expected Format (What We Need)

```json
{
  "batches": [
    {
      "batch_name": "ALO-RAW-25032",
      "qty": 300
    }
  ],
  "tds_requirements": {
    "pH": {"min": 3.5, "max": 4.5},
    "Total Solids": {"min": 0.5, "max": 1.5}
  }
}
```

---

## 3. Key Differences

| Aspect | Phase 2 Output | Phase 3 Current | Gap |
|--------|---------------|-----------------|-----|
| **Root Structure** | `batch_selections` array | `batches` array | Different key name |
| **Item Grouping** | Grouped by `item_code` | Flat batch list | Loses item context |
| **Batch Identifier** | `batch_no` or `batch_id` | `batch_name` | Different field name |
| **Quantity Field** | `allocated_qty` | `qty` | Different field name |
| **TDS Requirements** | Not included | Separate parameter | Must be provided |
| **Item Code** | Included per group | Not tracked | Lost in transformation |

---

## 4. Proposed Solution

### 4.1 Input Transformation Function

```python
def transform_phase2_input(phase2_output: Dict, tds_requirements: Dict = None) -> Dict:
    """
    Transform Phase 2 batch_selections format to Phase 3 internal format.
    
    Args:
        phase2_output: Output from Batch Selector Agent
        tds_requirements: TDS specifications (optional, can be fetched per item)
        
    Returns:
        Dict compatible with Phase 3 _validate_compliance
    """
    batches = []
    item_map = {}  # Track item_code for each batch
    
    for item_selection in phase2_output.get('batch_selections', []):
        item_code = item_selection.get('item_code')
        
        for batch in item_selection.get('selected_batches', []):
            batch_name = batch.get('batch_no') or batch.get('batch_id')
            
            transformed_batch = {
                'batch_name': batch_name,
                'qty': batch.get('allocated_qty', 0),
                # Preserve original data for enhanced output
                'item_code': item_code,
                'batch_id': batch.get('batch_id'),
                'warehouse': batch.get('warehouse'),
                'manufacturing_date': batch.get('manufacturing_date'),
                'expiry_date': batch.get('expiry_date'),
                'golden_number': batch.get('golden_number'),
                'fefo_rank': batch.get('fefo_rank')
            }
            
            batches.append(transformed_batch)
            item_map[batch_name] = item_code
    
    return {
        'batches': batches,
        'tds_requirements': tds_requirements or {},
        '_item_map': item_map,
        '_original_input': phase2_output
    }
```

### 4.2 New Action: validate_phase2_compliance

```python
def _validate_phase2_compliance(self, payload: Dict, message: AgentMessage) -> Dict:
    """
    Validate Phase 2 output directly without manual transformation.
    
    Args (in payload):
        phase2_output: Direct output from Batch Selector Agent
        tds_requirements: Optional - if not provided, fetched per item
        
    Returns:
        Compliance results grouped by item_code (matching Phase 3 output contract)
    """
    phase2_output = payload.get('phase2_output', payload)
    tds_requirements = payload.get('tds_requirements')
    
    # Transform input
    transformed = self._transform_phase2_input(phase2_output, tds_requirements)
    
    # Validate using existing logic
    validation = self._validate_compliance(transformed, message)
    
    # Restructure output to match Phase 3 output contract
    return self._format_phase3_output(validation, transformed)
```

---

## 5. Output Contract Alignment

### 5.1 Expected Phase 3 Output (Per Specification)

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
          "parameters_checked": [...],
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

### 5.2 Output Formatter Function

```python
def _format_phase3_output(self, validation: Dict, transformed: Dict) -> Dict:
    """
    Format validation results to match Phase 3 output contract.
    """
    item_map = transformed.get('_item_map', {})
    original = transformed.get('_original_input', {})
    
    # Group results by item_code
    results_by_item = {}
    
    for batch in validation.get('compliant_batches', []):
        item_code = batch.get('item_code') or item_map.get(batch.get('batch_name'))
        if item_code not in results_by_item:
            results_by_item[item_code] = {
                'item_code': item_code,
                'batches_checked': [],
                'item_compliance_status': 'ALL_COMPLIANT'
            }
        results_by_item[item_code]['batches_checked'].append({
            'batch_id': batch.get('batch_id'),
            'batch_no': batch.get('batch_name'),
            'allocated_qty': batch.get('qty'),
            'tds_status': 'COMPLIANT',
            'parameters_checked': batch.get('parameters', {}),
            'failed_parameters': [],
            'warnings': batch.get('warnings', [])
        })
    
    for batch in validation.get('non_compliant_batches', []):
        item_code = batch.get('item_code') or item_map.get(batch.get('batch_name'))
        if item_code not in results_by_item:
            results_by_item[item_code] = {
                'item_code': item_code,
                'batches_checked': [],
                'item_compliance_status': 'SOME_NON_COMPLIANT'
            }
        else:
            results_by_item[item_code]['item_compliance_status'] = 'SOME_NON_COMPLIANT'
            
        results_by_item[item_code]['batches_checked'].append({
            'batch_id': batch.get('batch_id'),
            'batch_no': batch.get('batch_name'),
            'allocated_qty': batch.get('qty'),
            'tds_status': batch.get('status', 'NON_COMPLIANT'),
            'parameters_checked': batch.get('parameters', {}),
            'failed_parameters': batch.get('failing_parameters', []),
            'warnings': batch.get('warnings', [])
        })
    
    # Determine overall compliance
    all_compliant = all(
        r['item_compliance_status'] == 'ALL_COMPLIANT' 
        for r in results_by_item.values()
    )
    
    return {
        'compliance_results': list(results_by_item.values()),
        'overall_compliance': 'COMPLIANT' if all_compliant else 'NON_COMPLIANT',
        'non_compliant_batches': validation.get('non_compliant_batches', []),
        'suggested_replacements': []  # To be populated by suggest_alternatives
    }
```

---

## 6. TDS Requirements Handling

### 6.1 Option A: Explicit TDS Requirements

```python
# Caller provides TDS requirements explicitly
payload = {
    "phase2_output": {...},
    "tds_requirements": {
        "pH": {"min": 3.5, "max": 4.5}
    }
}
```

### 6.2 Option B: Auto-Fetch from Item Specification

```python
def _get_tds_for_item(self, item_code: str) -> Dict:
    """
    Fetch TDS specifications for an item from Frappe.
    """
    # Get item's linked TDS specification
    item = frappe.get_doc('Item', item_code)
    spec_name = item.get('tds_specification')
    
    if spec_name:
        spec = frappe.get_doc('TDS Specification', spec_name)
        return {
            param.parameter_name: {
                'min': param.spec_min,
                'max': param.spec_max
            }
            for param in spec.parameters
        }
    return {}
```

### 6.3 Recommended Approach

Use **Option B** as default with **Option A** as override:

```python
def _validate_phase2_compliance(self, payload, message):
    phase2_output = payload.get('phase2_output', payload)
    explicit_tds = payload.get('tds_requirements')
    
    for item_selection in phase2_output.get('batch_selections', []):
        item_code = item_selection['item_code']
        
        # Use explicit TDS if provided, otherwise fetch from item
        tds_requirements = explicit_tds or self._get_tds_for_item(item_code)
        
        # ... validation logic
```

---

## 7. Implementation Checklist

- [ ] Add `_transform_phase2_input()` method
- [ ] Add `validate_phase2_compliance` action to process routing
- [ ] Add `_format_phase3_output()` method
- [ ] Add `_get_tds_for_item()` method for auto-fetch
- [ ] Update action routing in `process()` method
- [ ] Add unit tests for transformation
- [ ] Add integration tests for Phase 2 → Phase 3 flow
- [ ] Update PHASE3_IMPLEMENTATION_REPORT.md

---

## 8. Migration Path

### 8.1 Backward Compatibility

The existing `validate_compliance` action will continue to work with the current format. The new `validate_phase2_compliance` action provides the Phase 2-compatible interface.

### 8.2 Deprecation Plan

1. **Phase 1 (Now):** Add `validate_phase2_compliance` as new action
2. **Phase 2 (Later):** Make `validate_phase2_compliance` the default
3. **Phase 3 (Future):** Deprecate old format support

---

## 9. Example Usage

### 9.1 Direct Phase 2 Integration

```python
# Phase 2 output flows directly to Phase 3
phase2_result = batch_selector_agent.select_batches(formulation_request)

phase3_result = tds_compliance_agent.process(
    action="validate_phase2_compliance",
    payload={"phase2_output": phase2_result},
    message=agent_message
)
```

### 9.2 Orchestrator Workflow

```python
# In formulation_orchestrator
def run_compliance_check(self, batch_selections):
    return self.send_to_agent(
        agent="tds_compliance",
        action="validate_phase2_compliance",
        payload=batch_selections  # Direct pass-through
    )
```

---

**Document Version:** 1.0  
**Last Updated:** February 4, 2026  
**Status:** Ready for Implementation
