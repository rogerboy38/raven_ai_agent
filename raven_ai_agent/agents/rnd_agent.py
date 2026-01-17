"""
R&D (Research & Development) AI Agent
Assists with formulation, TDS management, and product development in ERPNext
"""
import frappe
from typing import Dict, List, Optional
from frappe.utils import nowdate, getdate
import re


class RnDAgent:
    """AI Agent for Research & Development and Formulation operations"""
    
    # Acemannan product properties reference
    ACEMANNAN_PROPERTIES = {
        "immunomodulator": "Stimulates immune response, acts as vaccine adjuvant",
        "antiviral": "Supports control of viral and fungal infections",
        "wound_healing": "Accelerates cell proliferation and collagen formation",
        "tissue_regeneration": "Bone and periodontal ligament regeneration",
        "biocompatibility": "Biodegradable biomaterial with low toxicity"
    }
    
    def __init__(self, user: str = None):
        self.user = user or frappe.session.user
        self.site_name = frappe.local.site
    
    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable markdown link"""
        slug = doctype.lower().replace(" ", "-")
        return f"[{name}](https://{self.site_name}/app/{slug}/{name})"
    
    # ========== TDS OPERATIONS ==========
    
    def get_tds_list(self, limit: int = 20) -> Dict:
        """List TDS Product Specifications"""
        try:
            tds_list = frappe.get_all("TDS Product Specification",
                fields=["name", "item_code", "item_name", "product_item", "workflow_state", "tds_version"],
                order_by="creation desc",
                limit=limit)
            
            result = []
            for tds in tds_list:
                result.append({
                    "name": tds.name,
                    "link": self.make_link("TDS Product Specification", tds.name),
                    "item_code": tds.get("item_code") or "N/A",
                    "item_name": tds.get("item_name") or tds.name,
                    "status": tds.get("workflow_state") or "N/A",
                    "version": tds.get("tds_version") or ""
                })
            
            return {"success": True, "count": len(result), "tds_list": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_tds_details(self, tds_name: str) -> Dict:
        """Get detailed TDS Product Specification"""
        try:
            tds = frappe.get_doc("TDS Product Specification", tds_name)
            
            # Get quality inspection parameters
            parameters = []
            if hasattr(tds, 'item_quality_inspection_parameter') and tds.item_quality_inspection_parameter:
                for param in tds.item_quality_inspection_parameter:
                    parameters.append({
                        "specification": getattr(param, 'specification', ''),
                        "parameter_group": getattr(param, 'parameter_group', ''),
                        "value": getattr(param, 'value', ''),
                        "uom": getattr(param, 'custom_uom', ''),
                        "min_value": getattr(param, 'min_value', None),
                        "max_value": getattr(param, 'max_value', None),
                        "method": getattr(param, 'custom_method', '')
                    })
            
            return {
                "success": True,
                "name": tds.name,
                "link": self.make_link("TDS Product Specification", tds.name),
                "item_code": tds.item_code or "N/A",
                "item_name": tds.item_name or tds.name,
                "product_item": tds.product_item or "",
                "status": tds.workflow_state or "N/A",
                "version": tds.tds_version or "",
                "approval_date": str(tds.approval_date) if tds.approval_date else "",
                "cas_number": tds.cas_number or "",
                "inci_name": tds.inci_name or "",
                "shelf_life": tds.shelf_life or "",
                "packaging": tds.packaging or "",
                "storage": tds.storage_and_handling_conditions or "",
                "parameters": parameters
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"TDS '{tds_name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def search_tds(self, query: str) -> Dict:
        """Search TDS by item code or item name"""
        try:
            fields = ["name", "item_code", "item_name", "workflow_state"]
            
            # Search by name
            tds_list = frappe.get_all("TDS Product Specification",
                filters={"name": ["like", f"%{query}%"]},
                fields=fields,
                limit=10)
            
            # Also search by item_code and item_name
            for field in ["item_code", "item_name"]:
                if len(tds_list) < 10:
                    more = frappe.get_all("TDS Product Specification",
                        filters={field: ["like", f"%{query}%"]},
                        fields=fields,
                        limit=10)
                    existing_names = [t.name for t in tds_list]
                    for t in more:
                        if t.name not in existing_names:
                            tds_list.append(t)
            
            result = []
            for tds in tds_list[:10]:
                result.append({
                    "name": tds.name,
                    "link": self.make_link("TDS Product Specification", tds.name),
                    "item_code": tds.get("item_code") or "N/A",
                    "item_name": tds.get("item_name") or tds.name
                })
            
            return {"success": True, "count": len(result), "results": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== FORMULATION OPERATIONS ==========
    
    def get_formulation(self, item_code: str) -> Dict:
        """Get formulation/recipe for an item from BOM or TDS"""
        try:
            # Clean item_code (remove brackets if present)
            item_code = item_code.strip().strip('[]')
            
            # Try exact match first
            bom = frappe.get_value("BOM", 
                {"item": item_code, "is_active": 1, "is_default": 1},
                ["name", "item", "quantity", "total_cost"],
                as_dict=True)
            
            # Try searching by like pattern if no exact match
            if not bom:
                bom_search = frappe.get_all("BOM",
                    filters={"item": ["like", f"%{item_code}%"], "is_active": 1},
                    fields=["name", "item", "quantity", "total_cost"],
                    limit=1)
                if bom_search:
                    bom = bom_search[0]
            
            if bom:
                bom_doc = frappe.get_doc("BOM", bom.name)
                ingredients = []
                for item in bom_doc.items:
                    ingredients.append({
                        "item_code": item.item_code,
                        "item_name": item.item_name,
                        "qty": item.qty,
                        "uom": item.uom,
                        "rate": item.rate
                    })
                
                return {
                    "success": True,
                    "source": "BOM",
                    "bom_name": bom.name,
                    "link": self.make_link("BOM", bom.name),
                    "item_code": bom.get("item", item_code),
                    "quantity": bom.quantity,
                    "ingredients": ingredients
                }
            
            # Try TDS if no BOM - check multiple field possibilities
            tds = None
            meta = frappe.get_meta("TDS Product Specification")
            available_fields = [f.fieldname for f in meta.fields]
            
            if "item_code" in available_fields:
                tds = frappe.get_value("TDS Product Specification", {"item_code": item_code}, "name")
            if not tds and "item" in available_fields:
                tds = frappe.get_value("TDS Product Specification", {"item": item_code}, "name")
            if not tds:
                # Search by name pattern
                tds_search = frappe.get_all("TDS Product Specification",
                    filters={"name": ["like", f"%{item_code}%"]},
                    limit=1)
                if tds_search:
                    tds = tds_search[0].name
            
            if tds:
                return self.get_tds_details(tds)
            
            return {"success": False, "error": f"No formulation found for item '{item_code}'"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def calculate_batch(self, item_code: str, batch_size: float) -> Dict:
        """Calculate ingredient quantities for a batch size"""
        try:
            formulation = self.get_formulation(item_code)
            if not formulation.get("success"):
                return formulation
            
            base_qty = formulation.get("quantity", 1)
            scale_factor = batch_size / base_qty
            
            scaled_ingredients = []
            for ing in formulation.get("ingredients", []):
                scaled_ingredients.append({
                    "item_code": ing["item_code"],
                    "item_name": ing.get("item_name", ""),
                    "base_qty": ing["qty"],
                    "scaled_qty": round(ing["qty"] * scale_factor, 4),
                    "uom": ing.get("uom", "")
                })
            
            return {
                "success": True,
                "item_code": item_code,
                "batch_size": batch_size,
                "scale_factor": scale_factor,
                "ingredients": scaled_ingredients
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== R&D PROJECT TRACKING ==========
    
    def get_rnd_projects(self, limit: int = 20) -> Dict:
        """List R&D related projects"""
        try:
            projects = frappe.get_all("Project",
                filters=[
                    ["project_name", "like", "%R&D%"],
                ],
                or_filters=[
                    ["project_name", "like", "%Research%"],
                    ["project_name", "like", "%Development%"],
                    ["project_name", "like", "%Formulation%"]
                ],
                fields=["name", "project_name", "status", "percent_complete"],
                order_by="creation desc",
                limit=limit)
            
            # Fallback - get recent projects
            if not projects:
                projects = frappe.get_all("Project",
                    fields=["name", "project_name", "status", "percent_complete"],
                    order_by="creation desc",
                    limit=limit)
            
            result = []
            for proj in projects:
                result.append({
                    "name": proj.name,
                    "link": self.make_link("Project", proj.name),
                    "project_name": proj.project_name,
                    "status": proj.status,
                    "progress": f"{proj.percent_complete or 0}%"
                })
            
            return {"success": True, "count": len(result), "projects": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== INGREDIENT/RAW MATERIAL LOOKUP ==========
    
    def search_ingredients(self, query: str) -> Dict:
        """Search raw materials/ingredients"""
        try:
            items = frappe.get_all("Item",
                filters={
                    "item_group": ["in", ["Raw Materials", "RAW M Liquids", "RAW M Solids", "Ingredients"]],
                    "item_code": ["like", f"%{query}%"]
                },
                or_filters=[
                    {"item_name": ["like", f"%{query}%"]},
                    {"description": ["like", f"%{query}%"]}
                ],
                fields=["item_code", "item_name", "item_group", "stock_uom"],
                limit=15)
            
            result = []
            for item in items:
                # Get current stock
                stock = frappe.db.sql("""
                    SELECT SUM(actual_qty) as qty 
                    FROM `tabBin` 
                    WHERE item_code = %s
                """, item.item_code, as_dict=True)
                
                result.append({
                    "item_code": item.item_code,
                    "link": self.make_link("Item", item.item_code),
                    "item_name": item.item_name,
                    "item_group": item.item_group,
                    "uom": item.stock_uom,
                    "stock_qty": stock[0].qty if stock and stock[0].qty else 0
                })
            
            return {"success": True, "count": len(result), "ingredients": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== ACEMANNAN REFERENCE ==========
    
    def get_acemannan_info(self, property_name: str = None) -> Dict:
        """Get acemannan product information and properties"""
        if property_name:
            prop = self.ACEMANNAN_PROPERTIES.get(property_name.lower())
            if prop:
                return {"success": True, "property": property_name, "description": prop}
            return {"success": False, "error": f"Property '{property_name}' not found"}
        
        return {
            "success": True,
            "product": "Acemannan",
            "description": "High-value polysaccharide from Aloe vera with multiple therapeutic applications",
            "properties": self.ACEMANNAN_PROPERTIES,
            "applications": [
                "Tissue engineering",
                "Advanced dermatology",
                "Veterinary medicine",
                "Immune support supplements",
                "Wound healing products"
            ],
            "innovation_focus": [
                "Higher concentration and standardization",
                "Regulatory and scientific differentiation",
                "Advanced biomaterial applications"
            ]
        }
    
    # ========== MAIN HANDLER ==========
    
    def process_command(self, message: str) -> str:
        """Process incoming command and return response"""
        message_lower = message.lower().strip()
        
        # Extract identifiers
        tds_pattern = r'(TDS-[A-Z0-9-]+)'
        tds_match = re.search(tds_pattern, message, re.IGNORECASE)
        tds_name = tds_match.group(1) if tds_match else None
        
        item_pattern = r'(\d{4}|\w+-\d+)'
        item_match = re.search(item_pattern, message)
        item_code = item_match.group(1) if item_match else None
        
        # TDS Commands
        if "show tds" in message_lower or "list tds" in message_lower:
            result = self.get_tds_list()
            if result["success"]:
                lines = [f"## TDS Product Specifications ({result['count']} found)\n"]
                for tds in result["tds_list"]:
                    lines.append(f"• {tds['link']} | {tds['item_code']} | {tds['item_name']} | {tds['status']}")
                return "\n".join(lines)
            return f"❌ Error: {result['error']}"
        
        if "search tds" in message_lower:
            query = message_lower.replace("search tds", "").strip()
            if not query:
                return "Please provide a search term: `search tds [query]`"
            result = self.search_tds(query)
            if result["success"]:
                if result["count"] == 0:
                    return f"No TDS found matching '{query}'"
                lines = [f"## TDS Search Results ({result['count']} found)\n"]
                for tds in result["results"]:
                    lines.append(f"• {tds['link']} | {tds['item_code']} | {tds['item_name']}")
                return "\n".join(lines)
            return f"❌ Error: {result['error']}"
        
        if tds_name or ("tds" in message_lower and "detail" in message_lower):
            name = tds_name or message_lower.replace("tds", "").replace("detail", "").strip()
            result = self.get_tds_details(name)
            if result["success"]:
                lines = [f"## TDS: {result['link']}\n"]
                lines.append(f"**Item Code:** {result['item_code']}")
                lines.append(f"**Item Name:** {result['item_name']}")
                lines.append(f"**Status:** {result['status']}")
                lines.append(f"**Version:** {result['version']}")
                if result.get("cas_number"):
                    lines.append(f"**CAS Number:** {result['cas_number']}")
                if result.get("inci_name"):
                    lines.append(f"**INCI Name:** {result['inci_name']}")
                if result.get("shelf_life"):
                    lines.append(f"\n**Shelf Life:** {result['shelf_life'][:200]}")
                if result.get("parameters"):
                    lines.append("\n**Quality Parameters:**")
                    for param in result["parameters"][:10]:
                        spec = param['specification'] or param['parameter_group'] or 'Parameter'
                        val = param['value'] or ''
                        if param['min_value'] is not None or param['max_value'] is not None:
                            val = f"{param['min_value'] or ''} - {param['max_value'] or ''}"
                        lines.append(f"  • {spec}: {val} {param['uom'] or ''}")
                return "\n".join(lines)
            return f"❌ Error: {result['error']}"
        
        # Formulation Commands
        if "formulation" in message_lower or "recipe" in message_lower:
            if item_code:
                result = self.get_formulation(item_code)
                if result["success"]:
                    lines = [f"## Formulation: {item_code}\n"]
                    lines.append(f"**Source:** {result.get('source', 'TDS')}")
                    if result.get("link"):
                        lines.append(f"**Document:** {result['link']}")
                    lines.append("\n**Ingredients:**")
                    for ing in result.get("ingredients", []):
                        lines.append(f"  • {ing['item_code']}: {ing['qty']} {ing.get('uom', '')}")
                    return "\n".join(lines)
                return f"❌ Error: {result['error']}"
            return "Please specify an item code: `formulation [ITEM-CODE]`"
        
        if "calculate batch" in message_lower or "batch size" in message_lower:
            # Extract batch size
            size_match = re.search(r'(\d+\.?\d*)\s*(kg|g|l|ml)?', message_lower)
            if item_code and size_match:
                batch_size = float(size_match.group(1))
                result = self.calculate_batch(item_code, batch_size)
                if result["success"]:
                    lines = [f"## Batch Calculation: {item_code}\n"]
                    lines.append(f"**Batch Size:** {batch_size}")
                    lines.append(f"**Scale Factor:** {result['scale_factor']:.4f}")
                    lines.append("\n**Scaled Ingredients:**")
                    for ing in result["ingredients"]:
                        lines.append(f"  • {ing['item_code']}: {ing['scaled_qty']} {ing['uom']} (base: {ing['base_qty']})")
                    return "\n".join(lines)
                return f"❌ Error: {result['error']}"
            return "Usage: `calculate batch [ITEM] [SIZE]` - e.g., `calculate batch 0323 100 kg`"
        
        # Ingredient Search
        if "search ingredient" in message_lower or "find ingredient" in message_lower:
            query = re.sub(r'(search|find)\s+ingredient[s]?\s*', '', message_lower).strip()
            if not query:
                return "Please provide a search term: `search ingredient [query]`"
            result = self.search_ingredients(query)
            if result["success"]:
                if result["count"] == 0:
                    return f"No ingredients found matching '{query}'"
                lines = [f"## Ingredients ({result['count']} found)\n"]
                for ing in result["ingredients"]:
                    stock_info = f"Stock: {ing['stock_qty']} {ing['uom']}" if ing['stock_qty'] else "No stock"
                    lines.append(f"• {ing['link']} | {ing['item_name']} | {stock_info}")
                return "\n".join(lines)
            return f"❌ Error: {result['error']}"
        
        # R&D Projects
        if "project" in message_lower:
            result = self.get_rnd_projects()
            if result["success"]:
                lines = [f"## R&D Projects ({result['count']} found)\n"]
                for proj in result["projects"]:
                    lines.append(f"• {proj['link']} | {proj['status']} | {proj['progress']}")
                return "\n".join(lines)
            return f"❌ Error: {result['error']}"
        
        # Acemannan Info
        if "acemannan" in message_lower:
            prop = None
            for key in self.ACEMANNAN_PROPERTIES.keys():
                if key in message_lower:
                    prop = key
                    break
            
            result = self.get_acemannan_info(prop)
            if result["success"]:
                if prop:
                    return f"**Acemannan - {prop.title()}**\n{result['description']}"
                else:
                    lines = ["## Acemannan Product Information\n"]
                    lines.append(f"**Description:** {result['description']}\n")
                    lines.append("**Key Properties:**")
                    for key, val in result["properties"].items():
                        lines.append(f"  • **{key.replace('_', ' ').title()}:** {val}")
                    lines.append("\n**Applications:**")
                    for app in result["applications"]:
                        lines.append(f"  • {app}")
                    lines.append("\n**Innovation Focus:**")
                    for focus in result["innovation_focus"]:
                        lines.append(f"  • {focus}")
                    return "\n".join(lines)
            return f"❌ Error: {result['error']}"
        
        # Help
        return """## R&D Bot Commands

**TDS (Technical Data Sheets):**
• `show tds` - List all TDS specifications
• `search tds [query]` - Search TDS by item/name
• `tds detail [TDS-NAME]` - View TDS details

**Formulation:**
• `formulation [ITEM]` - Get formulation/recipe for item
• `calculate batch [ITEM] [SIZE]` - Scale ingredients for batch

**Ingredients:**
• `search ingredient [query]` - Find raw materials

**R&D Projects:**
• `projects` - List R&D projects

**Acemannan Reference:**
• `acemannan` - Product info and properties
• `acemannan [property]` - Specific property (immunomodulator, antiviral, wound_healing, etc.)
"""
