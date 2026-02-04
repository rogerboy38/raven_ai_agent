"""Core Batch Selection Functions for BATCH_SELECTOR_AGENT

Main entry point for batch selection operations.
Provides frappe whitelist functions for direct API access.

Author: Raven AI Agent
Date: 2026-02-04
"""

import json
from typing import List, Dict, Any, Optional, Union

try:
    import frappe
    from frappe.utils import flt
    HAS_FRAPPE = True
except ImportError:
    HAS_FRAPPE = False
    def flt(x, precision=None):
        return float(x) if x else 0.0

from .parsers import parse_golden_number_universal
from .optimizer import optimize_batches, get_batch_sort_key

# Default configuration
DEFAULT_WAREHOUSE = 'FG to Sell Warehouse - AMB-W'
DEFAULT_NEAR_EXPIRY_DAYS = 30


def get_batch_cost(batch_id: str, item_code: str) -> tuple:
    """Get cost for batch using SLE with fallback to Item."""
    if not HAS_FRAPPE:
        return 0.0, True
    
    sle_rate = frappe.db.get_value(
        'Stock Ledger Entry',
        {'batch_no': batch_id, 'item_code': item_code, 'actual_qty': ['>', 0]},
        'valuation_rate', order_by='posting_date desc'
    )
    if sle_rate:
        return flt(sle_rate), False
    
    item_rate = frappe.db.get_value('Item', item_code, 'valuation_rate')
    return (flt(item_rate), False) if item_rate else (0.0, True)


def get_available_batches(item_code: str, warehouse: Optional[str] = None) -> List[Dict]:
    """Get available batches for item with stock > 0."""
    if not HAS_FRAPPE:
        return []
    
    batches = frappe.get_all('Batch', filters={'item': item_code, 'disabled': 0},
        fields=['name', 'batch_id', 'item', 'manufacturing_date', 'expiry_date', 'stock_uom'])
    
    result = []
    for batch in batches:
        bin_filters = {'item_code': item_code, 'batch_no': batch.name}
        if warehouse:
            bin_filters['warehouse'] = warehouse
        
        for bin_rec in frappe.get_all('Bin', filters=bin_filters,
                fields=['warehouse', 'actual_qty', 'reserved_qty']):
            available = (bin_rec.actual_qty or 0) - (bin_rec.reserved_qty or 0)
            if available > 0:
                cost, cost_unknown = get_batch_cost(batch.name, item_code)
                result.append({
                    'batch_id': batch.name, 'batch_no': batch.batch_id or batch.name,
                    'item_code': batch.item,
                    'manufacturing_date': str(batch.manufacturing_date) if batch.manufacturing_date else None,
                    'expiry_date': str(batch.expiry_date) if batch.expiry_date else None,
                    'warehouse': bin_rec.warehouse, 'available_qty': available,
                    'uom': batch.stock_uom, 'cost': cost, 'cost_unknown': cost_unknown, 'warnings': []
                })
    return result


