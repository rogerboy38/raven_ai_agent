"""
BOM Creator AI Agent
Automates Bill of Materials creation in ERPNext using natural language commands
"""
import frappe
import json
from typing import Dict, List, Optional
from frappe.utils import nowdate


class BOMCreatorAgent:
    """AI Agent for automating BOM Creator operations"""
    
    # Wrapper types for BOM hierarchy
    WRAPPER_TYPES = {
        "utility": {"suffix": "-Utility-", "item_group": "Services"},
        "supplies": {"suffix": "-Supplies-Material-", "item_group": "RAW M Liquids"},
        "raw_material": {"suffix": "-Raw-Material-", "item_group": "RAW M Liquids"},
        "packing": {"suffix": "-Packing-Material-", "item_group": "RAW M Liquids"}
    }
    
    def __init__(self, user: str = None):
        self.user = user or frappe.session.user
        self.site_name = frappe.local.site
    
    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable link"""
        slug = doctype.lower().replace(" ", "-")
        return f"https://{self.site_name}/app/{slug}/{name}"
    
    # ========== CORE BOM CREATOR OPERATIONS ==========
    
    def get_bom_creator(self, name: str) -> Dict:
        """Get BOM Creator details"""
        try:
            bc = frappe.get_doc("BOM Creator", name)
            return {
                "success": True,
                "name": bc.name,
                "item_code": bc.item_code,
                "status": bc.status,
                "items_count": len(bc.items),
                "raw_material_cost": bc.raw_material_cost,
                "link": self.make_link("BOM Creator", name)
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"BOM Creator '{name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def create_bom_from_template(self, product_code: str, template_bom_name: str) -> Dict:
        """Create new BOM Creator by copying from a template"""
        try:
            # Get template
            source = frappe.get_doc("BOM Creator", template_bom_name)
            
            # Copy document
            new_bc = frappe.copy_doc(source)
            new_bc.item_code = product_code
            new_bc.item_name = product_code
            new_bc.status = "Draft"
            
            # Update item references in child items
            for item in new_bc.items:
                if template_bom_name in str(item.item_code):
                    item.item_code = item.item_code.replace(template_bom_name.replace("BOM-", ""), product_code)
                if template_bom_name in str(item.fg_item):
                    item.fg_item = item.fg_item.replace(template_bom_name.replace("BOM-", ""), product_code)
            
            new_bc.flags.ignore_permissions = True
            new_bc.save()
            frappe.db.commit()
            
            return {
                "success": True,
                "bom_name": new_bc.name,
                "items_count": len(new_bc.items),
                "url": self.make_link("BOM Creator", new_bc.name),
                "message": f"✅ Created BOM Creator '{new_bc.name}' with {len(new_bc.items)} items"
            }
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "error": str(e)}
    
    def create_bom_from_tds(self, tds_name: str, template_bom_name: str = None) -> Dict:
        """Create BOM Creator from TDS Product Specification"""
        try:
            # Get TDS
            tds = frappe.get_doc("TDS Product Specification", tds_name)
            production_item = tds.item_code  # The production item code from TDS
            
            if not production_item:
                return {"success": False, "error": f"TDS '{tds_name}' has no item_code (production item)"}
            
            # Check if BOM Creator already exists
            existing = frappe.db.exists("BOM Creator", {"item_code": production_item})
            if existing:
                return {
                    "success": True,
                    "status": "exists",
                    "bom_name": existing,
                    "url": self.make_link("BOM Creator", existing),
                    "message": f"BOM Creator for '{production_item}' already exists"
                }
            
            # Find template if not provided
            if not template_bom_name:
                # Try to find similar product template
                generic_item = tds.product_item  # Generic/sales item
                similar_boms = frappe.get_all(
                    "BOM Creator",
                    filters={"status": ["!=", "Cancelled"]},
                    fields=["name", "item_code"],
                    limit=5
                )
                if similar_boms:
                    template_bom_name = similar_boms[0].name
                else:
                    return {"success": False, "error": "No template BOM Creator found. Please specify one."}
            
            # Create from template
            return self.create_bom_from_template(production_item, template_bom_name)
            
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"TDS '{tds_name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def add_wrapper(self, bom_creator_name: str, wrapper_type: str, parent_item: str, 
                    items: List[Dict] = None) -> Dict:
        """Add a wrapper (Utility, Supplies, Raw Material, Packing) to BOM Creator"""
        try:
            if wrapper_type not in self.WRAPPER_TYPES:
                return {"success": False, "error": f"Invalid wrapper type. Use: {list(self.WRAPPER_TYPES.keys())}"}
            
            bc = frappe.get_doc("BOM Creator", bom_creator_name)
            wrapper_config = self.WRAPPER_TYPES[wrapper_type]
            
            # Generate wrapper item code
            base_code = bc.item_code.split("-")[0]  # e.g., "0307" from "0307-500/100..."
            wrapper_code = f"{base_code}{wrapper_config['suffix']}{bc.item_code}"
            
            # Find parent row
            parent_row = None
            for idx, item in enumerate(bc.items):
                if item.item_code == parent_item:
                    parent_row = item
                    break
            
            if not parent_row:
                return {"success": False, "error": f"Parent item '{parent_item}' not found in BOM Creator"}
            
            # Add wrapper item
            wrapper_item = bc.append("items", {
                "item_code": wrapper_code,
                "item_name": wrapper_code,
                "item_group": wrapper_config["item_group"],
                "fg_item": parent_item,
                "is_expandable": 1,
                "qty": 1,
                "uom": "Kg",
                "parent_row_no": str(parent_row.idx),
                "fg_reference_id": parent_row.name
            })
            
            # Add child items if provided
            items_added = 0
            if items:
                for item_data in items:
                    bc.append("items", {
                        "item_code": item_data.get("item_code"),
                        "item_name": item_data.get("item_name", item_data.get("item_code")),
                        "item_group": item_data.get("item_group", "Raw Materials"),
                        "fg_item": wrapper_code,
                        "is_expandable": 0,
                        "qty": item_data.get("qty", 1),
                        "rate": item_data.get("rate", 0),
                        "uom": item_data.get("uom", "Kg"),
                        "parent_row_no": str(wrapper_item.idx),
                        "fg_reference_id": wrapper_item.name
                    })
                    items_added += 1
            
            bc.flags.ignore_permissions = True
            bc.save()
            frappe.db.commit()
            
            return {
                "success": True,
                "wrapper_code": wrapper_code,
                "items_added": items_added,
                "message": f"✅ Added {wrapper_type} wrapper '{wrapper_code}' with {items_added} items"
            }
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "error": str(e)}
    
    def add_items_to_bom(self, bom_creator_name: str, parent_item: str, 
                         items: List[Dict]) -> Dict:
        """Add items to a BOM Creator under a specific parent"""
        try:
            bc = frappe.get_doc("BOM Creator", bom_creator_name)
            
            # Find parent row
            parent_row = None
            for item in bc.items:
                if item.item_code == parent_item:
                    parent_row = item
                    break
            
            if not parent_row:
                return {"success": False, "error": f"Parent item '{parent_item}' not found"}
            
            items_added = 0
            for item_data in items:
                bc.append("items", {
                    "item_code": item_data.get("item_code"),
                    "item_name": item_data.get("item_name", item_data.get("item_code")),
                    "item_group": item_data.get("item_group", "Raw Materials"),
                    "fg_item": parent_item,
                    "is_expandable": item_data.get("is_expandable", 0),
                    "qty": item_data.get("qty", 1),
                    "rate": item_data.get("rate", 0),
                    "uom": item_data.get("uom", "Kg"),
                    "parent_row_no": str(parent_row.idx),
                    "fg_reference_id": parent_row.name,
                    "description": item_data.get("description", "")
                })
                items_added += 1
            
            bc.flags.ignore_permissions = True
            bc.save()
            frappe.db.commit()
            
            return {
                "success": True,
                "items_added": items_added,
                "total_items": len(bc.items),
                "message": f"✅ Added {items_added} items under '{parent_item}'"
            }
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "error": str(e)}
    
    def submit_bom_creator(self, bom_creator_name: str) -> Dict:
        """Submit BOM Creator to generate BOMs"""
        try:
            bc = frappe.get_doc("BOM Creator", bom_creator_name)
            
            if bc.docstatus == 1:
                return {"success": True, "message": f"BOM Creator '{bom_creator_name}' already submitted"}
            
            bc.flags.ignore_permissions = True
            bc.submit()
            frappe.db.commit()
            
            # Find created BOMs
            created_boms = frappe.get_all(
                "BOM",
                filters={"item": bc.item_code},
                fields=["name", "is_active", "is_default"]
            )
            
            # Add links to created BOMs
            bom_links = []
            for bom in created_boms:
                bom["link"] = self.make_link("BOM", bom["name"])
                bom_links.append(f"[{bom['name']}]({bom['link']})")
            
            bom_list_str = ", ".join(bom_links) if bom_links else "None"
            
            return {
                "success": True,
                "bom_creator": bom_creator_name,
                "bom_creator_link": self.make_link("BOM Creator", bom_creator_name),
                "created_boms": created_boms,
                "message": f"✅ BOM Creator submitted. Created {len(created_boms)} BOMs:\n\n{bom_list_str}"
            }
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "error": str(e)}
    
    # ========== VALIDATION ==========
    
    def validate_bom_creator(self, bom_creator_name: str) -> Dict:
        """Validate BOM Creator structure before submission"""
        try:
            bc = frappe.get_doc("BOM Creator", bom_creator_name)
            issues = []
            warnings = []
            
            # Check item exists
            if not frappe.db.exists("Item", bc.item_code):
                issues.append(f"Main item '{bc.item_code}' does not exist in Item master")
            
            # Check all child items exist
            for item in bc.items:
                if not frappe.db.exists("Item", item.item_code):
                    issues.append(f"Item '{item.item_code}' does not exist")
                
                # Check UOM exists
                if item.uom and not frappe.db.exists("UOM", item.uom):
                    issues.append(f"UOM '{item.uom}' does not exist for item '{item.item_code}'")
                
                # Check parent references
                if item.parent_row_no:
                    parent_found = any(str(i.idx) == item.parent_row_no for i in bc.items)
                    if not parent_found:
                        warnings.append(f"Item '{item.item_code}' references non-existent parent row {item.parent_row_no}")
            
            # Check quantities
            zero_qty_items = [i.item_code for i in bc.items if i.qty == 0]
            if zero_qty_items:
                warnings.append(f"Items with zero quantity: {', '.join(zero_qty_items[:5])}")
            
            return {
                "success": len(issues) == 0,
                "valid": len(issues) == 0,
                "issues": issues,
                "warnings": warnings,
                "items_count": len(bc.items),
                "message": "✅ BOM Creator is valid" if not issues else f"❌ Found {len(issues)} issues"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== NATURAL LANGUAGE HANDLER ==========
    
    def handle_bom_request(self, message: str) -> Dict:
        """Parse and handle natural language BOM requests"""
        message_lower = message.lower()
        
        # Create BOM from TDS
        if "create bom" in message_lower and "tds" in message_lower:
            # Extract TDS name from message
            # Pattern: "create bom from tds [TDS-NAME]"
            import re
            match = re.search(r'tds\s+([^\s]+)', message_lower)
            if match:
                tds_name = match.group(1)
                return self.create_bom_from_tds(tds_name)
            return {"success": False, "error": "Please specify TDS name: 'create bom from tds [TDS-NAME]'"}
        
        # Validate BOM
        if "validate" in message_lower and "bom" in message_lower:
            import re
            match = re.search(r'bom[- ]?creator?\s+([^\s]+)', message_lower) or \
                    re.search(r'validate\s+([^\s]+)', message_lower)
            if match:
                return self.validate_bom_creator(match.group(1))
            return {"success": False, "error": "Please specify BOM Creator name"}
        
        # Submit BOM
        if "submit" in message_lower and "bom" in message_lower:
            import re
            match = re.search(r'bom[- ]?creator?\s+([^\s]+)', message_lower) or \
                    re.search(r'submit\s+([^\s]+)', message_lower)
            if match:
                return self.submit_bom_creator(match.group(1))
            return {"success": False, "error": "Please specify BOM Creator name"}
        
        return {
            "success": False, 
            "error": "Unknown command. Available: create bom from tds [NAME], validate bom [NAME], submit bom [NAME]"
        }


# ========== API ENDPOINTS ==========

@frappe.whitelist()
def create_bom_from_template(product_code: str, template_bom_name: str) -> Dict:
    """API: Create BOM from template"""
    agent = BOMCreatorAgent()
    return agent.create_bom_from_template(product_code, template_bom_name)

@frappe.whitelist()
def create_bom_from_tds(tds_name: str, template_bom_name: str = None) -> Dict:
    """API: Create BOM from TDS"""
    agent = BOMCreatorAgent()
    return agent.create_bom_from_tds(tds_name, template_bom_name)

@frappe.whitelist()
def validate_bom_creator(bom_creator_name: str) -> Dict:
    """API: Validate BOM Creator"""
    agent = BOMCreatorAgent()
    return agent.validate_bom_creator(bom_creator_name)

@frappe.whitelist()
def submit_bom_creator(bom_creator_name: str) -> Dict:
    """API: Submit BOM Creator"""
    agent = BOMCreatorAgent()
    return agent.submit_bom_creator(bom_creator_name)

@frappe.whitelist()
def handle_bom_request(message: str) -> Dict:
    """API: Handle natural language BOM request"""
    agent = BOMCreatorAgent()
    return agent.handle_bom_request(message)
