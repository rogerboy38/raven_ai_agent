# Technical Specification: Phase 2 Input Format Adapter
## TDS Compliance Agent Enhancement

**Document ID:** TECH-SPEC-P3-001  
**Version:** 1.0  
**Date:** February 4, 2026  
**Author:** Matrix Agent  
**Status:** APPROVED FOR IMPLEMENTATION

---

## 1. Overview

### 1.1 Purpose

This technical specification defines the implementation requirements for adding Phase 2 input format support to the TDS Compliance Agent. The enhancement enables seamless integration between the Batch Selector Agent (Phase 2) and TDS Compliance Agent (Phase 3) in the formulation orchestrator workflow.

### 1.2 Scope

- Input transformation from Phase 2 format to Phase 3 internal format
- COA status validation (Approved-only enforcement)
- Output restructuring to match Phase 3 contract
- Suggest alternatives integration hook
- Backward compatibility with existing API

### 1.3 References

| Document | Location |
|----------|----------|
| Phase 2 Spec | `docs/project_formulation/PHASE2_BATCH_SELECTOR_AGENT.md` |
| Phase 3 Spec | `docs/project_formulation/PHASE3_TDS_COMPLIANCE_CHECKER.md` |
| Feature Spec | `docs/project_formulation/FEATURE_SUGGEST_ALTERNATIVES.md` |
| Format Report | `docs/project_formulation/PHASE2_INPUT_FORMAT_SUPPORT.md` |

---

## 2. Requirements

### 2.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-001 | Accept Phase 2 `batch_selections` format as input | HIGH |
| FR-002 | Transform input to internal validation format | HIGH |
| FR-003 | Validate COA status before parameter checking | HIGH |
| FR-004 | Group output results by `item_code` | HIGH |
| FR-005 | Return `item_compliance_status` per item group | HIGH |
| FR-006 | Auto-fetch TDS requirements from item specification | MEDIUM |
| FR-007 | Support explicit TDS requirements override | MEDIUM |
| FR-008 | Integrate with `suggest_alternatives` action | MEDIUM |
| FR-009 | Maintain backward compatibility with existing API | HIGH |

### 2.2 Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-001 | Processing time per batch | < 500ms |
| NFR-002 | Memory usage | < 50MB per request |
| NFR-003 | Error handling coverage | 100% |
| NFR-004 | Test coverage | > 90% |

---

## 3. Technical Design

### 3.1 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TDSComplianceAgent                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │ process()        │───►│ Action Router    │                   │
│  └──────────────────┘    └────────┬─────────┘                   │
│                                   │                              │
│         ┌─────────────────────────┼─────────────────────────┐   │
│         │                         │                         │   │
│         ▼                         ▼                         ▼   │
│  ┌──────────────┐    ┌────────────────────┐    ┌───────────────┐│
│  │validate_     │    │validate_phase2_    │    │suggest_       ││
│  │compliance    │    │compliance (NEW)    │    │alternatives   ││
│  │(existing)    │    │                    │    │(NEW)          ││
│  └──────────────┘    └─────────┬──────────┘    └───────────────┘│
│                                │                                 │
│                    ┌───────────┴───────────┐                    │
│                    ▼                       ▼                    │
│         ┌──────────────────┐    ┌──────────────────┐            │
│         │_transform_       │    │_format_phase3_   │            │
│         │phase2_input()    │    │output()          │            │
│         └──────────────────┘    └──────────────────┘            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow

```
Phase 2 Output                    Phase 3 Processing                    Phase 3 Output
─────────────                    ──────────────────                    ──────────────

batch_selections[]    ──►    _transform_phase2_input()
       │                              │
       │                              ▼
       │                     Internal batch list
       │                              │
       │                              ▼
       │                     _validate_coa_status()
       │                              │
       │                              ▼
       │                     _validate_compliance()
       │                              │
       │                              ▼
       │                     _format_phase3_output()    ──►    compliance_results[]
       │                              │
       │                              ▼
       │                     _suggest_alternatives()   ──►    suggested_replacements[]
```

---

## 4. API Specification

### 4.1 New Action: validate_phase2_compliance

#### Request

```python
{
    "action": "validate_phase2_compliance",
    "payload": {
        # Option 1: Direct Phase 2 output
        "batch_selections": [...],
        "overall_status": "...",
        
        # Option 2: Wrapped Phase 2 output
        "phase2_output": {
            "batch_selections": [...],
            "overall_status": "..."
        },
        
        # Optional: Override TDS requirements
        "tds_requirements": {
            "parameter_name": {"min": float, "max": float}
        },
        
        # Optional: Configuration
        "options": {
            "require_approved_coa": true,      # Default: true
            "auto_fetch_tds": true,            # Default: true
            "include_suggestions": false,       # Default: false
            "max_suggestions": 5               # Default: 5
        }
    }
}
```

