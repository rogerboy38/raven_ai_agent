"""
Standalone Unit Tests (No Frappe Required)
Run with: pytest test_standalone.py -v
"""
import pytest
import numpy as np
import json
from unittest.mock import Mock, patch, MagicMock


class TestCosineSimilarity:
    """Test cosine similarity calculations"""
    
    @staticmethod
    def cosine_similarity(a, b):
        """Local implementation for testing"""
        a = np.array(a)
        b = np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    
    def test_identical_vectors(self):
        """Identical vectors should have similarity 1.0"""
        vec = [1.0, 2.0, 3.0]
        assert abs(self.cosine_similarity(vec, vec) - 1.0) < 0.0001
    
    def test_orthogonal_vectors(self):
        """Orthogonal vectors should have similarity 0.0"""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        assert abs(self.cosine_similarity(vec1, vec2)) < 0.0001
    
    def test_opposite_vectors(self):
        """Opposite vectors should have similarity -1.0"""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [-1.0, 0.0, 0.0]
        assert abs(self.cosine_similarity(vec1, vec2) + 1.0) < 0.0001
    
    def test_similar_vectors(self):
        """Similar vectors should have high similarity"""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [1.1, 2.1, 3.1]
        similarity = self.cosine_similarity(vec1, vec2)
        assert similarity > 0.99
    
    def test_high_dimensional_vectors(self):
        """Test with high-dimensional vectors (like embeddings)"""
        np.random.seed(42)
        vec1 = np.random.randn(1536).tolist()
        vec2 = np.random.randn(1536).tolist()
        
        similarity = self.cosine_similarity(vec1, vec2)
        assert -1.0 <= similarity <= 1.0


class TestAutonomyDetection:
    """Test autonomy level detection"""
    
    @staticmethod
    def determine_autonomy(query: str) -> int:
        """Local implementation for testing"""
        query_lower = query.lower()
        
        # Level 3 keywords (dangerous operations)
        if any(word in query_lower for word in ["delete", "cancel", "submit", "create invoice", "payment"]):
            return 3
        
        # Level 2 keywords (modifications)
        if any(word in query_lower for word in ["update", "change", "modify", "set", "add"]):
            return 2
        
        # Default to Level 1 (read-only)
        return 1
    
    def test_read_only_queries(self):
        """Read-only queries should be Level 1"""
        queries = [
            "Show me invoices",
            "What are my sales?",
            "List all customers",
            "Get the order details",
            "Find pending bills"
        ]
        for query in queries:
            assert self.determine_autonomy(query) == 1, f"Failed for: {query}"
    
    def test_modification_queries(self):
        """Modification queries should be Level 2"""
        queries = [
            "Update the customer name",
            "Change the price to 100",
            "Modify the order status",
            "Set the due date",
            "Add a new item"
        ]
        for query in queries:
            assert self.determine_autonomy(query) == 2, f"Failed for: {query}"
    
    def test_dangerous_queries(self):
        """Dangerous operations should be Level 3"""
        queries = [
            "Delete all invoices",
            "Cancel the order",
            "Submit the document",
            "Create invoice for customer",
            "Process payment"
        ]
        for query in queries:
            assert self.determine_autonomy(query) == 3, f"Failed for: {query}"


class TestConfidenceScoring:
    """Test confidence scoring logic"""
    
    @staticmethod
    def calculate_confidence(sources_count: int, avg_similarity: float) -> str:
        """Calculate confidence level based on sources and similarity"""
        if sources_count >= 2 and avg_similarity >= 0.85:
            return "HIGH"
        elif sources_count >= 1 and avg_similarity >= 0.7:
            return "MEDIUM"
        elif sources_count >= 1 and avg_similarity >= 0.5:
            return "LOW"
        else:
            return "UNCERTAIN"
    
    def test_high_confidence(self):
        """Multiple sources with high similarity = HIGH"""
        assert self.calculate_confidence(3, 0.9) == "HIGH"
        assert self.calculate_confidence(2, 0.85) == "HIGH"
    
    def test_medium_confidence(self):
        """Single source with good similarity = MEDIUM"""
        assert self.calculate_confidence(1, 0.75) == "MEDIUM"
        assert self.calculate_confidence(1, 0.7) == "MEDIUM"
    
    def test_low_confidence(self):
        """Low similarity = LOW"""
        assert self.calculate_confidence(1, 0.6) == "LOW"
        assert self.calculate_confidence(2, 0.55) == "LOW"
    
    def test_uncertain(self):
        """No sources or very low similarity = UNCERTAIN"""
        assert self.calculate_confidence(0, 0.9) == "UNCERTAIN"
        assert self.calculate_confidence(1, 0.3) == "UNCERTAIN"


