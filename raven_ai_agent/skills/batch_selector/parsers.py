"""Universal Golden Number Parser for Batch Selection.

This module provides parsing functionality for the golden number format
used in batch identification: XX-YYYY-### (e.g., 01-2025-001)

Supported input formats:
    - Full golden number: "01-2025-001"
    - Partial year-sequence: "2025-001"
    - Sequence only: "001"
    - Product name search: "Moringa Capsules"
    - Date range: "2025-01-01 to 2025-01-31"
"""

import re
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime


# Golden number regex patterns
GOLDEN_NUMBER_FULL = re.compile(r'^(\d{2})-(\d{4})-(\d{3})$')
GOLDEN_NUMBER_YEAR_SEQ = re.compile(r'^(\d{4})-(\d{3})$')
GOLDEN_NUMBER_SEQ_ONLY = re.compile(r'^(\d{3})$')
DATE_RANGE_PATTERN = re.compile(r'^(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})$')


@dataclass
class ParsedGoldenNumber:
    """Structured result of golden number parsing."""
    valid: bool
    golden_number: Optional[str] = None
    components: Optional[Dict[str, str]] = None
    search_type: str = "unknown"
    confidence: float = 0.0
    error_message: Optional[str] = None
    raw_input: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "valid": self.valid,
            "golden_number": self.golden_number,
            "components": self.components,
            "search_type": self.search_type,
            "confidence": self.confidence,
            "error_message": self.error_message,
            "raw_input": self.raw_input
        }


class GoldenNumberParser:
    """Parser class for handling various golden number input formats."""
    
    def __init__(self, default_company_code: str = "01", default_year: Optional[int] = None):
        """
        Initialize the parser with defaults.
        
        Args:
            default_company_code: Default company code when not specified (default: "01")
            default_year: Default year when not specified (default: current year)
        """
        self.default_company_code = default_company_code
        self.default_year = default_year or datetime.now().year
    
    def parse(self, input_string: str) -> ParsedGoldenNumber:
        """
        Main entry point for parsing any input format.
        
        Args:
            input_string: The input to parse
            
        Returns:
            ParsedGoldenNumber with parsing results
        """
        if not input_string or not isinstance(input_string, str):
            return ParsedGoldenNumber(
                valid=False,
                error_message="Input must be a non-empty string",
                raw_input=str(input_string) if input_string else ""
            )
        
        cleaned = input_string.strip()
        
        # Try each parser in order of specificity
        parsers = [
            self._parse_full_golden_number,
            self._parse_year_sequence,
            self._parse_sequence_only,
            self._parse_date_range,
            self._parse_product_name
        ]
        
        for parser in parsers:
            result = parser(cleaned)
            if result.valid or result.search_type != "unknown":
                result.raw_input = input_string
                return result
        
        return ParsedGoldenNumber(
            valid=False,
            error_message=f"Could not parse input: {input_string}",
            raw_input=input_string
        )
    
    def _parse_full_golden_number(self, input_string: str) -> ParsedGoldenNumber:
        """Parse full golden number format: XX-YYYY-###"""
        match = GOLDEN_NUMBER_FULL.match(input_string)
        if match:
            company, year, sequence = match.groups()
            return ParsedGoldenNumber(
                valid=True,
                golden_number=input_string,
                components={
                    "company_code": company,
                    "year": year,
                    "sequence": sequence
                },
                search_type="exact",
                confidence=1.0
            )
        return ParsedGoldenNumber(valid=False)
    
    def _parse_year_sequence(self, input_string: str) -> ParsedGoldenNumber:
        """Parse year-sequence format: YYYY-###"""
        match = GOLDEN_NUMBER_YEAR_SEQ.match(input_string)
        if match:
            year, sequence = match.groups()
            golden_number = f"{self.default_company_code}-{year}-{sequence}"
            return ParsedGoldenNumber(
                valid=True,
                golden_number=golden_number,
                components={
                    "company_code": self.default_company_code,
                    "year": year,
                    "sequence": sequence
                },
                search_type="partial",
                confidence=0.9
            )
        return ParsedGoldenNumber(valid=False)
    
    def _parse_sequence_only(self, input_string: str) -> ParsedGoldenNumber:
        """Parse sequence only format: ###"""
        match = GOLDEN_NUMBER_SEQ_ONLY.match(input_string)
        if match:
            sequence = match.group(1)
            year = str(self.default_year)
            golden_number = f"{self.default_company_code}-{year}-{sequence}"
            return ParsedGoldenNumber(
                valid=True,
                golden_number=golden_number,
                components={
                    "company_code": self.default_company_code,
                    "year": year,
                    "sequence": sequence
                },
                search_type="partial",
                confidence=0.7
            )
        return ParsedGoldenNumber(valid=False)
    
    def _parse_date_range(self, input_string: str) -> ParsedGoldenNumber:
        """Parse date range format: YYYY-MM-DD to YYYY-MM-DD"""
        match = DATE_RANGE_PATTERN.match(input_string)
        if match:
            start_date, end_date = match.groups()
            return ParsedGoldenNumber(
                valid=True,
                components={
                    "start_date": start_date,
                    "end_date": end_date,
                    "search_type": "date_range"
                },
                search_type="date_range",
                confidence=0.8
            )
        return ParsedGoldenNumber(valid=False)
    
    def _parse_product_name(self, input_string: str) -> ParsedGoldenNumber:
        """Parse as product name search (fallback for text input)."""
        # If it contains letters and doesn't match other patterns, treat as product search
        if re.search(r'[a-zA-Z]', input_string) and len(input_string) >= 3:
            return ParsedGoldenNumber(
                valid=True,
                components={
                    "product_name": input_string,
                    "search_type": "product_search"
                },
                search_type="fuzzy",
                confidence=0.5
            )
        return ParsedGoldenNumber(valid=False)


