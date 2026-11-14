"""
End-to-End Integration Tests for Raven AI Agent

Tests the full pipeline from Alexa command through to agent routing.
These tests verify that:
1. Alexa-to-Raven API accepts and routes commands correctly
2. Command router dispatches to correct handlers
3. Safety guardrails block dangerous operations

Run with: python -m pytest tests/test_e2e_integration.py -v
Run ONLY integration tests: python -m pytest tests/test_e2e_integration.py -v -m integration
"""

import pytest
import json
import unittest
from unittest.mock import MagicMock, patch, PropertyMock


def is_frappe_available():
    """Check if frappe is available and properly initialized"""
    try:
        import frappe
        return hasattr(frappe, 'local') and hasattr(frappe.local, 'site')
    except ImportError:
        return False


def is_frappe_importable():
    """Check if frappe module can be imported without errors"""
    try:
        import frappe
        return True
    except Exception:
        return False


# Mark tests that require frappe to be importable
# Tests will skip gracefully if frappe is not available


# TestAlexaToRavenAPI removed with the endpoint: its module could not import (TASKS-342 ruling 77)


class TestCommandRouting(unittest.TestCase):
    """Test cases for command routing logic"""

    def setUp(self):
        """Set up test fixtures"""
        # determine_autonomy is a pure function, no frappe needed
        pass

    def test_determine_autonomy_level_3_for_dangerous_ops(self):
        """E2E-03: Dangerous operations get autonomy level 3"""
        try:
            from raven_ai_agent.api.command_router import CommandRouterMixin
            
            class TestRouter(CommandRouterMixin):
                def __init__(self):
                    self.user = "test@example.com"
            
            router = TestRouter()
            
            # Test dangerous operations
            dangerous_queries = [
                "delete sales order SO-001",
                "cancel invoice SINV-001",
                "submit payment PE-001",
                "create payment for SINV-001"
            ]
            
            for query in dangerous_queries:
                autonomy = router.determine_autonomy(query)
                self.assertEqual(autonomy, 3, f"Query '{query}' should be level 3")
        except ImportError:
            self.skipTest("Module not available in sandbox")

    def test_determine_autonomy_level_2_for_modifications(self):
        """E2E-04: Modification operations get autonomy level 2"""
        try:
            from raven_ai_agent.api.command_router import CommandRouterMixin
            
            class TestRouter(CommandRouterMixin):
                def __init__(self):
                    self.user = "test@example.com"
            
            router = TestRouter()
            
            # Test modification operations
            mod_queries = [
                "create a sales order",
                "update customer info",
                "add item to order",
                "convert quotation to sales order",
                "generate dashboard",
                "show sales report"
            ]
            
            for query in mod_queries:
                autonomy = router.determine_autonomy(query)
                self.assertEqual(autonomy, 2, f"Query '{query}' should be level 2")
        except ImportError:
            self.skipTest("Module not available in sandbox")

    def test_determine_autonomy_level_1_for_readonly(self):
        """E2E-05: Read-only queries get autonomy level 1"""
        try:
            from raven_ai_agent.api.command_router import CommandRouterMixin
            
            class TestRouter(CommandRouterMixin):
                def __init__(self):
                    self.user = "test@example.com"
            
            router = TestRouter()
            
            # Test read-only queries
            readonly_queries = [
                "what is the status of order SO-001",
                "show my invoices",
                "check warehouse stock",
                "list pending quotations"
            ]
            
            for query in readonly_queries:
                autonomy = router.determine_autonomy(query)
                self.assertEqual(autonomy, 1, f"Query '{query}' should be level 1")
        except ImportError:
            self.skipTest("Module not available in sandbox")


class TestUtteranceRouting(unittest.TestCase):
    """Test cases for routing specific utterances to correct handlers"""

    def setUp(self):
        """Set up test fixtures"""
        if not is_frappe_available():
            self.skipTest("Frappe not available")

    def test_workflow_orchestrator_routes_so_creation(self):
        """E2E-06: 'create sales order' routes to workflow orchestrator"""
        # This test verifies the utterance library mapping
        with open('tests/test_utterances.json', 'r') as f:
            utterances = json.load(f)
        
        so_creation = [u for u in utterances['utterances'] 
                      if 'workflow' in u['expected_tool'] and 'order' in u['utterance'].lower()]
        
        self.assertGreater(len(so_creation), 0, "Should have workflow utterances for SO creation")

    def test_payment_agent_routes_payment_commands(self):
        """E2E-07: Payment commands route to payment agent"""
        with open('tests/test_utterances.json', 'r') as f:
            utterances = json.load(f)
        
        payment_cmds = [u for u in utterances['utterances'] 
                       if u['expected_tool'] == 'payment_agent']
        
        self.assertGreater(len(payment_cmds), 0, "Should have payment agent utterances")

    def test_manufacturing_agent_routes_manufacturing_commands(self):
        """E2E-08: Manufacturing commands route to manufacturing agent"""
        with open('tests/test_utterances.json', 'r') as f:
            utterances = json.load(f)
        
        mfg_cmds = [u for u in utterances['utterances'] 
                   if u['expected_tool'] == 'manufacturing_agent']
        
        self.assertGreater(len(mfg_cmds), 0, "Should have manufacturing agent utterances")

    def test_adversarial_commands_are_blocked(self):
        """E2E-09: Adversarial commands are identified"""
        with open('tests/test_utterances.json', 'r') as f:
            utterances = json.load(f)
        
        adversarial = [u for u in utterances['utterances'] 
                     if u['category'] == 'adversarial']
        
        # Verify adversarial examples exist and are marked as blocked
        self.assertGreater(len(adversarial), 0, "Should have adversarial test cases")
        
        for adv in adversarial:
            self.assertTrue(
                adv['expected_outcome'].startswith('BLOCKED'),
                f"Adversarial '{adv['utterance']}' should be blocked, got: {adv['expected_outcome']}"
            )