#### Response

```python
{
    "compliance_results": [
        {
            "item_code": "ALO-LEAF-GEL-RAW",
            "batches_checked": [
                {
                    "batch_id": "BATCH-2025-001",
                    "batch_no": "ALO-RAW-25032",
                    "allocated_qty": 300,
                    "tds_status": "COMPLIANT",  # COMPLIANT, NON_COMPLIANT, NO_COA, COA_PENDING
                    "coa_record": "COA-AMB-2025-001",
                    "coa_status": "Approved",
                    "parameters_checked": [
                        {
                            "parameter": "pH",
                            "spec_min": 3.5,
                            "spec_max": 4.5,
                            "actual_value": 4.0,
                            "status": "PASS",
                            "unit": ""
                        }
                    ],
                    "failed_parameters": [],
                    "warnings": []
                }
            ],
            "item_compliance_status": "ALL_COMPLIANT"  # ALL_COMPLIANT, SOME_NON_COMPLIANT, ALL_NON_COMPLIANT
        }
    ],
    "overall_compliance": "COMPLIANT",  # COMPLIANT, NON_COMPLIANT
    "non_compliant_batches": [],
    "suggested_replacements": [],
    "summary": {
        "total_items": 1,
        "total_batches": 1,
        "compliant_count": 1,
        "non_compliant_count": 0,
        "compliance_rate": 100.0
    }
}
```

### 4.2 New Action: suggest_alternatives

#### Request

```python
{
    "action": "suggest_alternatives",
    "payload": {
        "non_compliant_batch": "ALO-RAW-25032",
        "item_code": "ALO-LEAF-GEL-RAW",
        "failed_parameters": [
            {
                "parameter": "Aloin",
                "actual_value": 2.5,
                "spec_min": 0.5,
                "spec_max": 2.0,
                "status": "FAIL_HIGH"
            }
        ],
        "required_quantity": 300,
        "tds_requirements": {...},
        "options": {
            "include_blends": true,
            "max_alternatives": 5,
            "fefo_priority": true,
            "same_warehouse_only": false
        }
    }
}
```

#### Response

```python
{
    "success": true,
    "alternatives": [
        {
            "type": "single_batch",
            "batch_id": "BATCH-2025-003",
            "batch_no": "ALO-RAW-25034",
            "item_code": "ALO-LEAF-GEL-RAW",
            "available_qty": 500,
            "compliance_score": 100,
            "parameters": {...},
            "expiry_date": "2026-03-15",
            "warehouse": "Main Warehouse - AMB",
            "recommendation": "Direct replacement - all parameters compliant"
        }
    ],
    "analysis": {
        "total_batches_evaluated": 8,
        "compliant_alternatives_found": 2,
        "blend_options_found": 1,
        "limiting_parameter": "Aloin"
    }
}
```

---

## 5. Implementation Details

### 5.1 File Modifications

**File:** `raven_ai_agent/skills/formulation_orchestrator/agents/tds_compliance.py`

### 5.2 New Methods

#### 5.2.1 _transform_phase2_input

```python
def _transform_phase2_input(self, phase2_output: Dict) -> Dict:
    """
    Transform Phase 2 batch_selections format to internal format.
    
    Args:
        phase2_output: Raw output from Batch Selector Agent
        
    Returns:
        Dict with:
            - batches: List of batch dicts in internal format
            - _item_map: Dict mapping batch_name to item_code
            - _original_input: Original Phase 2 output for reference
    """
    # Handle both wrapped and direct formats
    if 'phase2_output' in phase2_output:
        phase2_output = phase2_output['phase2_output']
    
    batches = []
    item_map = {}
    
    for item_selection in phase2_output.get('batch_selections', []):
        item_code = item_selection.get('item_code')
        
        for batch in item_selection.get('selected_batches', []):
            batch_name = batch.get('batch_no') or batch.get('batch_id')
            
            batches.append({
                'batch_name': batch_name,
                'qty': batch.get('allocated_qty', 0),
                'item_code': item_code,
                'batch_id': batch.get('batch_id'),
                'warehouse': batch.get('warehouse'),
                'manufacturing_date': batch.get('manufacturing_date'),
                'expiry_date': batch.get('expiry_date'),
                'golden_number': batch.get('golden_number'),
                'fefo_rank': batch.get('fefo_rank')
            })
            
            item_map[batch_name] = item_code
    
    return {
        'batches': batches,
        '_item_map': item_map,
        '_original_input': phase2_output
    }
```

