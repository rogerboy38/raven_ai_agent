"""
Vector Search Utilities for AI Memory
Uses OpenAI embeddings with cosine similarity
"""
import frappe
import json
import numpy as np
from typing import List, Dict, Optional
from openai import OpenAI


class VectorStore:
    """Vector store for semantic memory search"""
    
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS = 1536
    
    def __init__(self):
        settings = frappe.get_single("AI Agent Settings")
        self.client = OpenAI(api_key=settings.openai_api_key)
    
    def get_embedding(self, text: str) -> List[float]:
        """Generate embedding for text"""
        response = self.client.embeddings.create(
            model=self.EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        response = self.client.embeddings.create(
            model=self.EMBEDDING_MODEL,
            input=texts
        )
        return [item.embedding for item in response.data]
    
    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        a = np.array(a)
        b = np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    
    def store_memory_with_embedding(
        self,
        user: str,
        content: str,
        importance: str = "Normal",
        memory_type: str = "Fact",
        source: str = None
    ) -> str:
        """Store memory with its embedding"""
        embedding = self.get_embedding(content)
        
        doc = frappe.get_doc({
            "doctype": "AI Memory",
            "user": user,
            "content": content,
            "importance": importance,
            "memory_type": memory_type,
            "source": source or "Conversation",
            "embedding": json.dumps(embedding)
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    
    def search_similar(
        self,
        user: str,
        query: str,
        limit: int = 5,
        similarity_threshold: float = 0.7,
        importance_filter: List[str] = None
    ) -> List[Dict]:
        """Search for similar memories using vector similarity"""
        
        # Get query embedding
        query_embedding = self.get_embedding(query)
        
        # Build filters
        filters = {"user": user}
        if importance_filter:
            filters["importance"] = ["in", importance_filter]
        
        # Get all memories with embeddings for this user
        memories = frappe.get_list(
            "AI Memory",
            filters=filters,
            fields=["name", "content", "importance", "memory_type", "source", "embedding", "creation"]
        )
        
        # Calculate similarities
        results = []
        for memory in memories:
            if not memory.embedding:
                continue
            
            try:
                stored_embedding = json.loads(memory.embedding)
                similarity = self.cosine_similarity(query_embedding, stored_embedding)
                
                if similarity >= similarity_threshold:
                    results.append({
                        "name": memory.name,
                        "content": memory.content,
                        "importance": memory.importance,
                        "memory_type": memory.memory_type,
                        "source": memory.source,
                        "similarity": round(similarity, 4),
                        "creation": memory.creation
                    })
            except (json.JSONDecodeError, TypeError):
                continue
        
        # Sort by similarity and return top results
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]
    
    def update_missing_embeddings(self, user: str = None, batch_size: int = 50):
        """Backfill embeddings for memories that don't have them"""
        filters = {"embedding": ["is", "not set"]}
        if user:
            filters["user"] = user
        
        memories = frappe.get_list(
            "AI Memory",
            filters=filters,
            fields=["name", "content"],
            limit=batch_size
        )
        
        if not memories:
            return 0
        
        # Get embeddings in batch
        contents = [m.content for m in memories]
        embeddings = self.get_embeddings_batch(contents)
        
        # Update each memory
        for memory, embedding in zip(memories, embeddings):
            frappe.db.set_value(
                "AI Memory",
                memory.name,
                "embedding",
                json.dumps(embedding)
            )
        
        frappe.db.commit()
        return len(memories)
    
    def find_duplicates(self, user: str, threshold: float = 0.95) -> List[Dict]:
        """Find potential duplicate memories"""
        memories = frappe.get_list(
            "AI Memory",
            filters={"user": user, "embedding": ["is", "set"]},
            fields=["name", "content", "embedding"]
        )
        
        duplicates = []
        checked = set()
        
        for i, mem1 in enumerate(memories):
            if mem1.name in checked:
                continue
            
            emb1 = json.loads(mem1.embedding)
            
            for mem2 in memories[i+1:]:
                if mem2.name in checked:
                    continue
                
                emb2 = json.loads(mem2.embedding)
                similarity = self.cosine_similarity(emb1, emb2)
                
                if similarity >= threshold:
                    duplicates.append({
                        "memory_1": mem1.name,
                        "memory_2": mem2.name,
                        "content_1": mem1.content,
                        "content_2": mem2.content,
                        "similarity": round(similarity, 4)
                    })
                    checked.add(mem2.name)
        
        return duplicates


# Frappe API wrappers

@frappe.whitelist()
def vector_search(user: str, query: str, limit: int = 5) -> List[Dict]:
    """API endpoint for vector search"""
    store = VectorStore()
    return store.search_similar(user, query, limit=int(limit))


@frappe.whitelist()
def store_with_embedding(
    user: str,
    content: str,
    importance: str = "Normal",
    memory_type: str = "Fact",
    source: str = None
) -> str:
    """API endpoint to store memory with embedding"""
    store = VectorStore()
    return store.store_memory_with_embedding(user, content, importance, memory_type, source)


@frappe.whitelist()
def backfill_embeddings(user: str = None) -> Dict:
    """API endpoint to backfill missing embeddings"""
    store = VectorStore()
    count = store.update_missing_embeddings(user)
    return {"updated": count}


@frappe.whitelist()
def find_duplicate_memories(user: str) -> List[Dict]:
    """API endpoint to find duplicate memories"""
    store = VectorStore()
    return store.find_duplicates(user)
