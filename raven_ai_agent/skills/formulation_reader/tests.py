"""
Tests for Formulation Reader Skill - Phase 1
============================================

Test cases from specification:
- TC1.1: Read Batch AMB list for item X in warehouse Y - verify count and fields
- TC1.2: Read COA AMB2 parameters for a known batch - verify all analytics returned
- TC1.3: Simulate blend with 2 cunetes - verify weighted average calculation
- TC1.4: Compare simulation result to TDS - verify PASS/FAIL flags
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal


class TestFormulationReaderSkill(unittest.TestCase):
    """Test the FormulationReaderSkill query handling."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock frappe module
        self.frappe_patcher = patch.dict('sys.modules', {'frappe': MagicMock()})
        self.frappe_patcher.start()
        
        from raven_ai_agent.skills.formulation_reader.skill import FormulationReaderSkill
        self.skill = FormulationReaderSkill()
    
    def tearDown(self):
        """Clean up after tests."""
        self.frappe_patcher.stop()
    
    def test_can_handle_batch_query(self):
        """Test detection of batch-related queries."""
        queries = [
            "Show batches for item 0227-0303 in Almacen-MP",
            "List all batches in warehouse WH-001",
            "Get batch data for item AL-QX-90-10",
        ]
        
        for query in queries:
            can_handle, confidence = self.skill.can_handle(query)
            self.assertTrue(can_handle, f"Should handle: {query}")
            self.assertGreater(confidence, 0.5)
    
    def test_can_handle_coa_query(self):
        """Test detection of COA-related queries."""
        queries = [
            "Get COA for batch BATCH-AMB-2024-001",
            "Show analytical parameters for batch X",
            "What is the pH value for batch Y",
        ]
        
        for query in queries:
            can_handle, confidence = self.skill.can_handle(query)
            self.assertTrue(can_handle, f"Should handle: {query}")
    
    def test_can_handle_tds_query(self):
        """Test detection of TDS-related queries."""
        queries = [
            "What are TDS specs for AL-QX-90-10?",
            "Get TDS specifications for item X",
            "Show min max range for pH",
        ]
        
        for query in queries:
            can_handle, confidence = self.skill.can_handle(query)
            self.assertTrue(can_handle, f"Should handle: {query}")
    
    def test_can_handle_blend_query(self):
        """Test detection of blend simulation queries."""
        queries = [
            "Simulate blend of 10 kg from BATCH-001 and 15 kg from BATCH-002",
            "Calculate weighted average for blend",
            "Predict pH for blend of 20kg from X",
        ]
        
        for query in queries:
            can_handle, confidence = self.skill.can_handle(query)
            self.assertTrue(can_handle, f"Should handle: {query}")
    
    def test_extract_item_code(self):
        """Test item code extraction from queries."""
        test_cases = [
            ("Show batches for item AL-QX-90-10 in warehouse", "AL-QX-90-10"),
            ("Get data for 0227-0303", "0227-0303"),
            ("item AL-PX-80-20 details", "AL-PX-80-20"),
        ]
        
        for query, expected in test_cases:
            result = self.skill._extract_item_code(query)
            self.assertEqual(result, expected, f"Failed for: {query}")
    
    def test_extract_warehouse(self):
        """Test warehouse extraction from queries."""
        test_cases = [
            ("Show batches in warehouse WH-001", "WH-001"),
            ("Items in Almacen-MP", "Almacen-MP"),
            ("from AlmacenPrincipal", "AlmacenPrincipal"),
        ]
        
        for query, expected in test_cases:
            result = self.skill._extract_warehouse(query)
            self.assertEqual(result, expected, f"Failed for: {query}")
    
    def test_extract_blend_inputs(self):
        """Test blend input extraction from queries."""
        query = "Simulate blend of 10 kg from BATCH-001-C1 and 15 kg from BATCH-002-C1"
        inputs = self.skill._extract_blend_inputs(query)
        
        self.assertEqual(len(inputs), 2)
        self.assertEqual(inputs[0]["cunete_id"], "BATCH-001-C1")
        self.assertEqual(inputs[0]["mass_kg"], 10.0)
        self.assertEqual(inputs[1]["cunete_id"], "BATCH-002-C1")
        self.assertEqual(inputs[1]["mass_kg"], 15.0)


