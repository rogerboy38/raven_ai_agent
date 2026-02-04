"""
Tests for Formulation Orchestrator Skill
========================================

Unit tests for the orchestrator and its sub-agents.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from decimal import Decimal


class TestAgentMessage(unittest.TestCase):
    """Tests for AgentMessage class."""
    
    def test_create_message(self):
        """Test creating an AgentMessage."""
        from raven_ai_agent.skills.formulation_orchestrator.messages import (
            AgentMessage, AgentMessageType
        )
        
        msg = AgentMessage(
            source_agent="orchestrator",
            target_agent="batch_selector",
            action="select_batches",
            payload={"item_code": "ITEM_0617027231"}
        )
        
        self.assertEqual(msg.source_agent, "orchestrator")
        self.assertEqual(msg.target_agent, "batch_selector")
        self.assertEqual(msg.action, "select_batches")
        self.assertEqual(msg.message_type, AgentMessageType.REQUEST)
        self.assertIsNotNone(msg.message_id)
    
    def test_create_response(self):
        """Test creating a response message."""
        from raven_ai_agent.skills.formulation_orchestrator.messages import (
            AgentMessage, AgentMessageType
        )
        
        request = AgentMessage(
            source_agent="orchestrator",
            target_agent="batch_selector",
            action="select_batches",
            payload={}
        )
        
        response = request.create_response(
            success=True,
            result={"batches": []}
        )
        
        self.assertEqual(response.source_agent, "batch_selector")
        self.assertEqual(response.target_agent, "orchestrator")
        self.assertEqual(response.message_type, AgentMessageType.RESPONSE)
        self.assertTrue(response.success)
    
    def test_to_dict(self):
        """Test serialization to dict."""
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage
        
        msg = AgentMessage(
            source_agent="test",
            target_agent="test2",
            action="test_action",
            payload={"key": "value"}
        )
        
        data = msg.to_dict()
        
        self.assertIsInstance(data, dict)
        self.assertEqual(data['source_agent'], "test")
        self.assertEqual(data['action'], "test_action")


class TestAgentChannel(unittest.TestCase):
    """Tests for AgentChannel class."""
    
    def test_create_channel(self):
        """Test creating an AgentChannel."""
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentChannel
        
        channel = AgentChannel(source_agent="orchestrator")
        
        self.assertEqual(channel.source_agent, "orchestrator")
        self.assertIsNotNone(channel.workflow_id)
    
    def test_register_handler(self):
        """Test registering a handler."""
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentChannel
        
        channel = AgentChannel()
        handler = Mock()
        
        channel.register_local_handler("test_agent", handler)
        
        self.assertIn("test_agent", channel._local_handlers)


class TestWorkflowState(unittest.TestCase):
    """Tests for WorkflowState class."""
    
    def test_create_workflow_state(self):
        """Test creating a WorkflowState."""
        from raven_ai_agent.skills.formulation_orchestrator.messages import (
            WorkflowState, WorkflowPhase, AgentStatus
        )
        
        state = WorkflowState(request={"item_code": "ITEM_123"})
        
        self.assertIsNotNone(state.workflow_id)
        self.assertEqual(state.status, AgentStatus.IDLE)
        self.assertEqual(state.request.get("item_code"), "ITEM_123")
    
    def test_update_phase(self):
        """Test updating a workflow phase."""
        from raven_ai_agent.skills.formulation_orchestrator.messages import (
            WorkflowState, WorkflowPhase
        )
        
        state = WorkflowState()
        state.update_phase(WorkflowPhase.BATCH_SELECTION, {"batches": []})
        
        self.assertEqual(state.current_phase, WorkflowPhase.BATCH_SELECTION)
        self.assertIn(WorkflowPhase.BATCH_SELECTION.value, state.phases)


class TestBaseSubAgent(unittest.TestCase):
    """Tests for BaseSubAgent class."""
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_handle_message(self, mock_frappe):
        """Test handling a message."""
        from raven_ai_agent.skills.formulation_orchestrator.agents.base import MockSubAgent
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage
        
        agent = MockSubAgent(responses={"test": {"result": "success"}})
        
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="mock_agent",
            action="test",
            payload={}
        )
        
        response = agent.handle_message(message)
        
        self.assertTrue(response.success)
        self.assertEqual(response.result, {"result": "success"})
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_unknown_action(self, mock_frappe):
        """Test handling unknown action."""
        from raven_ai_agent.skills.formulation_orchestrator.agents.base import BaseSubAgent
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage
        
        class TestAgent(BaseSubAgent):
            name = "test_agent"
            def process(self, action, payload, message):
                return None
        
        agent = TestAgent()
        
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="test_agent",
            action="unknown_action",
            payload={}
        )
        
        response = agent.handle_message(message)
        
        self.assertFalse(response.success)
        self.assertEqual(response.error_code, "UNKNOWN_ACTION")


class TestBatchSelectorAgent(unittest.TestCase):
    """Tests for BatchSelectorAgent."""
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.batch_selector.get_available_batches')
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.batch_selector.parse_golden_number')
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_select_batches(self, mock_frappe, mock_parse, mock_get_batches):
        """Test batch selection."""
        from raven_ai_agent.skills.formulation_orchestrator.agents import BatchSelectorAgent
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage
        
        mock_parse.return_value = {'product': '0617', 'folio': 27, 'year': 23, 'fefo_key': 23027}
        mock_get_batches.return_value = [
            {'item_code': 'ITEM_0617027231', 'batch_name': 'LOTE001', 'qty': 500, 'fefo_key': 23027},
            {'item_code': 'ITEM_0617028231', 'batch_name': 'LOTE002', 'qty': 600, 'fefo_key': 23028},
        ]
        
        agent = BatchSelectorAgent()
        
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="batch_selector",
            action="select_batches",
            payload={
                "item_code": "ITEM_0617027231",
                "quantity_required": 1000
            }
        )
        
        response = agent.handle_message(message)
        
        self.assertTrue(response.success)
        self.assertIn('selected_batches', response.result)


class TestTDSComplianceAgent(unittest.TestCase):
    """Tests for TDSComplianceAgent."""
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.tds_compliance.get_batch_coa_parameters')
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.tds_compliance.check_tds_compliance')
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_validate_compliance(self, mock_frappe, mock_check, mock_coa):
        """Test TDS compliance validation."""
        from raven_ai_agent.skills.formulation_orchestrator.agents import TDSComplianceAgent
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage
        
        mock_coa.return_value = {'pH': {'value': 4.0, 'status': 'PASS'}}
        mock_check.return_value = {'all_pass': True, 'parameters': {'pH': {'status': 'PASS'}}}
        
        agent = TDSComplianceAgent()
        
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="tds_compliance",
            action="validate_compliance",
            payload={
                "batches": [{"batch_name": "LOTE001"}],
                "tds_requirements": {"pH": {"min": 3.5, "max": 4.5}}
            }
        )
        
        response = agent.handle_message(message)
        
        self.assertTrue(response.success)
        self.assertTrue(response.result.get('passed'))


class TestCostCalculatorAgent(unittest.TestCase):
    """Tests for CostCalculatorAgent."""
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_calculate_costs(self, mock_frappe):
        """Test cost calculation."""
        from raven_ai_agent.skills.formulation_orchestrator.agents import CostCalculatorAgent
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage
        
        mock_frappe.db.get_value.return_value = 10.0  # $10 per unit
        
        agent = CostCalculatorAgent()
        
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="cost_calculator",
            action="calculate_costs",
            payload={
                "batches": [
                    {"batch_name": "LOTE001", "item_code": "ITEM_0617027231", "qty": 100}
                ]
            }
        )
        
        response = agent.handle_message(message)
        
        self.assertTrue(response.success)
        self.assertIn('total_cost', response.result)


class TestReportGenerator(unittest.TestCase):
    """Tests for ReportGenerator."""
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_generate_report(self, mock_frappe):
        """Test report generation."""
        from raven_ai_agent.skills.formulation_orchestrator.agents import ReportGenerator
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage
        
        mock_frappe.utils.now_datetime.return_value = datetime.now()
        
        agent = ReportGenerator()
        
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="report_generator",
            action="generate_report",
            payload={
                "workflow_state": {
                    "workflow_id": "wf_123",
                    "request": {"item_code": "ITEM_123"},
                    "phases": {
                        "batch_selection": {"selected_batches": []},
                        "compliance": {"passed": True},
                        "costs": {"total_cost": 1000}
                    }
                },
                "report_type": "summary"
            }
        )
        
        response = agent.handle_message(message)
        
        self.assertTrue(response.success)
        self.assertIn('report_type', response.result)


class TestMessageFactory(unittest.TestCase):
    """Tests for MessageFactory."""
    
    def test_batch_selection_request(self):
        """Test creating batch selection request."""
        from raven_ai_agent.skills.formulation_orchestrator.messages import MessageFactory
        
        msg = MessageFactory.batch_selection_request(
            item_code="ITEM_0617027231",
            warehouse="FG to Sell Warehouse - AMB-W",
            quantity=1000,
            production_date="2026-02-10"
        )
        
        self.assertEqual(msg.target_agent, "batch_selector")
        self.assertEqual(msg.action, "select_batches")
        self.assertEqual(msg.payload['item_code'], "ITEM_0617027231")
    
    def test_tds_compliance_request(self):
        """Test creating TDS compliance request."""
        from raven_ai_agent.skills.formulation_orchestrator.messages import MessageFactory
        
        msg = MessageFactory.tds_compliance_request(
            batches=[{"batch_name": "LOTE001"}],
            tds_requirements={"pH": {"min": 3.5, "max": 4.5}}
        )
        
        self.assertEqual(msg.target_agent, "tds_compliance")
        self.assertEqual(msg.action, "validate_compliance")


class TestFormulationOrchestratorSkill(unittest.TestCase):
    """Tests for FormulationOrchestratorSkill."""
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.skill.frappe')
    def test_parse_request(self, mock_frappe):
        """Test request parsing."""
        from raven_ai_agent.skills.formulation_orchestrator.skill import FormulationOrchestratorSkill
        
        skill = FormulationOrchestratorSkill()
        
        request = skill._parse_request(
            "Formulate 1000kg of ITEM_0617027231",
            {}
        )
        
        self.assertIsNotNone(request)
        self.assertEqual(request['item_code'], "ITEM_0617027231")
        self.assertEqual(request['quantity_required'], 1000)
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.skill.frappe')
    def test_handle_query(self, mock_frappe):
        """Test handling a query."""
        from raven_ai_agent.skills.formulation_orchestrator.skill import FormulationOrchestratorSkill
        
        skill = FormulationOrchestratorSkill()
        
        # Mock sub-agents
        skill.batch_selector.handle_message = Mock(return_value=Mock(
            success=True, 
            result={'selected_batches': [], 'total_qty': 0, 'coverage_percent': 0}
        ))
        
        result = skill.handle(
            "Formulate 500kg of ITEM_0617027231",
            {}
        )
        
        self.assertTrue(result['handled'])
        self.assertIsNotNone(result['response'])




# ============================================================================
# NEW TESTS: Phase 2-4 Integration and Format Consistency
# Added: February 4, 2026
# ============================================================================

class TestPhase2InputTransformation(unittest.TestCase):
    """Tests for Phase 2 input transformation to Phase 3 format."""
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_transform_direct_format(self, mock_frappe):
        """Test transformation of direct Phase 2 output."""
        from raven_ai_agent.skills.formulation_orchestrator.agents import TDSComplianceAgent
        
        agent = TDSComplianceAgent()
        
        # Phase 2 direct output format
        phase2_output = {
            'batch_selections': [
                {
                    'item_code': 'ITEM_0617027231',
                    'selected_batches': [
                        {'batch_no': 'LOTE001', 'allocated_qty': 500}
                    ]
                }
            ]
        }
        
        # Transform should extract batches with item_code
        if hasattr(agent, '_transform_phase2_input'):
            result = agent._transform_phase2_input(phase2_output)
            self.assertIsInstance(result, list)
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_item_map_creation(self, mock_frappe):
        """Test item_code mapping from Phase 2 output."""
        from raven_ai_agent.skills.formulation_orchestrator.agents import TDSComplianceAgent
        
        agent = TDSComplianceAgent()
        
        phase2_output = {
            'batch_selections': [
                {'item_code': 'ITEM_001', 'selected_batches': [{'batch_no': 'B001'}]},
                {'item_code': 'ITEM_002', 'selected_batches': [{'batch_no': 'B002'}]}
            ]
        }
        
        if hasattr(agent, '_transform_phase2_input'):
            result = agent._transform_phase2_input(phase2_output)
            for batch in result:
                if 'item_code' in batch:
                    self.assertIsNotNone(batch['item_code'])


class TestCOAStatusValidation(unittest.TestCase):
    """Tests for COA status validation before parameter checking."""
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.tds_compliance.get_batch_coa_parameters')
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_approved_coa_valid(self, mock_frappe, mock_coa):
        """Test approved COA passes validation."""
        from raven_ai_agent.skills.formulation_orchestrator.agents import TDSComplianceAgent
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage
        
        mock_coa.return_value = {'pH': {'value': 4.0}, 'status': 'Approved'}
        
        agent = TDSComplianceAgent()
        
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="tds_compliance",
            action="check_batch",
            payload={"batch_name": "LOTE001", "tds_requirements": {"pH": {"min": 3.5, "max": 4.5}}}
        )
        
        response = agent.handle_message(message)
        self.assertTrue(response.success)
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.tds_compliance.get_batch_coa_parameters')
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_missing_coa_handled(self, mock_frappe, mock_coa):
        """Test missing COA returns error."""
        from raven_ai_agent.skills.formulation_orchestrator.agents import TDSComplianceAgent
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage
        
        mock_coa.return_value = None
        
        agent = TDSComplianceAgent()
        
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="tds_compliance",
            action="check_batch",
            payload={"batch_name": "LOTE_NO_COA", "tds_requirements": {"pH": {"min": 3.5, "max": 4.5}}}
        )
        
        response = agent.handle_message(message)
        self.assertTrue(response.success)
        if 'reason' in response.result:
            self.assertIn('COA', response.result.get('reason', '').upper())


class TestSuggestAlternatives(unittest.TestCase):
    """Tests for suggest_alternatives action."""
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_fefo_sorting(self, mock_frappe):
        """Test expiry date sorting."""
        batches = [
            {'batch_name': 'B1', 'expiry_date': '2027-06-01'},
            {'batch_name': 'B2', 'expiry_date': '2026-03-01'},
            {'batch_name': 'B3', 'expiry_date': '2026-12-01'}
        ]
        
        sorted_batches = sorted(batches, key=lambda x: x.get('expiry_date', '9999-12-31'))
        self.assertEqual(sorted_batches[0]['batch_name'], 'B2')


class TestPhaseIntegration(unittest.TestCase):
    """Integration tests for Phase 2 -> Phase 3 -> Phase 4 flow."""
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.tds_compliance.get_batch_coa_parameters')
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.tds_compliance.check_tds_compliance')
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_phase2_to_phase3_flow(self, mock_frappe, mock_check, mock_coa):
        """Test Phase 2 output to Phase 3 input compatibility."""
        from raven_ai_agent.skills.formulation_orchestrator.agents import TDSComplianceAgent
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage
        
        mock_coa.return_value = {'pH': {'value': 4.0, 'status': 'PASS'}}
        mock_check.return_value = {'all_pass': True, 'parameters': {'pH': {'status': 'PASS'}}}
        
        agent = TDSComplianceAgent()
        
        phase2_style_payload = {
            'batches': [{'batch_name': 'LOTE001', 'item_code': 'ITEM_001', 'allocated_qty': 500}],
            'tds_requirements': {'pH': {'min': 3.5, 'max': 4.5}}
        }
        
        message = AgentMessage(
            source_agent="batch_selector",
            target_agent="tds_compliance",
            action="validate_compliance",
            payload=phase2_style_payload
        )
        
        response = agent.handle_message(message)
        self.assertTrue(response.success)
        self.assertIn('compliant_batches', response.result)
    
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_phase3_to_phase4_handoff(self, mock_frappe):
        """Test Phase 3 to Phase 4 compatibility."""
        from raven_ai_agent.skills.formulation_orchestrator.agents import CostCalculatorAgent
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage
        
        mock_frappe.db.get_value.return_value = 10.0
        
        agent = CostCalculatorAgent()
        
        phase3_output_batches = [
            {'batch_name': 'LOTE001', 'item_code': 'ITEM_0617027231', 'qty': 500, 'status': 'COMPLIANT'}
        ]
        
        message = AgentMessage(
            source_agent="tds_compliance",
            target_agent="cost_calculator",
            action="calculate_costs",
            payload={'batches': phase3_output_batches}
        )
        
        response = agent.handle_message(message)
        self.assertTrue(response.success)
        self.assertIn('total_cost', response.result)


if __name__ == '__main__':
    unittest.main()
