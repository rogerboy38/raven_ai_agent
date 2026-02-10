# Formulation Orchestrator - Integration Test Plan

## Document Information
- **Version**: 1.0
- **Date**: February 4, 2026
- **Author**: Raven AI Agent Development Team
- **Status**: Active

---

## 1. Overview

This Integration Test Plan covers the complete testing strategy for the Formulation Orchestrator multi-agent system. The plan ensures all phases work together seamlessly to deliver accurate production cost calculations, quality control validation, and comprehensive reporting for formulation manufacturing processes.

### 1.1 System Architecture

```
Phase 1: Input Validator -> Phase 2: BOM Exploder
        |                          |
Phase 3: Inventory Checker -> Phase 4: Cost Calculator
        |                          |
Phase 5: Optimization Engine -> Phase 6: Report Generator
```

### 1.2 Test Coverage Summary

| Phase | Component | Test ID Range | Unit Tests | Integration Tests |
|-------|-----------|---------------|------------|-------------------|
| 1 | Input Validator | VAL-001 to VAL-010 | 12 | 5 |
| 2 | BOM Exploder | BOM-001 to BOM-010 | 15 | 6 |
| 3 | Inventory Checker | INV-001 to INV-010 | 14 | 5 |
| 4 | Cost Calculator | CST-001 to CST-010 | 16 | 7 |
| 5 | Optimization Engine | OPT-001 to OPT-010 | 18 | 8 |
| 6 | Report Generator | RPT-001 to RPT-010 | 15+ | 6 |
| **Total** | | | **90+** | **37** |

---

## 2. Phase-Specific Test Cases

### 2.1 Phase 1: Input Validator (VAL-001 to VAL-010)

#### Unit Tests
| Test ID | Test Name | Description | Expected Result |
|---------|-----------|-------------|----------------|
| VAL-001 | Valid formulation item | Test valid formulation input | Pass validation |
| VAL-002 | Invalid item type | Test rejection of non-formulation | Raise ValidationError |
| VAL-003 | Quantity validation | Test positive quantity requirement | Reject zero/negative |
| VAL-004 | UOM consistency | Verify UOM matches item default | Pass or convert |
| VAL-005 | BOM existence | Confirm active BOM exists | Pass or raise error |
| VAL-006 | Batch size | Validate batch within limits | Pass validation |
| VAL-007 | Date range | Check manufacturing dates | Valid date range |
| VAL-008 | Required fields | All mandatory fields present | Pass validation |
| VAL-009 | Data types | Correct data type validation | Type matching |
| VAL-010 | Duplicate detection | Detect duplicate requests | Flag duplicates |

#### Integration Tests
- VAL-INT-001: Validation to BOM Exploder handoff
- VAL-INT-002: Error propagation to downstream phases
- VAL-INT-003: Multi-formulation batch validation
- VAL-INT-004: Concurrent validation requests
- VAL-INT-005: Validation with ERPNext live data

---

### 2.2 Phase 2: BOM Exploder (BOM-001 to BOM-010)

#### Unit Tests
| Test ID | Test Name | Description | Expected Result |
|---------|-----------|-------------|----------------|
| BOM-001 | Single-level explosion | Explode simple BOM | Flat ingredient list |
| BOM-002 | Multi-level explosion | Nested BOM handling | Recursive explosion |
| BOM-003 | Quantity per batch | Calculate scaled quantities | Accurate scaling |
| BOM-004 | UOM conversion | Handle mixed UOMs | Converted values |
| BOM-005 | Scrap factor | Include waste percentage | Adjusted quantities |
| BOM-006 | Alternative items | Handle substitute ingredients | Alternatives listed |
| BOM-007 | Sub-assembly detection | Identify sub-assemblies | Flagged items |
| BOM-008 | Circular reference | Prevent infinite loops | Error raised |
| BOM-009 | Version selection | Use correct BOM version | Version matched |
| BOM-010 | Ingredient aggregation | Combine duplicate items | Aggregated list |

