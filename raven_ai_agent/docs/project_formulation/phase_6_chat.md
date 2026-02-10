# Phase 6: Report Generator

## Overview

This document outlines the Report Generator agent, the final phase of the Formulation Orchestrator pipeline. The Report Generator transforms optimized batch selections into production-ready outputs suitable for manufacturing, inventory management, and compliance documentation.

## Agent Architecture

### File Location
```
raven_ai_agent/skills/formulation_orchestrator/agents/report_generator.py
```

### Core Components

1. **ReportGenerator Class** - Main orchestrator for report generation
2. **Format Handlers** - Pluggable output format processors
3. **Template Engine** - Customizable report templates
4. **Export Manager** - Multi-format export capabilities

---

## Report Types

### 1. Production Order Report

Detailed batch picking list for manufacturing floor.

```python
def generate_production_report(optimization_result, production_order=None):
    """
    Generates a production-ready batch picking report.
    
    Args:
        optimization_result: dict - Output from Phase 5 Optimization Engine
        production_order: str - Optional Work Order reference
    
    Returns:
        dict: {
            'report_type': 'production_order',
            'generated_at': datetime,
            'production_order': str,
            'item_code': str,
            'required_qty': float,
            'picking_list': [
                {
                    'sequence': int,
                    'batch_id': str,
                    'warehouse': str,
                    'location': str,
                    'quantity': float,
                    'unit': str,
                    'expiry_date': date,
                    'days_to_expiry': int,
                    'unit_cost': float,
                    'line_total': float
                }
            ],
            'summary': {
                'total_quantity': float,
                'total_cost': float,
                'batch_count': int,
                'strategy_used': str,
                'fefo_compliant': bool
            },
            'warnings': list,
            'notes': list
        }
    """
```

### 2. Cost Analysis Report

Detailed cost breakdown for financial review.

```python
def generate_cost_report(optimization_result, cost_data=None):
    """
    Generates cost analysis report with variance data.
    
    Returns:
        dict: {
            'report_type': 'cost_analysis',
            'cost_summary': {
                'total_material_cost': float,
                'average_unit_cost': float,
                'weighted_average_cost': float,
                'cost_variance': float,
                'variance_percentage': float
            },
            'batch_costs': [...],
            'comparison': {
                'vs_standard_cost': float,
                'vs_last_batch': float,
                'potential_savings': float
            },
            'strategy_impact': {
                'strategy_used': str,
                'cost_if_strict_fefo': float,
                'cost_if_minimize_cost': float,
                'savings_achieved': float
            }
        }
    """
```

### 3. Compliance Report

FEFO compliance and TDS verification report.

```python
def generate_compliance_report(optimization_result, tds_results=None):
    """
    Generates compliance report for audit trails.
    
    Returns:
        dict: {
            'report_type': 'compliance',
            'fefo_compliance': {
                'compliant': bool,
                'violations': list,
                'violation_count': int,
                'oldest_batch_used_first': bool
            },
            'tds_compliance': {
                'all_specs_met': bool,
                'spec_results': [...],
                'warnings': list
            },
            'shelf_life': {
                'min_remaining_days': int,
                'batches_near_expiry': list,
                'expiry_warnings': list
            },
            'traceability': {
                'batch_ids': list,
                'source_warehouses': list,
                'timestamp': datetime
            }
        }
    """
```

### 4. Summary Report

Executive summary combining all reports.

```python
def generate_summary_report(optimization_result, include_sections=None):
    """
    Generates executive summary report.
    
    Args:
        include_sections: list - ['production', 'cost', 'compliance', 'recommendations']
    
    Returns:
        dict: Combined summary with key metrics and recommendations
    """
```

---

## Main Function Interface

```python
def generate_report(input_data, report_type='production', format='dict'):
    """
    Main entry point for report generation.
    
    Args:
        input_data: dict containing:
            - optimization_result: dict - Phase 5 output (required)
            - cost_data: dict - Phase 4 cost analysis (optional)
            - tds_results: dict - Phase 3 TDS compliance (optional)
            - production_order: str - Work Order reference (optional)
            - formulation: dict - Phase 1 formulation data (optional)
        
        report_type: str - One of:
            - 'production' (default) - Picking list for manufacturing
            - 'cost' - Financial analysis
            - 'compliance' - Audit and compliance
            - 'summary' - Executive summary
            - 'full' - All reports combined
        
        format: str - Output format:
            - 'dict' (default) - Python dictionary
            - 'json' - JSON string
            - 'html' - HTML formatted report
            - 'pdf' - PDF document (requires template)
            - 'csv' - CSV for picking list only
    
    Returns:
        Report in specified format
    """
```

---

## Output Formats

### Supported Formats

| Format | Use Case | Features |
|--------|----------|----------|
| `dict` | API responses, further processing | Native Python, full data |
| `json` | API responses, storage | Serializable, portable |
| `html` | Web display, email reports | Styled, printable |
| `pdf` | Official documents, archival | Professional, signed |
| `csv` | Spreadsheet import, ERP integration | Simple, compatible |

### Format Handlers

```python
class FormatHandler:
    """Base class for format handlers."""
    
    @abstractmethod
    def render(self, report_data: dict) -> Any:
        """Render report data to specific format."""
        pass

class JSONHandler(FormatHandler):
    def render(self, report_data: dict) -> str:
        return json.dumps(report_data, default=str, indent=2)

class HTMLHandler(FormatHandler):
    def __init__(self, template_name='default'):
        self.template = load_template(template_name)
    
    def render(self, report_data: dict) -> str:
        return self.template.render(**report_data)

class CSVHandler(FormatHandler):
    def render(self, report_data: dict) -> str:
        # Extract picking_list for CSV export
        picking_list = report_data.get('picking_list', [])
        return self._to_csv(picking_list)
```

