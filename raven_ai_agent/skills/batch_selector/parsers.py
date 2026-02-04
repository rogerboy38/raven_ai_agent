"""Golden Number Parsers for BATCH_SELECTOR_AGENT

Supports both legacy and new item code formats for FEFO sorting.

Formats:
- New (YYWWDS): ITEM-NAME-250311 -> year=25, week=03, day=1, seq=1
- Legacy (PPPPFFYYPS): ITEM_0617027231 -> product=0617, folio=27, year=23, plant=1

Author: Raven AI Agent
Date: 2026-02-04
"""

import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


def parse_golden_number_yywwds(item_code: str) -> Optional[Dict[str, Any]]:
    """
    Parse golden number from new format: YYWWDS
    
    Pattern: 6 digits at end of item_code
    - YY = Year (2 digits, 00-99)
    - WW = Week (2 digits, 01-52)
    - D = Day of week (1 digit, 1-7)
    - S = Sequence (1 digit, 1-9)
    
    Args:
        item_code: Item code string (e.g., 'ALOE-200X-PWD-250311')
    
    Returns:
        Dict with parsed values and sort_key, or None if pattern doesn't match
    
    Examples:
        >>> parse_golden_number_yywwds('ALOE-200X-PWD-250311')
        {'format': 'YYWWDS', 'year': 25, 'week': 3, 'day': 1, 'sequence': 1,
         'parsed_date': '2025-01-13', 'sort_key': '2025030111'}
    """
    match = re.search(r'(\d{2})(\d{2})(\d)(\d)$', item_code)
    if not match:
        return None
    
    year, week, day, seq = map(int, match.groups())
    
    # Validate ranges
    if week < 1 or week > 52 or day < 1 or day > 7:
        return None
    
    # Convert to full year (2000-2049 -> 20xx, 2050-2099 -> 19xx)
    full_year = 2000 + year if year < 50 else 1900 + year
    
    # Calculate actual date from ISO week date
    # ISO week 1 contains January 4th
    jan4 = datetime(full_year, 1, 4)
    week_start = jan4 - timedelta(days=jan4.weekday())
    target_date = week_start + timedelta(weeks=week - 1, days=day - 1)
    
    return {
        'format': 'YYWWDS',
        'year': year,
        'week': week,
        'day': day,
        'sequence': seq,
        'parsed_date': target_date.strftime('%Y-%m-%d'),
        'sort_key': f"{full_year:04d}{week:02d}{day}{seq}"
    }


def parse_golden_number_legacy(item_code: str) -> Optional[Dict[str, Any]]:
    """
    Parse golden number from legacy format: PPPPFFYYPS
    
    Pattern: 9-10 digits at end of item_code
    - PPPP = Product code (4 digits)
    - FF = Folio number (2 digits)
    - YY = Year (2 digits)
    - P = Plant (1 digit)
    - S = Sequence (0-1 digit, optional)
    
    Args:
        item_code: Item code string (e.g., 'ITEM_0617027231')
    
    Returns:
        Dict with parsed values and sort_key, or None if pattern doesn't match
    
    Examples:
        >>> parse_golden_number_legacy('ITEM_0617027231')
        {'format': 'PPPPFFYYPS', 'product': '0617', 'folio': 27, 'year': 23,
         'plant': '1', 'sequence': 1, 'sort_key': '202327001'}
    """
    match = re.search(r'(\d{4})(\d{2})(\d{2})(\d)(\d?)$', item_code)
    if not match:
        return None
    
    product, folio, year, plant, seq = match.groups()
    full_year = 2000 + int(year) if int(year) < 50 else 1900 + int(year)
    
    return {
        'format': 'PPPPFFYYPS',
        'product': product,
        'folio': int(folio),
        'year': int(year),
        'plant': plant,
        'sequence': int(seq or 1),
        'sort_key': f"{full_year:04d}{int(folio):02d}00{plant}{seq or 1}"
    }


def parse_golden_number_universal(item_code: str) -> Optional[Dict[str, Any]]:
    """
    Parse golden number supporting both formats with auto-detection.
    
    Tries new format (YYWWDS) first, then falls back to legacy (PPPPFFYYPS).
    
    Args:
        item_code: Item code string
    
    Returns:
        Dict with parsed values, format indicator, and sort_key.
        Returns None if neither pattern matches.
    
    Examples:
        >>> parse_golden_number_universal('ALOE-200X-PWD-250311')
        {'format': 'YYWWDS', 'year': 25, 'week': 3, ...}
        
        >>> parse_golden_number_universal('ITEM_0617027231')
        {'format': 'PPPPFFYYPS', 'product': '0617', ...}
    """
    # Try new format first (more specific pattern validation)
    result = parse_golden_number_yywwds(item_code)
    if result:
        return result
    
    # Fall back to legacy format
    result = parse_golden_number_legacy(item_code)
    if result:
        return result
    
    return None


def get_manufacturing_date_from_golden_number(
    item_code: str
) -> Optional[str]:
    """
    Extract manufacturing date from golden number.
    
    Args:
        item_code: Item code with golden number
    
    Returns:
        Date string in YYYY-MM-DD format, or None if can't be parsed
    """
    gn = parse_golden_number_universal(item_code)
    if not gn:
        return None
    
    if gn.get('format') == 'YYWWDS':
        return gn.get('parsed_date')
    
    # For legacy format, we don't have exact date
    # Return approximate date based on folio (assuming folio = week)
    if gn.get('format') == 'PPPPFFYYPS':
        full_year = 2000 + gn['year'] if gn['year'] < 50 else 1900 + gn['year']
        # Approximate: folio as week number
        try:
            jan4 = datetime(full_year, 1, 4)
            week_start = jan4 - timedelta(days=jan4.weekday())
            target_date = week_start + timedelta(weeks=gn['folio'] - 1)
            return target_date.strftime('%Y-%m-%d')
        except Exception:
            return None
    
    return None
