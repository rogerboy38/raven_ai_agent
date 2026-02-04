"""Batch Optimization Functions for BATCH_SELECTOR_AGENT

Provides sorting and filtering functions for batch selection:
- FEFO (First Expired, First Out) sorting
- Cost-based sorting
- Expiry filtering

Author: Raven AI Agent
Date: 2026-02-04
"""

from datetime import date, datetime
from typing import List, Dict, Any, Optional, Tuple

from .parsers import parse_golden_number_universal


def get_batch_sort_key(batch: Dict[str, Any]) -> Tuple[int, str]:
    """
    Get sort key for FEFO ordering.
    
    Priority:
    1. Golden number from item_code (priority 0)
    2. Manufacturing date (priority 1)
    3. Expiry date (priority 2)
    4. No date info (priority 3, lowest)
    
    Args:
        batch: Batch dict with item_code, manufacturing_date, expiry_date
    
    Returns:
        Tuple of (priority, sort_key_string) for sorting
    """
    # Try golden number first
    gn = parse_golden_number_universal(batch.get('item_code', ''))
    if gn:
        return (0, gn['sort_key'])
    
    # Fall back to manufacturing_date
    if batch.get('manufacturing_date'):
        mfg_date = batch['manufacturing_date']
        if isinstance(mfg_date, (date, datetime)):
            mfg_date = mfg_date.strftime('%Y-%m-%d')
        return (1, str(mfg_date))
    
    # Fall back to expiry_date
    if batch.get('expiry_date'):
        exp_date = batch['expiry_date']
        if isinstance(exp_date, (date, datetime)):
            exp_date = exp_date.strftime('%Y-%m-%d')
        return (2, str(exp_date))
    
    # No date info - lowest priority
    return (3, '9999-12-31')


def sort_batches_fefo(batches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort batches using FEFO (First Expired, First Out) logic.
    
    Prioritizes batches with golden numbers, then manufacturing date,
    then expiry date. Oldest batches come first.
    
    Args:
        batches: List of batch dictionaries
    
    Returns:
        Sorted list with oldest batches first
    """
    return sorted(batches, key=get_batch_sort_key)


def sort_batches_cost(
    batches: List[Dict[str, Any]],
    ascending: bool = True
) -> List[Dict[str, Any]]:
    """
    Sort batches by cost.
    
    Args:
        batches: List of batch dicts with 'cost' field
        ascending: If True, cheapest first; if False, most expensive first
    
    Returns:
        Sorted list by cost
    """
    def get_cost_key(batch):
        cost = batch.get('cost', 0)
        # If cost unknown, put at end
        if batch.get('cost_unknown', False):
            return float('inf') if ascending else float('-inf')
        return cost
    
    return sorted(batches, key=get_cost_key, reverse=not ascending)


def filter_batches_by_expiry(
    batches: List[Dict[str, Any]],
    include_expired: bool = False,
    near_expiry_days: int = 30
) -> List[Dict[str, Any]]:
    """
    Filter and flag batches based on expiry status.
    
    Args:
        batches: List of batch dictionaries
        include_expired: If True, include expired batches with warning flag
        near_expiry_days: Days threshold for near-expiry warning
    
    Returns:
        Filtered list with warning flags added
    """
    today = date.today()
    result = []
    
    for batch in batches:
        # Initialize warnings list if not present
        batch['warnings'] = batch.get('warnings', [])
        batch['is_expired'] = False
        batch['is_near_expiry'] = False
        
        expiry_date = batch.get('expiry_date')
        if expiry_date:
            # Convert string to date if needed
            if isinstance(expiry_date, str):
                try:
                    expiry = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                except ValueError:
                    # Try alternate format
                    try:
                        expiry = datetime.strptime(expiry_date[:10], '%Y-%m-%d').date()
                    except ValueError:
                        expiry = None
            elif isinstance(expiry_date, datetime):
                expiry = expiry_date.date()
            elif isinstance(expiry_date, date):
                expiry = expiry_date
            else:
                expiry = None
            
            if expiry:
                # Check if expired
                if expiry <= today:
                    batch['is_expired'] = True
                    if include_expired:
                        batch['warnings'].append('EXPIRED')
                        result.append(batch)
                    continue  # Skip expired batches unless included
                
                # Check near expiry
                days_to_expiry = (expiry - today).days
                if days_to_expiry <= near_expiry_days:
                    batch['is_near_expiry'] = True
                    batch['warnings'].append(f'Expires within {days_to_expiry} days')
        
        result.append(batch)
    
    return result


def optimize_batches(
    batches: List[Dict[str, Any]],
    mode: str = 'fefo',
    include_expired: bool = False,
    near_expiry_days: int = 30
) -> List[Dict[str, Any]]:
    """
    Apply optimization mode to batch list.
    
    Modes:
    - 'fefo': First Expired, First Out (default)
    - 'cost': Lowest cost first
    - 'cost_desc': Highest cost first
    
    Args:
        batches: List of batch dictionaries
        mode: Optimization mode ('fefo', 'cost', 'cost_desc')
        include_expired: Include expired batches
        near_expiry_days: Near-expiry warning threshold
    
    Returns:
        Optimized and filtered batch list
    """
    # Filter by expiry first
    filtered = filter_batches_by_expiry(
        batches,
        include_expired=include_expired,
        near_expiry_days=near_expiry_days
    )
    
    # Apply sorting based on mode
    if mode == 'fefo':
        return sort_batches_fefo(filtered)
    elif mode == 'cost':
        return sort_batches_cost(filtered, ascending=True)
    elif mode == 'cost_desc':
        return sort_batches_cost(filtered, ascending=False)
    else:
        # Default to FEFO
        return sort_batches_fefo(filtered)