#### 5.2.2 _validate_coa_status

```python
def _validate_coa_status(self, batch_name: str, require_approved: bool = True) -> Dict:
    """
    Validate COA exists and has acceptable status.
    
    Args:
        batch_name: Batch identifier
        require_approved: If True, only 'Approved' status is valid
        
    Returns:
        Dict with:
            - valid: bool
            - coa_record: COA name if found
            - coa_status: COA status
            - reason: Error reason if invalid
    """
    coa_params = get_batch_coa_parameters(batch_name)
    
    if not coa_params:
        return {
            'valid': False,
            'coa_record': None,
            'coa_status': None,
            'reason': 'NO_COA',
            'action_required': 'Submit COA before using this batch'
        }
    
    # Extract COA record info (implementation depends on formulation_reader)
    coa_info = coa_params.get('_coa_info', {})
    coa_status = coa_info.get('status', 'Unknown')
    coa_record = coa_info.get('name')
    
    if require_approved and coa_status != 'Approved':
        return {
            'valid': False,
            'coa_record': coa_record,
            'coa_status': coa_status,
            'reason': 'COA_PENDING',
            'action_required': f'COA is {coa_status}, approval required before use'
        }
    
    return {
        'valid': True,
        'coa_record': coa_record,
        'coa_status': coa_status,
        'coa_params': coa_params
    }
```

#### 5.2.3 _get_tds_for_item

```python
def _get_tds_for_item(self, item_code: str) -> Dict:
    """
    Fetch TDS specifications for an item from Frappe.
    
    Args:
        item_code: Item code to fetch TDS for
        
    Returns:
        Dict of parameter specifications {param_name: {min, max}}
    """
    try:
        item = frappe.get_doc('Item', item_code)
        spec_name = item.get('tds_specification') or item.get('specification')
        
        if not spec_name:
            # Try to find by item code pattern
            specs = frappe.get_all(
                'TDS Specification',
                filters={'item_code': item_code},
                limit=1
            )
            if specs:
                spec_name = specs[0].name
        
        if spec_name:
            spec_doc = frappe.get_doc('TDS Specification', spec_name)
            return {
                param.parameter_name: {
                    'min': param.get('spec_min'),
                    'max': param.get('spec_max'),
                    'unit': param.get('unit', '')
                }
                for param in spec_doc.get('parameters', [])
            }
    except Exception as e:
        self._log(f"Error fetching TDS for {item_code}: {e}")
    
    return {}
```

#### 5.2.4 _format_phase3_output

```python
def _format_phase3_output(
    self, 
    validation: Dict, 
    transformed: Dict,
    options: Dict = None
) -> Dict:
    """
    Format validation results to match Phase 3 output contract.
    
    Args:
        validation: Result from _validate_compliance
        transformed: Transformed input with metadata
        options: Processing options
        
    Returns:
        Phase 3 compliant output structure
    """
    options = options or {}
    item_map = transformed.get('_item_map', {})
    
    # Group results by item_code
    results_by_item = {}
    non_compliant_list = []
    
    # Process compliant batches
    for batch in validation.get('compliant_batches', []):
        item_code = batch.get('item_code') or item_map.get(batch.get('batch_name'))
        self._add_to_item_results(results_by_item, item_code, batch, 'COMPLIANT')
    
    # Process non-compliant batches
    for batch in validation.get('non_compliant_batches', []):
        item_code = batch.get('item_code') or item_map.get(batch.get('batch_name'))
        self._add_to_item_results(results_by_item, item_code, batch, batch.get('status', 'NON_COMPLIANT'))
        non_compliant_list.append({
            'item_code': item_code,
            'batch_id': batch.get('batch_id'),
            'batch_no': batch.get('batch_name'),
            'reason': batch.get('status'),
            'failed_parameters': batch.get('failing_parameters', [])
        })
    
    # Calculate summary
    total_batches = len(validation.get('compliant_batches', [])) + len(validation.get('non_compliant_batches', []))
    compliant_count = len(validation.get('compliant_batches', []))
    
    return {
        'compliance_results': list(results_by_item.values()),
        'overall_compliance': 'COMPLIANT' if not non_compliant_list else 'NON_COMPLIANT',
        'non_compliant_batches': non_compliant_list,
        'suggested_replacements': [],  # Populated by suggest_alternatives if enabled
        'summary': {
            'total_items': len(results_by_item),
            'total_batches': total_batches,
            'compliant_count': compliant_count,
            'non_compliant_count': len(non_compliant_list),
            'compliance_rate': (compliant_count / total_batches * 100) if total_batches > 0 else 0
        }
    }

def _add_to_item_results(
    self, 
    results_by_item: Dict, 
    item_code: str, 
    batch: Dict, 
    status: str
) -> None:
    """Helper to add batch to item results grouping."""
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
        'tds_status': status,
        'coa_record': batch.get('coa_record'),
        'coa_status': batch.get('coa_status'),
        'parameters_checked': self._format_parameters(batch.get('parameters', {})),
        'failed_parameters': batch.get('failing_parameters', []),
        'warnings': batch.get('warnings', [])
    })
    
    # Update item compliance status
    if status != 'COMPLIANT':
        current = results_by_item[item_code]['item_compliance_status']
        if current == 'ALL_COMPLIANT':
            results_by_item[item_code]['item_compliance_status'] = 'SOME_NON_COMPLIANT'

def _format_parameters(self, params: Dict) -> List[Dict]:
    """Convert parameters dict to list format."""
    return [
        {
            'parameter': name,
            'spec_min': data.get('spec_min'),
            'spec_max': data.get('spec_max'),
            'actual_value': data.get('value'),
            'status': data.get('status'),
            'unit': data.get('unit', '')
        }
        for name, data in params.items()
    ]
```

