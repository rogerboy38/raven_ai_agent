"""
Tests for Raymond-Lucy AI Agent
Run with: bench --site [site] run-tests --app raven_ai_agent
"""
import frappe
import unittest
import json
from unittest.mock import Mock, patch, MagicMock
import numpy as np


class TestVectorStore(unittest.TestCase):
    """Tests for vector store functionality"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures"""
        frappe.set_user("Administrator")
        
        # Create test settings
        if not frappe.db.exists("AI Agent Settings"):
            settings = frappe.get_doc({
                "doctype": "AI Agent Settings",
                "enabled": 1,
                "openai_api_key": "test-key",
                "model": "gpt-4o-mini"
            })
            settings.insert()
    
    def test_cosine_similarity(self):
        """Test cosine similarity calculation"""
        from raven_ai_agent.utils.vector_store import VectorStore
        
        # Identical vectors should have similarity 1.0
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(VectorStore.cosine_similarity(vec1, vec2), 1.0, places=5)
        
        # Orthogonal vectors should have similarity 0.0
        vec3 = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(VectorStore.cosine_similarity(vec1, vec3), 0.0, places=5)
        
        # Opposite vectors should have similarity -1.0
        vec4 = [-1.0, 0.0, 0.0]
        self.assertAlmostEqual(VectorStore.cosine_similarity(vec1, vec4), -1.0, places=5)
    
    @patch('raven_ai_agent.utils.vector_store.OpenAI')
    def test_get_embedding(self, mock_openai):
        """Test embedding generation"""
        from raven_ai_agent.utils.vector_store import VectorStore
        
        # Mock OpenAI response
        mock_embedding = [0.1] * 1536
        mock_response = Mock()
        mock_response.data = [Mock(embedding=mock_embedding)]
        mock_openai.return_value.embeddings.create.return_value = mock_response
        
        store = VectorStore()
        embedding = store.get_embedding("test text")
        
        self.assertEqual(len(embedding), 1536)
        self.assertEqual(embedding, mock_embedding)
    
    @patch('raven_ai_agent.utils.vector_store.OpenAI')
    def test_store_memory_with_embedding(self, mock_openai):
        """Test storing memory with embedding"""
        from raven_ai_agent.utils.vector_store import VectorStore
        
        # Mock OpenAI
        mock_embedding = [0.1] * 1536
        mock_response = Mock()
        mock_response.data = [Mock(embedding=mock_embedding)]
        mock_openai.return_value.embeddings.create.return_value = mock_response
        
        store = VectorStore()
        memory_name = store.store_memory_with_embedding(
            user="Administrator",
            content="Test memory content",
            importance="High",
            memory_type="Fact"
        )
        
        self.assertIsNotNone(memory_name)
        
        # Verify memory was stored
        memory = frappe.get_doc("AI Memory", memory_name)
        self.assertEqual(memory.content, "Test memory content")
        self.assertEqual(memory.importance, "High")
        self.assertIsNotNone(memory.embedding)
        
        # Cleanup
        frappe.delete_doc("AI Memory", memory_name)