def select_optimal_batches(item_code: str, required_qty: float, warehouse: Optional[str] = None,
        optimization_mode: str = 'fefo', include_expired: bool = False,
        near_expiry_days: int = DEFAULT_NEAR_EXPIRY_DAYS) -> Dict:
    """Select optimal batches to fulfill required quantity."""
    batches = get_available_batches(item_code, warehouse)
    if not batches:
        return {'item_code': item_code, 'required_qty': required_qty, 'selected_batches': [],
                'total_allocated': 0, 'shortfall': required_qty, 'fulfillment_status': 'NO_STOCK'}
    
    sorted_batches = optimize_batches(batches, mode=optimization_mode,
        include_expired=include_expired, near_expiry_days=near_expiry_days)
    
    allocations, remaining = [], required_qty
    for rank, batch in enumerate(sorted_batches, start=1):
        if remaining <= 0:
            break
        allocate_qty = min(batch['available_qty'], remaining)
        gn = parse_golden_number_universal(batch.get('item_code', ''))
        allocations.append({
            'batch_id': batch['batch_id'], 'batch_no': batch['batch_no'],
            'available_qty': batch['available_qty'], 'allocated_qty': allocate_qty,
            'warehouse': batch['warehouse'],
            'manufacturing_date': batch.get('manufacturing_date'),
            'expiry_date': batch.get('expiry_date'),
            'golden_number': gn, 'fefo_rank': rank, 'tds_status': 'pending_check',
            'cost': batch.get('cost', 0), 'warnings': batch.get('warnings', [])
        })
        remaining -= allocate_qty
    
    total = required_qty - max(0, remaining)
    return {'item_code': item_code, 'required_qty': required_qty, 'selected_batches': allocations,
            'total_allocated': total, 'shortfall': max(0, remaining),
            'fulfillment_status': 'COMPLETE' if remaining <= 0 else 'PARTIAL'}


def calculate_weighted_average(batches_with_params: List[Dict]) -> Dict[str, float]:
    """Calculate weighted average: sum(param_value * qty) / total_qty"""
    total_qty = sum(b.get('quantity', 0) for b in batches_with_params)
    if total_qty == 0:
        return {}
    all_params = set()
    for b in batches_with_params:
        all_params.update(b.get('coa_params', {}).keys())
    return {param: flt(sum(b.get('coa_params', {}).get(param, {}).get('value', 0) * b.get('quantity', 0)
            for b in batches_with_params) / total_qty, 4) for param in all_params}


def validate_blend_compliance(selected_batches: List[Dict], tds_specs: Dict) -> Dict:
    """Validate if blended parameters meet TDS specifications."""
    batches_with_params = [{'quantity': b.get('allocated_qty', 0), 'coa_params': b.get('coa_params', {})}
                           for b in selected_batches]
    weighted_avgs = calculate_weighted_average(batches_with_params)
    compliance_results, all_compliant = {}, True
    for param, spec in tds_specs.items():
        val = weighted_avgs.get(param)
        min_v, max_v = spec.get('min'), spec.get('max')
        if val is None:
            compliance_results[param] = {'status': 'UNKNOWN'}
            all_compliant = False
        elif (min_v and val < min_v) or (max_v and val > max_v):
            compliance_results[param] = {'status': 'FAIL', 'actual': val, 'min': min_v, 'max': max_v}
            all_compliant = False
        else:
            compliance_results[param] = {'status': 'PASS', 'actual': val}
    return {'compliant': all_compliant, 'weighted_averages': weighted_avgs, 'parameter_results': compliance_results}


if HAS_FRAPPE:
    @frappe.whitelist()
    def select_batches_for_formulation(required_items, warehouse=None, optimization_mode='fefo',
            include_expired=False, near_expiry_days=DEFAULT_NEAR_EXPIRY_DAYS):
        """Raven AI Skill: Select optimal batches for formulation items."""
        if isinstance(required_items, str):
            required_items = json.loads(required_items)
        batch_selections, all_fulfilled = [], True
        for item in required_items:
            item_code = item.get('item_code')
            if not frappe.db.exists('Item', item_code):
                batch_selections.append({'item_code': item_code, 'fulfillment_status': 'ERROR',
                    'error': f'Item {item_code} does not exist'})
                all_fulfilled = False
                continue
            selection = select_optimal_batches(item_code, flt(item.get('required_qty', 0)),
                warehouse, optimization_mode, include_expired, near_expiry_days)
            selection['item_name'] = item.get('item_name', '')
            if selection['fulfillment_status'] != 'COMPLETE':
                all_fulfilled = False
            batch_selections.append(selection)
        return {'batch_selections': batch_selections,
                'overall_status': 'ALL_ITEMS_FULFILLED' if all_fulfilled else 'SOME_ITEMS_SHORT'}