#### 5.2.5 _validate_phase2_compliance (Main Action)

```python
def _validate_phase2_compliance(self, payload: Dict, message: AgentMessage) -> Dict:
    """
    Validate Phase 2 output directly with full contract compliance.
    
    Args (in payload):
        batch_selections: Phase 2 output (direct or wrapped)
        tds_requirements: Optional explicit TDS requirements
        options: Processing options
        
    Returns:
        Phase 3 compliant output with compliance_results grouped by item
    """
    options = payload.get('options', {})
    explicit_tds = payload.get('tds_requirements')
    require_approved = options.get('require_approved_coa', True)
    auto_fetch_tds = options.get('auto_fetch_tds', True)
    include_suggestions = options.get('include_suggestions', False)
    
    # Transform input
    transformed = self._transform_phase2_input(payload)
    batches = transformed.get('batches', [])
    
    self._log(f"Validating {len(batches)} batches from Phase 2 output")
    self.send_status("validating_phase2", {"batch_count": len(batches)})
    
    compliant = []
    non_compliant = []
    warnings = []
    
    # Group batches by item for TDS lookup
    batches_by_item = {}
    for batch in batches:
        item_code = batch.get('item_code')
        if item_code not in batches_by_item:
            batches_by_item[item_code] = []
        batches_by_item[item_code].append(batch)
    
    # Process each item group
    for item_code, item_batches in batches_by_item.items():
        # Get TDS requirements
        if explicit_tds:
            tds_requirements = explicit_tds
        elif auto_fetch_tds:
            tds_requirements = self._get_tds_for_item(item_code)
            if not tds_requirements:
                warnings.append(f"No TDS specification found for item {item_code}")
        else:
            tds_requirements = {}
        
        # Validate each batch
        for batch in item_batches:
            batch_name = batch.get('batch_name')
            
            if not batch_name:
                non_compliant.append({
                    **batch,
                    'status': 'INVALID',
                    'reason': 'No batch name provided',
                    'action_required': 'Provide valid batch identifier'
                })
                continue
            
            # Validate COA status
            coa_validation = self._validate_coa_status(batch_name, require_approved)
            
            if not coa_validation['valid']:
                non_compliant.append({
                    **batch,
                    'status': coa_validation['reason'],
                    'coa_record': coa_validation.get('coa_record'),
                    'coa_status': coa_validation.get('coa_status'),
                    'reason': coa_validation.get('reason'),
                    'action_required': coa_validation.get('action_required')
                })
                continue
            
            # Check TDS compliance
            coa_params = coa_validation['coa_params']
            compliance = check_tds_compliance(coa_params, tds_requirements)
            
            if compliance['all_pass']:
                compliant.append({
                    **batch,
                    'status': 'COMPLIANT',
                    'coa_record': coa_validation.get('coa_record'),
                    'coa_status': coa_validation.get('coa_status'),
                    'parameters': compliance['parameters']
                })
            else:
                failing = [
                    param for param, result in compliance['parameters'].items()
                    if result.get('status') != 'PASS'
                ]
                non_compliant.append({
                    **batch,
                    'status': 'NON_COMPLIANT',
                    'coa_record': coa_validation.get('coa_record'),
                    'coa_status': coa_validation.get('coa_status'),
                    'failing_parameters': failing,
                    'parameters': compliance['parameters']
                })
    
    # Build validation result
    validation = {
        'passed': len(non_compliant) == 0 and len(compliant) > 0,
        'compliant_batches': compliant,
        'non_compliant_batches': non_compliant
    }
    
    # Format output
    result = self._format_phase3_output(validation, transformed, options)
    
    # Add suggestions if requested
    if include_suggestions and non_compliant:
        suggestions = self._get_suggestions_for_non_compliant(
            non_compliant, 
            transformed,
            options
        )
        result['suggested_replacements'] = suggestions
    
    # Add warnings
    if warnings:
        result['warnings'] = warnings
    
    self.send_status("completed", {
        "passed": validation['passed'],
        "compliant_count": len(compliant),
        "non_compliant_count": len(non_compliant)
    })
    
    return result
```