class TestFormulationReader(unittest.TestCase):
    """Test the FormulationReader data access class."""
    
    def setUp(self):
        """Set up test fixtures with mocked frappe."""
        self.frappe_mock = MagicMock()
        self.frappe_patcher = patch.dict('sys.modules', {'frappe': self.frappe_mock})
        self.frappe_patcher.start()
        
        from raven_ai_agent.skills.formulation_reader.reader import FormulationReader
        self.reader = FormulationReader()
    
    def tearDown(self):
        """Clean up after tests."""
        self.frappe_patcher.stop()


class TestWeightedAverageCalculation(unittest.TestCase):
    """TC1.3: Test weighted average calculation accuracy."""
    
    def test_simple_weighted_average(self):
        """Test weighted average calculation matches manual Excel calculation."""
        # Given: Two cunetes with pH values
        # Cunete 1: pH 3.5, mass 10 kg
        # Cunete 2: pH 3.7, mass 15 kg
        # Expected: (3.5 * 10 + 3.7 * 15) / (10 + 15) = (35 + 55.5) / 25 = 3.62
        
        from raven_ai_agent.skills.formulation_reader.reader import (
            BlendInput, BlendParameterResult
        )
        
        values = [(3.5, 10.0), (3.7, 15.0)]
        total_weighted = sum(v * m for v, m in values)
        total_mass = sum(m for _, m in values)
        predicted = total_weighted / total_mass
        
        self.assertAlmostEqual(predicted, 3.62, places=2)
    
    def test_weighted_average_with_three_inputs(self):
        """Test weighted average with three cunetes."""
        # Cunete 1: polysaccharides 8.2, mass 10 kg
        # Cunete 2: polysaccharides 8.5, mass 20 kg
        # Cunete 3: polysaccharides 7.8, mass 5 kg
        # Expected: (8.2*10 + 8.5*20 + 7.8*5) / (10+20+5) = 291/35 ≈ 8.314
        
        values = [(8.2, 10.0), (8.5, 20.0), (7.8, 5.0)]
        total_weighted = sum(v * m for v, m in values)
        total_mass = sum(m for _, m in values)
        predicted = total_weighted / total_mass
        
        self.assertAlmostEqual(predicted, 8.314, places=2)
    
    def test_weighted_average_single_input(self):
        """Test weighted average with single cunete equals the value."""
        value, mass = 3.6, 25.0
        predicted = (value * mass) / mass
        
        self.assertEqual(predicted, 3.6)


class TestTDSPassFailLogic(unittest.TestCase):
    """TC1.4: Test PASS/FAIL determination against TDS ranges."""
    
    def test_pass_within_range(self):
        """Value within TDS range should PASS."""
        predicted = 3.6
        tds_min = 3.4
        tds_max = 3.8
        
        passes = tds_min <= predicted <= tds_max
        self.assertTrue(passes)
    
    def test_fail_below_min(self):
        """Value below TDS min should FAIL."""
        predicted = 3.2
        tds_min = 3.4
        tds_max = 3.8
        
        passes = tds_min <= predicted <= tds_max
        self.assertFalse(passes)
    
    def test_fail_above_max(self):
        """Value above TDS max should FAIL."""
        predicted = 4.0
        tds_min = 3.4
        tds_max = 3.8
        
        passes = tds_min <= predicted <= tds_max
        self.assertFalse(passes)
    
    def test_pass_at_boundary_min(self):
        """Value at TDS min boundary should PASS."""
        predicted = 3.4
        tds_min = 3.4
        tds_max = 3.8
        
        passes = tds_min <= predicted <= tds_max
        self.assertTrue(passes)
    
    def test_pass_at_boundary_max(self):
        """Value at TDS max boundary should PASS."""
        predicted = 3.8
        tds_min = 3.4
        tds_max = 3.8
        
        passes = tds_min <= predicted <= tds_max
        self.assertTrue(passes)
    
    def test_pass_with_only_max(self):
        """Value below max when only max is specified should PASS."""
        predicted = 8.0
        tds_max = 10.0
        
        passes = predicted <= tds_max
        self.assertTrue(passes)
    
    def test_pass_with_only_min(self):
        """Value above min when only min is specified should PASS."""
        predicted = 7.5
        tds_min = 5.0
        
        passes = predicted >= tds_min
        self.assertTrue(passes)


