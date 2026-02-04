"""BATCH_SELECTOR_AGENT Skill

Phase 2 of the Formulation Orchestration Project.

This skill provides intelligent batch selection for raw materials
using FEFO (First Expired, First Out) logic while respecting
TDS compliance requirements.

Author: Raven AI Agent
Date: 2026-02-04
Version: 1.0.0
"""

from .parsers import (
    parse_golden_number_universal,
    parse_golden_number_yywwds,
    parse_golden_number_legacy
)

from .selector import (
    get_available_batches,
    select_optimal_batches,
    select_batches_for_formulation,
    get_batch_cost,
    calculate_weighted_average,
    validate_blend_compliance
)

from .optimizer import (
    sort_batches_fefo,
    sort_batches_cost,
    get_batch_sort_key,
    filter_batches_by_expiry
)

__all__ = [
    # Parsers
    'parse_golden_number_universal',
    'parse_golden_number_yywwds',
    'parse_golden_number_legacy',
    # Selector
    'get_available_batches',
    'select_optimal_batches',
    'select_batches_for_formulation',
    'get_batch_cost',
    'calculate_weighted_average',
    'validate_blend_compliance',
    # Optimizer
    'sort_batches_fefo',
    'sort_batches_cost',
    'get_batch_sort_key',
    'filter_batches_by_expiry',
]

__version__ = '1.0.0'
__author__ = 'Raven AI Agent'

# Default configuration
DEFAULT_WAREHOUSE = 'FG to Sell Warehouse - AMB-W'
DEFAULT_NEAR_EXPIRY_DAYS = 30
DEFAULT_OPTIMIZATION_MODE = 'fefo'  # 'fefo' or 'cost'
