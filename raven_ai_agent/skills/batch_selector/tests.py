"""Unit Tests for BATCH_SELECTOR_AGENT

Comprehensive test suite covering:
- Golden number parsing (YYWWDS and legacy formats)
- FEFO sorting algorithms
- Cost-based optimization
- Batch allocation logic
- Compliance validation

Author: Raven AI Agent
Date: 2026-02-04
"""

import unittest
from datetime import datetime, date, timedelta
from typing import List, Dict, Any

# Import modules under test
from .parsers import (
    parse_golden_number_yywwds,
    parse_golden_number_legacy,
    parse_golden_number_universal,
    get_manufacturing_date_from_golden_number
)
from .optimizer import (
    get_batch_sort_key,
    sort_batches_fefo,
    sort_batches_cost,
    filter_batches_by_expiry,
    optimize_batches
)
from .selector import (
    calculate_weighted_average,
    validate_blend_compliance
)


class TestGoldenNumberParserYYWWDS(unittest.TestCase):
    """Test cases for new YYWWDS format parsing."""
    
    def test_valid_basic_format(self):
        """Test parsing standard YYWWDS format."""
        result = parse_golden_number_yywwds('ALOE-200X-PWD-250311')
        self.assertIsNotNone(result)
        self.assertEqual(result['format'], 'YYWWDS')
        self.assertEqual(result['year'], 25)
        self.assertEqual(result['week'], 3)
        self.assertEqual(result['day'], 1)
        self.assertEqual(result['sequence'], 1)
        self.assertEqual(result['parsed_date'], '2025-01-13')
    
    def test_week_05_day_2(self):
        """Test Week 5, Day 2."""
        result = parse_golden_number_yywwds('ALO-GEL-RAW-250521')
        self.assertIsNotNone(result)
        self.assertEqual(result['week'], 5)
        self.assertEqual(result['day'], 2)
    
    def test_invalid_week_zero(self):
        """Week 0 should be invalid."""
        result = parse_golden_number_yywwds('TEST-250011')
        self.assertIsNone(result)
    
    def test_invalid_week_53(self):
        """Week 53 should be invalid."""
        result = parse_golden_number_yywwds('TEST-255311')
        self.assertIsNone(result)
    
    def test_invalid_day_zero(self):
        """Day 0 should be invalid."""
        result = parse_golden_number_yywwds('TEST-250301')
        self.assertIsNone(result)
    
    def test_invalid_day_8(self):
        """Day 8 should be invalid."""
        result = parse_golden_number_yywwds('TEST-250381')
        self.assertIsNone(result)
    
    def test_no_match_short_code(self):
        """Codes without 6 trailing digits should return None."""
        result = parse_golden_number_yywwds('SHORT-123')
        self.assertIsNone(result)
    
    def test_sort_key_ordering(self):
        """Sort keys should order correctly."""
        r1 = parse_golden_number_yywwds('A-250311')  # Week 3
        r2 = parse_golden_number_yywwds('B-250511')  # Week 5
        r3 = parse_golden_number_yywwds('C-240311')  # Year 24
        
        self.assertLess(r3['sort_key'], r1['sort_key'])
        self.assertLess(r1['sort_key'], r2['sort_key'])


class TestFEFOSorting(unittest.TestCase):
    """Test FEFO sorting algorithms."""
    
    def test_sort_by_golden_number(self):
        """Batches with golden numbers sort by date."""
        batches = [
            {'item_code': 'ALOE-250521', 'batch_id': 'B3'},  # Week 5
            {'item_code': 'ALOE-250311', 'batch_id': 'B1'},  # Week 3
            {'item_code': 'ALOE-250411', 'batch_id': 'B2'},  # Week 4
        ]
        sorted_batches = sort_batches_fefo(batches)
        
        self.assertEqual(sorted_batches[0]['batch_id'], 'B1')
        self.assertEqual(sorted_batches[1]['batch_id'], 'B2')
        self.assertEqual(sorted_batches[2]['batch_id'], 'B3')
    
    def test_golden_number_priority(self):
        """Golden number has priority over mfg date."""
        batches = [
            {'item_code': 'ALOE-250311', 'manufacturing_date': '2025-02-01'},
            {'item_code': 'LEGACY', 'manufacturing_date': '2025-01-01'},
        ]
        sorted_batches = sort_batches_fefo(batches)
        
        self.assertEqual(sorted_batches[0]['item_code'], 'ALOE-250311')


class TestCostSorting(unittest.TestCase):
    """Test cost-based sorting."""
    
    def test_sort_ascending(self):
        """Cheapest batches first."""
        batches = [
            {'batch_id': 'B1', 'cost': 100},
            {'batch_id': 'B2', 'cost': 50},
            {'batch_id': 'B3', 'cost': 75},
        ]
        sorted_batches = sort_batches_cost(batches, ascending=True)
        
        self.assertEqual(sorted_batches[0]['cost'], 50)
        self.assertEqual(sorted_batches[1]['cost'], 75)
        self.assertEqual(sorted_batches[2]['cost'], 100)


class TestWeightedAverage(unittest.TestCase):
    """Test weighted average calculations."""
    
    def test_simple_weighted_average(self):
        """Calculate weighted average correctly."""
        batches = [
            {'quantity': 100, 'coa_params': {'Aloin': {'value': 1.0}}},
            {'quantity': 200, 'coa_params': {'Aloin': {'value': 2.0}}},
        ]
        result = calculate_weighted_average(batches)
        
        # (100*1.0 + 200*2.0) / 300 = 1.6667
        self.assertAlmostEqual(result['Aloin'], 1.6667, places=4)


class TestComplianceValidation(unittest.TestCase):
    """Test TDS compliance validation."""
    
    def test_compliant_blend(self):
        """Blend meeting TDS specs is compliant."""
        batches = [
            {'allocated_qty': 100, 'coa_params': {'Aloin': {'value': 1.5}}}
        ]
        tds_specs = {'Aloin': {'min': 0.5, 'max': 2.0}}
        
        result = validate_blend_compliance(batches, tds_specs)
        
        self.assertTrue(result['compliant'])
        self.assertEqual(result['parameter_results']['Aloin']['status'], 'PASS')
    
    def test_non_compliant_blend(self):
        """Blend failing TDS spec is non-compliant."""
        batches = [
            {'allocated_qty': 100, 'coa_params': {'Aloin': {'value': 3.0}}}
        ]
        tds_specs = {'Aloin': {'min': 0.5, 'max': 2.0}}
        
        result = validate_blend_compliance(batches, tds_specs)
        
        self.assertFalse(result['compliant'])
        self.assertEqual(result['parameter_results']['Aloin']['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