# Module-level convenience functions
_default_parser = GoldenNumberParser()


def parse_golden_number(input_string: str) -> Dict[str, Any]:
    """
    Parse a golden number input string.
    
    Args:
        input_string: The input to parse
        
    Returns:
        Dictionary with parsing results
    """
    result = _default_parser.parse(input_string)
    return result.to_dict()


def validate_format(golden_number: str) -> bool:
    """
    Validate if a string is a valid full golden number format.
    
    Args:
        golden_number: The string to validate
        
    Returns:
        True if valid XX-YYYY-### format, False otherwise
    """
    return bool(GOLDEN_NUMBER_FULL.match(golden_number.strip()))


def extract_components(golden_number: str) -> Optional[Dict[str, str]]:
    """
    Extract components from a golden number.
    
    Args:
        golden_number: The golden number to parse
        
    Returns:
        Dictionary with company_code, year, sequence or None if invalid
    """
    match = GOLDEN_NUMBER_FULL.match(golden_number.strip())
    if match:
        company, year, sequence = match.groups()
        return {
            "company_code": company,
            "year": year,
            "sequence": sequence
        }
    return None


def fuzzy_match(partial_input: str, company_code: str = "01") -> List[str]:
    """
    Generate possible golden numbers from partial input.
    
    Args:
        partial_input: Partial golden number input
        company_code: Default company code to use
        
    Returns:
        List of possible golden number matches
    """
    current_year = datetime.now().year
    possibilities = []
    
    # Try sequence only
    if GOLDEN_NUMBER_SEQ_ONLY.match(partial_input):
        # Current year and previous year
        possibilities.append(f"{company_code}-{current_year}-{partial_input}")
        possibilities.append(f"{company_code}-{current_year - 1}-{partial_input}")
    
    # Try year-sequence
    elif GOLDEN_NUMBER_YEAR_SEQ.match(partial_input):
        possibilities.append(f"{company_code}-{partial_input}")
    
    return possibilities