### 5.3 Updated process() Method

```python
def process(self, action: str, payload: Dict, message: AgentMessage) -> Optional[Dict]:
    """Route to specific action handler."""
    actions = {
        # Existing actions
        "validate_compliance": self._validate_compliance,
        "check_batch": self._check_single_batch,
        "compare_specs": self._compare_specs,
        "get_compliance_report": self._get_compliance_report,
        # New actions
        "validate_phase2_compliance": self._validate_phase2_compliance,
        "suggest_alternatives": self._suggest_alternatives,
    }
    
    handler = actions.get(action)
    if handler:
        return handler(payload, message)
    return None
```

---

## 6. Testing Requirements

### 6.1 Unit Tests

```python
class TestPhase2InputTransformation:
    def test_transform_direct_format(self):
        """Test transformation of direct Phase 2 output."""
        pass
    
    def test_transform_wrapped_format(self):
        """Test transformation of wrapped Phase 2 output."""
        pass
    
    def test_transform_empty_batches(self):
        """Test handling of empty batch selections."""
        pass
    
    def test_item_map_creation(self):
        """Test item_code mapping is correctly created."""
        pass


class TestCOAStatusValidation:
    def test_approved_coa_valid(self):
        """Test approved COA passes validation."""
        pass
    
    def test_pending_coa_rejected(self):
        """Test pending COA is rejected when require_approved=True."""
        pass
    
    def test_missing_coa_handled(self):
        """Test missing COA returns proper error."""
        pass


class TestPhase2Compliance:
    def test_full_compliance_flow(self):
        """Test end-to-end Phase 2 to Phase 3 flow."""
        pass
    
    def test_output_format_matches_contract(self):
        """Verify output structure matches Phase 3 contract."""
        pass
    
    def test_item_grouping(self):
        """Test results are correctly grouped by item_code."""
        pass


class TestTDSAutoFetch:
    def test_auto_fetch_enabled(self):
        """Test TDS specs are auto-fetched when enabled."""
        pass
    
    def test_explicit_override(self):
        """Test explicit TDS requirements override auto-fetch."""
        pass
```

### 6.2 Integration Tests

```python
class TestPhase2ToPhase3Integration:
    def test_batch_selector_to_tds_compliance(self):
        """Test full workflow from Phase 2 output to Phase 3 result."""
        pass
    
    def test_phase3_to_phase4_handoff(self):
        """Test Phase 3 output is compatible with Phase 4 input."""
        pass
```

---

## 7. Deployment

### 7.1 Migration Steps

1. Deploy updated `tds_compliance.py`
2. Run unit tests
3. Run integration tests
4. Update orchestrator to use `validate_phase2_compliance`
5. Monitor for errors
6. Deprecate old flow after validation period

### 7.2 Rollback Plan

1. Revert to previous `tds_compliance.py`
2. Orchestrator falls back to manual transformation
3. No data migration required (stateless)

---

## 8. Acceptance Criteria

- [ ] `validate_phase2_compliance` action accepts Phase 2 output directly
- [ ] COA status is validated before parameter checking
- [ ] Non-approved COAs are rejected with clear error message
- [ ] Output is grouped by `item_code` as per Phase 3 contract
- [ ] `item_compliance_status` is correctly calculated per item
- [ ] TDS requirements are auto-fetched when not explicitly provided
- [ ] Explicit TDS requirements override auto-fetch
- [ ] Backward compatibility maintained for existing `validate_compliance` action
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Documentation updated

---

**Document End**  
**Approved for Implementation:** February 4, 2026
