"""Batch Selector Skill for Raven AI Agent.

This skill provides functionality to parse and select batches using
the golden number format (XX-YYYY-###).

Modules:
    - parsers: Universal golden number parser with fuzzy matching
    - selector: Batch selection and Frappe API integration
"""

from .parsers import (
    parse_golden_number,
    validate_format,
    extract_components,
    fuzzy_match,
    GoldenNumberParser
)

from .selector import (
    select_batch,
    query_frappe_batch,
    format_response,
    BatchSelector
)

__version__ = "0.1.0"
__all__ = [
    # Parser functions
    "parse_golden_number",
    "validate_format",
    "extract_components",
    "fuzzy_match",
    "GoldenNumberParser",
    # Selector functions
    "select_batch",
    "query_frappe_batch",
    "format_response",
    "BatchSelector",
]