class TestRaymondLucyAgent(unittest.TestCase):
    """Tests for the main agent class"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures"""
        frappe.set_user("Administrator")
    
    def test_determine_autonomy_level_1(self):
        """Test autonomy detection for read-only queries"""
        from raven_ai_agent.api.agent import RaymondLucyAgent
        
        with patch.object(RaymondLucyAgent, '_get_settings', return_value={"openai_api_key": "test"}):
            with patch('raven_ai_agent.api.agent.OpenAI'):
                agent = RaymondLucyAgent("Administrator")
                
                # Read-only queries should be Level 1
                self.assertEqual(agent.determine_autonomy("Show me invoices"), 1)
                self.assertEqual(agent.determine_autonomy("What are my sales?"), 1)
                self.assertEqual(agent.determine_autonomy("List customers"), 1)
    
    def test_determine_autonomy_level_2(self):
        """Test autonomy detection for modification queries"""
        from raven_ai_agent.api.agent import RaymondLucyAgent
        
        with patch.object(RaymondLucyAgent, '_get_settings', return_value={"openai_api_key": "test"}):
            with patch('raven_ai_agent.api.agent.OpenAI'):
                agent = RaymondLucyAgent("Administrator")
                
                # Modification queries should be Level 2
                self.assertEqual(agent.determine_autonomy("Update the customer name"), 2)
                self.assertEqual(agent.determine_autonomy("Change the price"), 2)
                self.assertEqual(agent.determine_autonomy("Modify the order"), 2)
    
    def test_determine_autonomy_level_3(self):
        """Test autonomy detection for dangerous operations"""
        from raven_ai_agent.api.agent import RaymondLucyAgent
        
        with patch.object(RaymondLucyAgent, '_get_settings', return_value={"openai_api_key": "test"}):
            with patch('raven_ai_agent.api.agent.OpenAI'):
                agent = RaymondLucyAgent("Administrator")
                
                # Dangerous operations should be Level 3
                self.assertEqual(agent.determine_autonomy("Delete all invoices"), 3)
                self.assertEqual(agent.determine_autonomy("Submit the document"), 3)
                self.assertEqual(agent.determine_autonomy("Create invoice and submit"), 3)
    
    def test_get_morning_briefing_empty(self):
        """Test morning briefing with no memories"""
        from raven_ai_agent.api.agent import RaymondLucyAgent
        
        with patch.object(RaymondLucyAgent, '_get_settings', return_value={"openai_api_key": "test"}):
            with patch('raven_ai_agent.api.agent.OpenAI'):
                agent = RaymondLucyAgent("test_user_empty@example.com")
                briefing = agent.get_morning_briefing()
                
                self.assertIn("Morning Briefing", briefing)
    
    def test_get_erpnext_context_invoices(self):
        """Test ERPNext context retrieval for invoice queries"""
        from raven_ai_agent.api.agent import RaymondLucyAgent
        
        with patch.object(RaymondLucyAgent, '_get_settings', return_value={"openai_api_key": "test"}):
            with patch('raven_ai_agent.api.agent.OpenAI'):
                agent = RaymondLucyAgent("Administrator")
                context = agent.get_erpnext_context("Show me recent invoices")
                
                # Should attempt to query Sales Invoice
                self.assertIsInstance(context, str)


class TestAIMemoryDoctype(unittest.TestCase):
    """Tests for AI Memory doctype"""
    
    def test_create_memory(self):
        """Test creating a memory document"""
        memory = frappe.get_doc({
            "doctype": "AI Memory",
            "user": "Administrator",
            "content": "Test memory",
            "importance": "Normal",
            "memory_type": "Fact"
        })
        memory.insert()
        
        self.assertIsNotNone(memory.name)
        self.assertEqual(memory.content, "Test memory")
        
        # Cleanup
        frappe.delete_doc("AI Memory", memory.name)
    
    def test_memory_importance_levels(self):
        """Test all importance levels"""
        for importance in ["Critical", "High", "Normal", "Low"]:
            memory = frappe.get_doc({
                "doctype": "AI Memory",
                "user": "Administrator",
                "content": f"Test {importance} memory",
                "importance": importance,
                "memory_type": "Fact"
            })
            memory.insert()
            
            loaded = frappe.get_doc("AI Memory", memory.name)
            self.assertEqual(loaded.importance, importance)
            
            frappe.delete_doc("AI Memory", memory.name)
    
    def test_memory_types(self):
        """Test all memory types"""
        for memory_type in ["Fact", "Preference", "Summary", "Correction"]:
            memory = frappe.get_doc({
                "doctype": "AI Memory",
                "user": "Administrator",
                "content": f"Test {memory_type}",
                "importance": "Normal",
                "memory_type": memory_type
            })
            memory.insert()
            
            loaded = frappe.get_doc("AI Memory", memory.name)
            self.assertEqual(loaded.memory_type, memory_type)
            
            frappe.delete_doc("AI Memory", memory.name)