#### Integration Tests
- BOM-INT-001: BOM explosion with real ERPNext BOMs
- BOM-INT-002: BOM to Inventory Checker data transfer
- BOM-INT-003: Multi-product BOM explosion batch
- BOM-INT-004: BOM with missing sub-components
- BOM-INT-005: BOM version switching mid-process
- BOM-INT-006: Large BOM stress test (100+ items)

---

### 2.3 Phase 3: Inventory Checker (INV-001 to INV-010)

#### Unit Tests
| Test ID | Test Name | Description | Expected Result |
|---------|-----------|-------------|----------------|
| INV-001 | Stock availability | Check item stock levels | Available quantity |
| INV-002 | Multi-warehouse | Aggregate across warehouses | Total stock |
| INV-003 | Reserved stock | Exclude reserved quantities | Available stock |
| INV-004 | Batch tracking | Track batch/lot numbers | Batch details |
| INV-005 | FEFO ordering | First Expiry First Out | Ordered by expiry |
| INV-006 | Shortage calculation | Calculate shortfall | Shortage amount |
| INV-007 | Reorder alerts | Trigger low stock alerts | Alert generated |
| INV-008 | Stock valuation | Calculate stock value | Valuation amount |
| INV-009 | UOM conversion | Convert stock UOMs | Converted quantity |
| INV-010 | Real-time sync | Sync with live stock | Updated values |

#### Integration Tests
- INV-INT-001: Inventory check with live ERPNext stock
- INV-INT-002: Inventory to Cost Calculator handoff
- INV-INT-003: Multi-warehouse picking optimization
- INV-INT-004: Stock reservation during calculation
- INV-INT-005: Inventory with pending transactions

---

### 2.4 Phase 4: Cost Calculator (CST-001 to CST-010)

#### Unit Tests
| Test ID | Test Name | Description | Expected Result |
|---------|-----------|-------------|----------------|
| CST-001 | Material cost | Calculate raw material cost | Total material cost |
| CST-002 | Labor cost | Include labor charges | Labor amount |
| CST-003 | Overhead allocation | Distribute overhead costs | Allocated overhead |
| CST-004 | Scrap cost | Calculate waste cost | Scrap amount |
| CST-005 | Multi-currency | Handle currency conversion | Converted costs |
| CST-006 | Cost center | Allocate to cost centers | Center breakdown |
| CST-007 | Standard vs actual | Compare cost methods | Cost comparison |
| CST-008 | Cost rollup | Roll up sub-assembly costs | Total rolled cost |
| CST-009 | Price list | Use correct price list | Listed prices |
| CST-010 | Margin calculation | Calculate profit margin | Margin percentage |

#### Integration Tests
- CST-INT-001: Cost calculation with real pricing
- CST-INT-002: Cost to Optimization Engine handoff
- CST-INT-003: Cost recalculation on price changes
- CST-INT-004: Cost with multiple price lists
- CST-INT-005: Cost center P&L integration
- CST-INT-006: Cost with pending purchase orders
- CST-INT-007: Full cost breakdown report

---

### 2.5 Phase 5: Optimization Engine (OPT-001 to OPT-010)

#### Unit Tests
| Test ID | Test Name | Description | Expected Result |
|---------|-----------|-------------|----------------|
| OPT-001 | Basic optimization | Simple batch optimization | Optimized batch |
| OPT-002 | Multi-constraint | Handle multiple constraints | Feasible solution |
| OPT-003 | Cost minimization | Minimize total cost | Lowest cost plan |
| OPT-004 | Waste minimization | Reduce material waste | Minimal waste |
| OPT-005 | Scheduling | Production scheduling | Schedule generated |
| OPT-006 | Capacity constraints | Respect capacity limits | Within capacity |
| OPT-007 | Substitution | Ingredient substitution | Alternatives used |
| OPT-008 | Batch sizing | Optimize batch sizes | Optimal batches |
| OPT-009 | Multi-product | Multiple product optimization | Combined plan |
| OPT-010 | Metrics calculation | Calculate optimization metrics | Metrics report |

#### Integration Tests
- OPT-INT-001: Full workflow optimization test
- OPT-INT-002: Optimization with real constraints
- OPT-INT-003: Optimization to Report Generator handoff
- OPT-INT-004: Re-optimization on constraint changes
- OPT-INT-005: Multi-scenario comparison
- OPT-INT-006: Optimization with inventory shortages
- OPT-INT-007: Optimization performance benchmark
- OPT-INT-008: Parallel optimization requests