---

## Integration with Previous Phases

### Data Flow

```
Phase 1 (Formulation) ─────┐
                           │
Phase 2 (Batch Selection) ─┤
                           │
Phase 3 (TDS Compliance) ──┼──► Phase 6 (Report Generator) ──► Output
                           │
Phase 4 (Cost Calculator) ─┤
                           │
Phase 5 (Optimization) ────┘
```

### Input Structure

```python
input_data = {
    # Required - From Phase 5
    'optimization_result': {
        'success': True,
        'selected_batches': [...],
        'summary': {...},
        'warnings': [...],
        'alternatives': {...}
    },
    
    # Optional - From Phase 4
    'cost_data': {
        'valuation_method': 'moving_average',
        'cost_trend': {...},
        'variance_analysis': {...}
    },
    
    # Optional - From Phase 3
    'tds_results': {
        'compliant': True,
        'spec_checks': [...]
    },
    
    # Optional - From Phase 1
    'formulation': {
        'item_code': str,
        'item_name': str,
        'bom_no': str
    },
    
    # Optional - Context
    'production_order': 'WO-2026-00123',
    'requested_by': 'Production Manager',
    'notes': 'Urgent order for Customer X'
}
```

---

## Template System

### Default Templates

| Template | Purpose |
|----------|----------|
| `production_picking.html` | Manufacturing floor picking list |
| `cost_analysis.html` | Financial review report |
| `compliance_audit.html` | Compliance and audit trail |
| `executive_summary.html` | Management summary |

### Custom Templates

```python
# Register custom template
report_generator.register_template(
    name='custom_picking',
    template_path='templates/my_picking_list.html',
    report_type='production'
)

# Use custom template
report = generate_report(
    input_data,
    report_type='production',
    format='html',
    template='custom_picking'
)
```

---

## Unit Tests

### Test Cases (RPT-001 through RPT-012)

| Test ID | Description | Input | Expected |
|---------|-------------|-------|----------|
| RPT-001 | Production report generation | Valid optimization | Complete picking list |
| RPT-002 | Cost report generation | Optimization + cost data | Cost breakdown |
| RPT-003 | Compliance report | Optimization + TDS | Compliance status |
| RPT-004 | Summary report | All phase data | Executive summary |
| RPT-005 | JSON format output | Any report | Valid JSON string |
| RPT-006 | HTML format output | Any report | Rendered HTML |
| RPT-007 | CSV export | Production report | Valid CSV |
| RPT-008 | Missing optional data | Partial input | Graceful handling |
| RPT-009 | Empty batch list | No batches | Empty report + warning |
| RPT-010 | Custom template | Custom path | Template rendered |
| RPT-011 | Multi-item report | Multiple items | Combined report |
| RPT-012 | Timestamp and metadata | Any report | Correct metadata |

---

## Error Handling

```python
class ReportGenerationError(Exception):
    """Base exception for report generation errors."""
    pass

class InvalidInputError(ReportGenerationError):
    """Raised when input data is invalid or missing required fields."""
    pass

class TemplateNotFoundError(ReportGenerationError):
    """Raised when specified template doesn't exist."""
    pass

class FormatNotSupportedError(ReportGenerationError):
    """Raised when requested format is not supported."""
    pass

class RenderingError(ReportGenerationError):
    """Raised when report rendering fails."""
    def __init__(self, format_type, original_error):
        self.format_type = format_type
        self.original_error = original_error
```

---

## Example Usage

### Basic Production Report

```python
from raven_ai_agent.skills.formulation_orchestrator.agents import report_generator

# Get optimization result from Phase 5
optimization_result = optimization_engine.optimize_batch_selection(input_data)

# Generate production report
report = report_generator.generate_report(
    input_data={'optimization_result': optimization_result},
    report_type='production',
    format='dict'
)

print(f"Picking List for {report['item_code']}:")
for item in report['picking_list']:
    print(f"  {item['sequence']}. Batch {item['batch_id']}: {item['quantity']} {item['unit']}")
```

### Full Pipeline Report

```python
# Collect all phase outputs
input_data = {
    'optimization_result': phase5_result,
    'cost_data': phase4_result,
    'tds_results': phase3_result,
    'formulation': phase1_result,
    'production_order': 'WO-2026-00123'
}

# Generate comprehensive report
full_report = report_generator.generate_report(
    input_data=input_data,
    report_type='full',
    format='html'
)

# Save to file
with open('formulation_report.html', 'w') as f:
    f.write(full_report)
```

---

## Session Summary

**Status:** Ready for Implementation

**Key Components:**
- Four report types (Production, Cost, Compliance, Summary)
- Five output formats (dict, JSON, HTML, PDF, CSV)
- Template system for customization
- Full integration with all previous phases

**Next Steps:**
1. Implement `report_generator.py` agent
2. Add format handlers (JSON, HTML, CSV)
3. Create default HTML templates
4. Add unit tests (RPT-001 through RPT-012)
5. Test full pipeline integration with Phases 1-5
6. Create PDF export capability (optional)

---

*Document created as part of the Raven AI Agent project formulation process.*