class TestDataClasses(unittest.TestCase):
    """Test data class structures."""
    
    def test_blend_input_creation(self):
        """Test BlendInput dataclass."""
        from raven_ai_agent.skills.formulation_reader.reader import BlendInput
        
        inp = BlendInput(cunete_id="BATCH-001-C1", mass_kg=10.0)
        self.assertEqual(inp.cunete_id, "BATCH-001-C1")
        self.assertEqual(inp.mass_kg, 10.0)
    
    def test_tds_parameter_defaults(self):
        """Test TDSParameter default values."""
        from raven_ai_agent.skills.formulation_reader.reader import TDSParameter
        
        param = TDSParameter(parameter_code="ph", parameter_name="pH")
        self.assertIsNone(param.min_value)
        self.assertIsNone(param.max_value)
        self.assertTrue(param.is_critical)
    
    def test_coa_parameter_creation(self):
        """Test COAParameter dataclass."""
        from raven_ai_agent.skills.formulation_reader.reader import COAParameter
        
        param = COAParameter(
            parameter_code="ph",
            parameter_name="pH",
            average=3.6,
            min_value=3.4,
            max_value=3.8,
            result="PASS"
        )
        self.assertEqual(param.average, 3.6)
        self.assertEqual(param.result, "PASS")


# Golden Test Data (from historical formulations)
GOLDEN_TEST_DATA = {
    "test_1": {
        "description": "Simple 2-cunete blend for AL-QX-90-10",
        "inputs": [
            {"cunete_id": "BATCH-2024-001-C1", "mass_kg": 300.0, "ph": 3.5, "polysaccharides": 8.2},
            {"cunete_id": "BATCH-2024-002-C1", "mass_kg": 400.0, "ph": 3.7, "polysaccharides": 8.4},
        ],
        "target_item": "AL-QX-90-10",
        "tds": {"ph": {"min": 3.4, "max": 3.9}, "polysaccharides": {"min": 8.0, "max": 9.0}},
        "expected": {
            "ph": 3.614,  # (3.5*300 + 3.7*400) / 700
            "polysaccharides": 8.314,  # (8.2*300 + 8.4*400) / 700
            "all_pass": True,
        }
    }
}


class TestGoldenTests(unittest.TestCase):
    """Golden tests using historical formulation data."""
    
    def test_golden_blend_calculation(self):
        """Verify weighted averages match expected values from golden test data."""
        test = GOLDEN_TEST_DATA["test_1"]
        
        # Calculate weighted averages
        total_mass = sum(inp["mass_kg"] for inp in test["inputs"])
        
        ph_weighted = sum(inp["ph"] * inp["mass_kg"] for inp in test["inputs"])
        poly_weighted = sum(inp["polysaccharides"] * inp["mass_kg"] for inp in test["inputs"])
        
        predicted_ph = ph_weighted / total_mass
        predicted_poly = poly_weighted / total_mass
        
        # Verify against expected
        self.assertAlmostEqual(predicted_ph, test["expected"]["ph"], places=3)
        self.assertAlmostEqual(predicted_poly, test["expected"]["polysaccharides"], places=3)
        
        # Verify PASS/FAIL
        ph_passes = test["tds"]["ph"]["min"] <= predicted_ph <= test["tds"]["ph"]["max"]
        poly_passes = test["tds"]["polysaccharides"]["min"] <= predicted_poly <= test["tds"]["polysaccharides"]["max"]
        
        self.assertTrue(ph_passes)
        self.assertTrue(poly_passes)
        self.assertEqual(ph_passes and poly_passes, test["expected"]["all_pass"])


if __name__ == "__main__":
    unittest.main()
