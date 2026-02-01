"""
Migration Fixer Skill - Class-based implementation
Uses the SkillBase framework for auto-discovery
"""

from raven_ai_agent.skills.framework import SkillBase
from raven_ai_agent.skills.migration_fixer.fixer import MigrationFixer
from typing import Dict, Optional


class MigrationFixerSkill(SkillBase):
    """
    Skill for FoxPro -> ERPNext migration validation and repair.
    
    Commands:
        - scan migration 2024/2025
        - compare folio XXXXX
        - fix folio XXXXX [confirm]
        - migration report
    """
    
    name = "migration-fixer"
    description = "FoxPro to ERPNext migration validation and repair for quotations/sales orders"
    emoji = "🔧"
    version = "1.0.0"
    priority = 70  # High priority for migration commands
    
    triggers = [
        "scan migration",
        "fix folio",
        "compare folio",
        "migration report",
        "validate folio",
        "check quotation",
        "foxpro"
    ]
    
    patterns = [
        r"scan\s+migration\s+\d{4}",
        r"fix\s+folio\s+\d{5}",
        r"compare\s+folio\s+\d{5}",
        r"migration.*report",
        r"folio\s+\d{5}"
    ]
    
    def __init__(self, agent=None):
        super().__init__(agent)
        self.fixer = MigrationFixer()
    
    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """Handle migration-related queries"""
        query_lower = query.lower().strip()
        
        # Scan commands
        if "scan migration" in query_lower:
            return self._handle_scan(query_lower)
        
        # Fix commands
        if "fix folio" in query_lower:
            return self._handle_fix(query_lower)
        
        # Compare commands
        if "compare folio" in query_lower:
            return self._handle_compare(query_lower)
        
        # Report command
        if "migration report" in query_lower:
            return self._handle_report(query_lower)
        
        return None
    
    def _handle_scan(self, query: str) -> Dict:
        """Handle scan migration commands"""
        parts = query.split()
        
        # Check for year
        for p in parts:
            if p in ["2024", "2025"]:
                year = int(p)
                range_info = MigrationFixer.FOLIO_RANGES.get(year, {})
                results = self.fixer.scan_range(
                    range_info.get("start"), 
                    range_info.get("end")
                )
                
                return {
                    "handled": True,
                    "response": self._format_scan_results(results, year),
                    "confidence": 0.95,
                    "data": results
                }
        
        # Check for range
        if "from" in query and "to" in query:
            try:
                from_idx = parts.index("from")
                to_idx = parts.index("to")
                start = parts[from_idx + 1]
                end = parts[to_idx + 1]
                
                results = self.fixer.scan_range(start, end)
                return {
                    "handled": True,
                    "response": self._format_scan_results(results),
                    "confidence": 0.95,
                    "data": results
                }
            except (ValueError, IndexError):
                pass
        
        return {
            "handled": True,
            "response": "📋 **Usage:** `scan migration 2024` or `scan migration from 00800 to 00850`",
            "confidence": 0.7
        }
    
    def _handle_fix(self, query: str) -> Dict:
        """Handle fix folio commands"""
        parts = query.split()
        
        try:
            folio_idx = parts.index("folio") + 1
            folio = parts[folio_idx]
            confirm = "confirm" in parts
            
            result = self.fixer.fix_quotation(folio, dry_run=not confirm)
            
            if result.get("error"):
                return {
                    "handled": True,
                    "response": f"❌ **Error:** {result['error']}",
                    "confidence": 0.9
                }
            
            if not result.get("changes"):
                return {
                    "handled": True,
                    "response": f"✅ **Folio {folio}:** No fixes needed - data is correct",
                    "confidence": 0.95
                }
            
            changes_text = "\n".join([
                f"  - `{c['field']}`: '{c['old']}' → '{c['new']}'"
                for c in result['changes']
            ])
            
            if result.get("applied"):
                return {
                    "handled": True,
                    "response": f"✅ **Fixed folio {folio}:**\n{changes_text}",
                    "confidence": 0.95,
                    "data": result
                }
            else:
                return {
                    "handled": True,
                    "response": f"🔍 **Preview for folio {folio}:**\n{changes_text}\n\n*Say `fix folio {folio} confirm` to apply*",
                    "confidence": 0.95,
                    "data": result
                }
                
        except (ValueError, IndexError):
            return {
                "handled": True,
                "response": "📋 **Usage:** `fix folio 00752` or `fix folio 00752 confirm`",
                "confidence": 0.7
            }
    
    def _handle_compare(self, query: str) -> Dict:
        """Handle compare folio commands"""
        parts = query.split()
        
        try:
            folio_idx = parts.index("folio") + 1
            folio = parts[folio_idx]
            
            from raven_ai_agent.skills.migration_fixer.api import compare_folio
            result = compare_folio(folio)
            
            if isinstance(result, dict) and result.get("error"):
                return {
                    "handled": True,
                    "response": f"❌ {result['error']}",
                    "confidence": 0.9
                }
            
            return {
                "handled": True,
                "response": self._format_comparison(result),
                "confidence": 0.95,
                "data": result
            }
            
        except (ValueError, IndexError):
            return {
                "handled": True,
                "response": "📋 **Usage:** `compare folio 00752`",
                "confidence": 0.7
            }
    
    def _handle_report(self, query: str) -> Dict:
        """Handle migration report commands"""
        year = None
        if "2024" in query:
            year = 2024
        elif "2025" in query:
            year = 2025
        
        report = self.fixer.generate_report(year=year)
        
        return {
            "handled": True,
            "response": report,
            "confidence": 0.95
        }
    
    def _format_scan_results(self, results: Dict, year: int = None) -> str:
        """Format scan results as a nice message"""
        year_str = f" ({year})" if year else ""
        
        output = f"""📊 **Migration Scan Results{year_str}**

| Status | Count |
|--------|-------|
| 📋 Scanned | {results['scanned']} |
| ✅ OK | {results['ok']} |
| ⚠️ Warnings | {results['warnings']} |
| ❌ Errors | {results['errors']} |
| 📭 Missing | {results.get('missing', 0)} |
"""
        
        if results.get('details'):
            output += "\n**Top Issues:**\n"
            for d in results['details'][:5]:
                issues_str = d['issues'][0] if d['issues'] else 'Unknown issue'
                output += f"- `{d['folio']}`: {issues_str}\n"
            
            remaining = len(results['details']) - 5
            if remaining > 0:
                output += f"\n*...and {remaining} more issues*"
        
        return output
    
    def _format_comparison(self, result: Dict) -> str:
        """Format comparison result"""
        folio = result.get('folio', 'Unknown')
        output = f"📋 **Comparison for Folio {folio}**\n\n"
        
        if result.get("foxpro"):
            fp = result["foxpro"]
            output += "**FoxPro Source:**\n"
            output += f"- Customer: {fp.get('customer', 'N/A')}\n"
            output += f"- Date: {fp.get('date', 'N/A')}\n"
            if fp.get('total'):
                output += f"- Total: ${float(fp['total']):,.2f}\n"
            output += f"- Lote Real: {fp.get('lote_real', 'N/A')}\n"
            output += f"- Items: {fp.get('items_count', 0)}\n\n"
        else:
            output += "**FoxPro:** ❌ Not found\n\n"
        
        if result.get("erpnext"):
            erp = result["erpnext"]
            output += f"**ERPNext ({erp.get('name', 'Unknown')}):**\n"
            output += f"- Customer: {erp.get('customer', 'N/A')}\n"
            output += f"- Date: {erp.get('date', 'N/A')}\n"
            output += f"- Total: ${erp.get('total', 0):,.2f}\n"
            output += f"- Lote Real: {erp.get('lote_real', 'N/A')}\n"
            output += f"- Items: {erp.get('items_count', 0)}\n\n"
        else:
            output += "**ERPNext:** ❌ Not found\n\n"
        
        if result.get("differences"):
            output += "**⚠️ Differences Found:**\n"
            for d in result["differences"]:
                output += f"- `{d['field']}`: FoxPro='{d['foxpro']}' vs ERPNext='{d['erpnext']}'\n"
        else:
            output += "✅ **No differences found**\n"
        
        return output


# Export the skill class for auto-discovery
SKILL_CLASS = MigrationFixerSkill