class TestProtocolCompliance(unittest.TestCase):
    """Tests for Raymond-Lucy Protocol compliance"""
    
    def test_raymond_protocol_confidence_levels(self):
        """Test that responses include confidence levels"""
        from raven_ai_agent.api.agent import SYSTEM_PROMPT
        
        # Verify system prompt includes confidence requirements
        self.assertIn("CONFIDENCE", SYSTEM_PROMPT)
        self.assertIn("HIGH", SYSTEM_PROMPT)
        self.assertIn("MEDIUM", SYSTEM_PROMPT)
        self.assertIn("LOW", SYSTEM_PROMPT)
        self.assertIn("UNCERTAIN", SYSTEM_PROMPT)
    
    def test_memento_protocol_importance_tags(self):
        """Test that importance levels are defined"""
        from raven_ai_agent.api.agent import SYSTEM_PROMPT
        
        self.assertIn("CRITICAL", SYSTEM_PROMPT)
        self.assertIn("HIGH", SYSTEM_PROMPT)
        self.assertIn("NORMAL", SYSTEM_PROMPT)
    
    def test_lucy_protocol_session_management(self):
        """Test that session management is mentioned"""
        from raven_ai_agent.api.agent import SYSTEM_PROMPT
        
        self.assertIn("morning briefing", SYSTEM_PROMPT.lower())
        self.assertIn("session", SYSTEM_PROMPT.lower())
    
    def test_karpathy_protocol_autonomy_levels(self):
        """Test that autonomy levels are defined"""
        from raven_ai_agent.api.agent import SYSTEM_PROMPT
        
        self.assertIn("LEVEL 1", SYSTEM_PROMPT)
        self.assertIn("LEVEL 2", SYSTEM_PROMPT)
        self.assertIn("LEVEL 3", SYSTEM_PROMPT)
        self.assertIn("COPILOT", SYSTEM_PROMPT)
        self.assertIn("COMMAND", SYSTEM_PROMPT)
        self.assertIn("AGENT", SYSTEM_PROMPT)


class TestAPIEndpoints(unittest.TestCase):
    """Tests for API endpoints"""
    
    def test_process_message_endpoint(self):
        """Test the main message processing endpoint"""
        from raven_ai_agent.api.agent import process_message
        
        # Should be a whitelisted function
        self.assertTrue(hasattr(process_message, 'is_whitelisted'))
    
    def test_vector_search_endpoint(self):
        """Test vector search endpoint"""
        from raven_ai_agent.utils.vector_store import vector_search
        
        self.assertTrue(hasattr(vector_search, 'is_whitelisted'))
    
    def test_store_with_embedding_endpoint(self):
        """Test store with embedding endpoint"""
        from raven_ai_agent.utils.vector_store import store_with_embedding
        
        self.assertTrue(hasattr(store_with_embedding, 'is_whitelisted'))


class TestMemoryUtilities(unittest.TestCase):
    """Tests for memory utility functions"""
    
    def test_search_similar_memories(self):
        """Test keyword-based memory search"""
        from raven_ai_agent.utils.memory import search_similar_memories
        
        # Create test memory
        memory = frappe.get_doc({
            "doctype": "AI Memory",
            "user": "Administrator",
            "content": "User prefers dark mode interface",
            "importance": "Normal",
            "memory_type": "Preference"
        })
        memory.insert()
        
        # Search for it
        results = search_similar_memories("Administrator", "dark mode")
        
        # Should find the memory
        found = any(r.content == "User prefers dark mode interface" for r in results)
        self.assertTrue(found)
        
        # Cleanup
        frappe.delete_doc("AI Memory", memory.name)


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestVectorStore))
    suite.addTests(loader.loadTestsFromTestCase(TestRaymondLucyAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestAIMemoryDoctype))
    suite.addTests(loader.loadTestsFromTestCase(TestProtocolCompliance))
    suite.addTests(loader.loadTestsFromTestCase(TestAPIEndpoints))
    suite.addTests(loader.loadTestsFromTestCase(TestMemoryUtilities))
    
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


if __name__ == "__main__":
    run_tests()
