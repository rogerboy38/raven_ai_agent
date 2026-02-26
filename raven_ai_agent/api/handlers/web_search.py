"""
Direct Web Search Commands
"""
import frappe
import json
import re
import requests
from typing import Optional, Dict, List
from bs4 import BeautifulSoup

class WebSearchMixin:
    """Mixin for _handle_web_search_commands"""

    def _handle_web_search_commands(self, query: str, query_lower: str) -> Optional[Dict]:
        """Dispatched from execute_workflow_command"""
        # ==================== DIRECT WEB SEARCH ====================
        
        # Direct web search that shows raw results
        if query_lower.startswith("search ") or query_lower.startswith("buscar "):
            try:
                # Extract search query
                search_query = query[7:].strip() if query_lower.startswith("search ") else query[7:].strip()
                # Remove brackets if present
                search_query = search_query.strip("[]")
                
                # Check if user wants to save results
                save_to_memory = "[save]" in query_lower or "[guardar]" in query_lower
                if save_to_memory:
                    search_query = search_query.replace("[save]", "").replace("[guardar]", "").strip()
                
                if len(search_query) > 2:
                    results = self.duckduckgo_search(search_query, max_results=8)
                    
                    if "No search results" in results or "Search error" in results:
                        return {
                            "success": False,
                            "message": f"🔍 **Web Search**: {search_query}\n\n{results}"
                        }
                    
                    # Save to memory if requested
                    save_msg = ""
                    if save_to_memory:
                        try:
                            import datetime
                            self.store_memory(
                                content=f"Search: {search_query}\n\n{results[:1500]}",
                                category="research",
                                importance="medium"
                            )
                            save_msg = "\n\n✅ *Saved to memory*"
                        except Exception as me:
                            save_msg = f"\n\n⚠️ Could not save: {str(me)}"
                    
                    footer = "\n\n---\n💡 Add `[save]` to save results to memory"
                    return {
                        "success": True,
                        "message": f"🔍 **Web Search**: {search_query}\n\n{results}{save_msg}{footer}"
                    }
                else:
                    return {
                        "success": True,
                        "message": "🔍 **Web Search**\n\nUsage: `@ai search [your query]`\n\nExample: `@ai search aloe acemannan suppliers China`\n\nAdd `[save]` to save results to memory"
                    }
                    
            except Exception as e:
                return {"success": False, "error": f"Search Error: {str(e)}"}
        
        # ==================== END DIRECT WEB SEARCH ====================

        return None