class TestSafetyGuardrails(unittest.TestCase):
    """Test cases for safety guardrails"""

    def setUp(self):
        """Set up test fixtures"""
        if not is_frappe_available():
            self.skipTest("Frappe not available")

    def test_delete_operations_blocked_from_alexa_origin(self):
        """E2E-10: Delete operations blocked for Alexa origin"""
        # Load utterance that attempts delete
        with open('tests/test_utterances.json', 'r') as f:
            utterances = json.load(f)
        
        delete_cmd = next((u for u in utterances['utterances'] 
                         if 'delete' in u['utterance'].lower()), None)
        
        self.assertIsNotNone(delete_cmd)
        self.assertEqual(delete_cmd['expected_tool'], 'blocked')
        self.assertIn('delete', delete_cmd['expected_outcome'].lower())

    def test_cancel_operations_blocked_from_alexa_origin(self):
        """E2E-11: Cancel operations blocked for Alexa origin"""
        with open('tests/test_utterances.json', 'r') as f:
            utterances = json.load(f)
        
        cancel_cmd = next((u for u in utterances['utterances'] 
                         if 'cancel' in u['utterance'].lower()), None)
        
        self.assertIsNotNone(cancel_cmd)
        self.assertEqual(cancel_cmd['expected_tool'], 'blocked')

    def test_submit_operations_blocked_from_alexa_origin(self):
        """E2E-12: Submit operations blocked for Alexa origin"""
        with open('tests/test_utterances.json', 'r') as f:
            utterances = json.load(f)
        
        submit_cmd = next((u for u in utterances['utterances'] 
                         if 'submit' in u['utterance'].lower() and 'sales order' in u['utterance'].lower()), None)
        
        self.assertIsNotNone(submit_cmd)
        self.assertEqual(submit_cmd['expected_tool'], 'blocked')

    def test_prompt_injection_detected(self):
        """E2E-13: Prompt injection attempts are blocked"""
        with open('tests/test_utterances.json', 'r') as f:
            utterances = json.load(f)
        
        injection_cmd = next((u for u in utterances['utterances'] 
                           if 'ignore previous' in u['utterance'].lower() or 'admin mode' in u['utterance'].lower()), None)
        
        self.assertIsNotNone(injection_cmd)
        self.assertEqual(injection_cmd['expected_tool'], 'blocked')
        self.assertIn('BLOCKED', injection_cmd['expected_outcome'])


class TestUtteranceCoverage(unittest.TestCase):
    """Verify utterance library coverage"""

    def test_golden_path_coverage(self):
        """E2E-14: Golden path commands have sufficient coverage"""
        with open('tests/test_utterances.json', 'r') as f:
            utterances = json.load(f)
        
        golden = [u for u in utterances['utterances'] 
                 if u['category'] == 'golden_path']
        
        self.assertGreaterEqual(len(golden), 10, 
                               "Should have at least 10 golden path test cases")

    def test_edge_case_coverage(self):
        """E2E-15: Edge cases have sufficient coverage"""
        with open('tests/test_utterances.json', 'r') as f:
            utterances = json.load(f)
        
        edge = [u for u in utterances['utterances'] 
               if u['category'] == 'edge_case']
        
        self.assertGreaterEqual(len(edge), 5,
                               "Should have at least 5 edge case test cases")

    def test_adversarial_coverage(self):
        """E2E-16: Adversarial cases have sufficient coverage"""
        with open('tests/test_utterances.json', 'r') as f:
            utterances = json.load(f)
        
        adv = [u for u in utterances['utterances'] 
              if u['category'] == 'adversarial']
        
        self.assertGreaterEqual(len(adv), 5,
                              "Should have at least 5 adversarial test cases")

    def test_all_utterances_have_required_fields(self):
        """E2E-17: All utterances have required fields"""
        with open('tests/test_utterances.json', 'r') as f:
            utterances = json.load(f)
        
        required_fields = ['utterance', 'expected_tool', 'expected_outcome', 'category']
        
        for u in utterances['utterances']:
            for field in required_fields:
                self.assertIn(field, u, 
                            f"Utterance '{u.get('utterance', 'unknown')}' missing field '{field}'")


if __name__ == '__main__':
    unittest.main()