class TestMemoryImportance:
    """Test memory importance classification"""
    
    @staticmethod
    def classify_importance(content: str, source: str = None) -> str:
        """Classify memory importance"""
        content_lower = content.lower()
        
        # Critical patterns
        if any(word in content_lower for word in ["api key", "password", "secret", "credential"]):
            return "Critical"
        
        # High patterns
        if any(word in content_lower for word in ["preference", "always", "never", "important"]):
            return "High"
        
        # Low patterns
        if any(word in content_lower for word in ["maybe", "sometimes", "might"]):
            return "Low"
        
        return "Normal"
    
    def test_critical_classification(self):
        """Security-related content should be Critical"""
        assert self.classify_importance("User's API key is xyz") == "Critical"
        assert self.classify_importance("Password changed") == "Critical"
    
    def test_high_classification(self):
        """Preference content should be High"""
        assert self.classify_importance("User preference: dark mode") == "High"
        assert self.classify_importance("Important: always use metric") == "High"
    
    def test_normal_classification(self):
        """Regular content should be Normal"""
        assert self.classify_importance("User asked about invoices") == "Normal"
    
    def test_low_classification(self):
        """Uncertain content should be Low"""
        assert self.classify_importance("User might prefer email") == "Low"


class TestEmbeddingStorage:
    """Test embedding storage and retrieval"""
    
    def test_embedding_json_serialization(self):
        """Test that embeddings can be serialized to JSON"""
        embedding = [0.1] * 1536
        serialized = json.dumps(embedding)
        deserialized = json.loads(serialized)
        
        assert len(deserialized) == 1536
        assert deserialized == embedding
    
    def test_large_embedding_storage(self):
        """Test storage of realistic embedding sizes"""
        np.random.seed(42)
        embedding = np.random.randn(1536).tolist()
        
        # Serialize and deserialize
        serialized = json.dumps(embedding)
        deserialized = json.loads(serialized)
        
        # Check precision is maintained
        for orig, restored in zip(embedding, deserialized):
            assert abs(orig - restored) < 1e-10


class TestQueryParsing:
    """Test query intent parsing"""
    
    @staticmethod
    def detect_erpnext_intent(query: str) -> list:
        """Detect ERPNext doctypes from query"""
        query_lower = query.lower()
        intents = []
        
        if any(word in query_lower for word in ["invoice", "sales", "revenue"]):
            intents.append("Sales Invoice")
        if any(word in query_lower for word in ["customer", "client"]):
            intents.append("Customer")
        if any(word in query_lower for word in ["item", "product", "stock"]):
            intents.append("Item")
        if any(word in query_lower for word in ["order", "purchase"]):
            intents.append("Purchase Order")
        if any(word in query_lower for word in ["employee", "staff"]):
            intents.append("Employee")
        
        return intents
    
    def test_invoice_intent(self):
        """Test invoice-related queries"""
        intents = self.detect_erpnext_intent("Show me recent invoices")
        assert "Sales Invoice" in intents
    
    def test_customer_intent(self):
        """Test customer-related queries"""
        intents = self.detect_erpnext_intent("List all customers")
        assert "Customer" in intents
    
    def test_multiple_intents(self):
        """Test queries with multiple intents"""
        intents = self.detect_erpnext_intent("Show invoices for customer ABC")
        assert "Sales Invoice" in intents
        assert "Customer" in intents
    
    def test_no_intent(self):
        """Test queries with no specific intent"""
        intents = self.detect_erpnext_intent("Hello, how are you?")
        assert len(intents) == 0


class TestRateLimiting:
    """Test rate limiting logic"""
    
    @staticmethod
    def should_rate_limit(requests_count: int, window_seconds: int, limit: int) -> bool:
        """Check if request should be rate limited"""
        return requests_count >= limit
    
    def test_under_limit(self):
        """Should not rate limit when under limit"""
        assert not self.should_rate_limit(5, 60, 10)
    
    def test_at_limit(self):
        """Should rate limit when at limit"""
        assert self.should_rate_limit(10, 60, 10)
    
    def test_over_limit(self):
        """Should rate limit when over limit"""
        assert self.should_rate_limit(15, 60, 10)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
