# Technical Specification: Phase 6 Report Generator

## Document Information

| Field | Value |
|-------|-------|
| **Phase** | 6 - Report Generator |
| **Status** | Ready for Implementation |
| **Version** | 1.0 |
| **Created** | 2026-02-04 |

---

## 1. Overview

### 1.1 Purpose

The Report Generator is the final phase of the Formulation Orchestrator pipeline. It transforms optimized batch selections from Phase 5 into production-ready reports.

### 1.2 Scope

- Report type definitions and structures
- Output format handlers (dict, JSON, HTML, CSV, PDF)
- Template system architecture
- Integration with Phases 1-5

---

## 2. Report Types

### 2.1 Production Report
- Batch picking list for manufacturing floor
- Sequence numbers, locations, quantities
- Expiry tracking and warnings

### 2.2 Cost Report
- Total material cost breakdown
- Variance analysis vs standard cost
- Strategy comparison savings

### 2.3 Compliance Report
- FEFO compliance status
- TDS compliance verification
- Shelf life tracking
- Audit traceability

### 2.4 Summary Report
- Executive overview
- Key metrics dashboard
- Recommendations

---

## 3. Output Formats

| Format | Use Case | Notes |
|--------|----------|-------|
| `dict` | API responses | Native Python |
| `json` | Storage, APIs | Serializable |
| `html` | Web display, Email | Styled, printable |
| `csv` | ERP integration | Picking list only |
| `pdf` | Official documents | Professional |

---

## 4. Test Plan

### 4.1 Test Cases (RPT-001 through RPT-012)

| Test ID | Description | Priority |
|---------|-------------|----------|
| RPT-001 | Production report generation | P0 |
| RPT-002 | Cost report with Phase 4 data | P0 |
| RPT-003 | Compliance report with TDS | P0 |
| RPT-004 | Summary report | P0 |
| RPT-005 | JSON format output | P0 |
| RPT-006 | HTML format output | P1 |
| RPT-007 | CSV export | P1 |
| RPT-008 | Missing optional data | P0 |
| RPT-009 | Empty batch list | P0 |
| RPT-010 | Custom template | P1 |
| RPT-011 | Multi-item report | P1 |
| RPT-012 | Metadata generation | P0 |

---

## 5. Integration Points

### 5.1 Input from Previous Phases

```
Phase 1 (Formulation) --> Item details, BOM
Phase 3 (TDS) ---------> Compliance results
Phase 4 (Cost) --------> Cost analysis
Phase 5 (Optimization) -> Selected batches (REQUIRED)
```

### 5.2 Output Destinations

- ERPNext Work Order
- Frappe Print Format
- Email notifications
- External systems via API

---

## 6. Error Handling

| Error Type | Condition | Response |
|------------|-----------|----------|
| `InvalidInputError` | Missing required data | Return error with details |
| `TemplateNotFoundError` | Custom template missing | Fallback to default |
| `FormatNotSupportedError` | Invalid format | Return supported formats |
| `RenderingError` | Template render failure | Log and return raw dict |

---

## 7. Implementation Checklist

- [ ] Core ReportGenerator class
- [ ] Production report function
- [ ] Cost report function
- [ ] Compliance report function
- [ ] Summary report function
- [ ] JSON format handler
- [ ] HTML format handler
- [ ] CSV format handler
- [ ] Default HTML templates
- [ ] Unit tests (RPT-001 to RPT-012)
- [ ] Integration tests
- [ ] Documentation

---

*Technical Specification for Phase 6 Report Generator*