---

### 2.6 Phase 6: Report Generator (RPT-001 to RPT-010)

#### Unit Tests
| Test ID | Test Name | Description | Expected Result |
|---------|-----------|-------------|----------------|
| RPT-001 | Production order | Generate production order | Valid order format |
| RPT-002 | Picking list | Generate picking list | FEFO ordered list |
| RPT-003 | ASCII cost table | Format cost breakdown | ASCII table |
| RPT-004 | ASCII picking table | Format picking list | ASCII table |
| RPT-005 | ERPNext Note | Create Note document | Note created |
| RPT-006 | Public/Private setting | Set note visibility | Correct setting |
| RPT-007 | Email sending | Send report via email | Email delivered |
| RPT-008 | HTML conversion | Convert to HTML format | Valid HTML |
| RPT-009 | Empty list handling | Handle empty datasets | Graceful handling |
| RPT-010 | Error handling | Handle generation errors | Error reported |

#### Integration Tests
- RPT-INT-001: Full report generation workflow
- RPT-INT-002: Report with ERPNext Note creation
- RPT-INT-003: Email delivery with attachments
- RPT-INT-004: Multi-format report generation
- RPT-INT-005: Report with large datasets
- RPT-INT-006: Concurrent report generation

---

## 3. End-to-End Integration Tests

### 3.1 E2E Test Matrix (E2E-001 to E2E-010)

| Test ID | Scenario | Phases | Priority |
|---------|----------|--------|----------|
| E2E-001 | Simple formulation costing | 1-2-3-4-6 | Critical |
| E2E-002 | Complex multi-level BOM | 1-2-3-4-5-6 | Critical |
| E2E-003 | Inventory shortage handling | 1-2-3-4-5-6 | High |
| E2E-004 | Multi-currency costing | 1-2-3-4-6 | High |
| E2E-005 | Batch size optimization | 1-2-3-4-5-6 | High |
| E2E-006 | Complete report generation | 1-2-3-4-5-6 | Critical |
| E2E-007 | Error recovery workflow | All | Medium |
| E2E-008 | Concurrent multi-user | All | Medium |
| E2E-009 | Performance stress test | All | Medium |
| E2E-010 | Production environment | All | Critical |

### 3.2 E2E Test Execution Order

1. **Smoke Tests** (E2E-001, E2E-006): Basic functionality
2. **Core Workflow** (E2E-002, E2E-003, E2E-004): Main use cases
3. **Optimization** (E2E-005): Advanced features
4. **Robustness** (E2E-007, E2E-008): Error handling
5. **Performance** (E2E-009, E2E-010): Load testing

---

## 4. Test Data Requirements

### 4.1 ERPNext Test Data

| Data Type | Test Items | Purpose |
|-----------|------------|--------|
| Formulation Items | FORM-001, FORM-002, FORM-003 | Input validation |
| BOM Structures | BOM-FORM-001-001, BOM-FORM-002-001 | BOM explosion |
| Warehouses | Raw Materials, WIP, Finished Goods | Inventory checks |
| Price Lists | Standard Buying, Standard Selling | Cost calculation |
| Stock Entries | Various test batches | Stock availability |

### 4.2 Mock Data Fixtures

- `fixture_valid_formulation.json`: Valid formulation input data
- `fixture_complex_bom.json`: Multi-level BOM structure
- `fixture_inventory_stock.json`: Stock levels per warehouse
- `fixture_pricing_data.json`: Item pricing information
- `fixture_optimization_params.json`: Optimization constraints

---

## 5. Test Execution Schedule

### 5.1 Automated Test Schedule

| Test Type | Frequency | Duration | Environment |
|-----------|-----------|----------|-------------|
| Unit Tests | Every commit | 5 min | CI/CD |
| Integration Tests | Daily | 30 min | Staging |
| E2E Tests | Weekly | 2 hours | Staging |
| Performance Tests | Monthly | 4 hours | Production-like |

### 5.2 Manual Test Schedule

- **UAT Testing**: Before each release
- **Regression Testing**: After major changes
- **Exploratory Testing**: Monthly

---

## 6. Test Environment Configuration

### 6.1 Required Setup

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-mock

# Configure test environment
export FRAPPE_SITE=test.site.local
export TEST_MODE=true

# Run all tests
pytest raven_ai_agent/skills/formulation_orchestrator/tests.py -v

# Run specific phase tests
pytest -k "Phase6" -v

# Run with coverage
pytest --cov=formulation_orchestrator --cov-report=html
```

### 6.2 Test Configuration File

```python
# tests/conftest.py
import pytest
from unittest.mock import Mock, patch

@pytest.fixture
def mock_frappe():
    with patch('frappe') as mock:
        mock.get_doc = Mock()
        mock.get_all = Mock()
        mock.call = Mock()
        yield mock

@pytest.fixture
def sample_formulation():
    return {
        'item_code': 'FORM-TEST-001',
        'item_name': 'Test Formulation',
        'batch_size': 100,
        'uom': 'Kg'
    }
```

---

## 7. Test Metrics and Reporting

### 7.1 Success Criteria

| Metric | Target | Current |
|--------|--------|---------|
| Unit Test Coverage | >80% | TBD |
| Integration Test Pass Rate | 100% | TBD |
| E2E Test Pass Rate | 100% | TBD |
| Performance Response Time | <5s | TBD |

### 7.2 Reporting Format

- **Daily**: Unit test results via CI/CD
- **Weekly**: Integration test summary
- **Monthly**: Full test coverage report
- **Per Release**: Complete test documentation

---

## 8. Risk Assessment

### 8.1 High-Risk Areas

| Area | Risk Level | Mitigation |
|------|------------|------------|
| BOM Circular References | High | Deep testing + validation |
| Multi-currency Conversion | Medium | Edge case testing |
| Concurrent Access | Medium | Load testing |
| ERPNext API Changes | Low | Version pinning |

### 8.2 Test Priority Matrix

```
High Priority:
- Phase handoff tests (data integrity)
- Cost calculation accuracy
- Report generation completeness

Medium Priority:
- Performance optimization
- Error recovery
- Edge case handling

Low Priority:
- UI formatting
- Logging details
- Documentation generation
```

---

## 9. Implemented Test Classes Reference

### 9.1 tests.py Test Classes (Commit 4710f82)

| Class Name | Test IDs | Description |
|------------|----------|-------------|
| TestProductionOrderReport | RPT-001, RPT-002 | Production order and picking list |
| TestASCIIFormatting | RPT-003, RPT-004 | ASCII table formatting |
| TestERPNextIntegration | RPT-005, RPT-006 | Note document creation |
| TestEmailReport | RPT-007, RPT-008 | Email functionality |
| TestReportGeneratorEdgeCases | RPT-009, RPT-010 | Edge case handling |
| TestPhase6Integration | - | Phase 5 to 6 handoff |

### 9.2 Test Execution Commands

```bash
# Run all Phase 6 tests
pytest -k "RPT" -v

# Run specific test class
pytest -k "TestProductionOrderReport" -v

# Run with verbose output
pytest tests.py::TestASCIIFormatting -v --tb=short
```

---

## 10. Appendix

### 10.1 Related Documentation

- [Phase 1 Chat](phase_1_chat.md) - Input Validator documentation
- [Phase 2 Chat](phase_2_chat.md) - BOM Exploder documentation
- [Phase 3 Chat](phase_3_chat.md) - Inventory Checker documentation
- [Phase 4 Chat](phase_4_chat.md) - Cost Calculator documentation
- [Phase 5 Chat](phase_5_chat.md) - Optimization Engine documentation
- [Phase 6 Chat](phase_6_chat.md) - Report Generator documentation
- [Technical Specs](TECH_SPEC_PHASE6_REPORT_GENERATOR.md) - Phase 6 technical specification

### 10.2 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Feb 4, 2026 | Initial test plan creation |

---

**Document Status**: Complete
**Last Updated**: February 4, 2026
**Next Review**: After Phase 6 testing completion
