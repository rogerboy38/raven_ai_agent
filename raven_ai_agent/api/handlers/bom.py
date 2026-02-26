"""
BOM Commands + Label Fixer + Cancel/Revert
"""
import frappe
import json
import re
import requests
from typing import Optional, Dict, List


class BOMMixin:
    """Mixin for _handle_bom_commands"""

    def _handle_bom_commands(self, query: str, query_lower: str) -> Optional[Dict]:
        """Dispatched from execute_workflow_command"""
        # ==================== BOM COMMANDS ====================
        
        # Show BOM or BOM Creator details
        # Match BOM-xxx or any name pattern for BOM Creator (e.g., TEST-BOM-FIX)
        bom_match = re.search(r'show\s+(?:bom|bom\s+creator)\s+([^\s]+)', query, re.IGNORECASE)
        if not bom_match:
            bom_match = re.search(r'(BOM-[^\s]+)', query, re.IGNORECASE)
        
        if bom_match and ("show" in query_lower or "details" in query_lower or "items" in query_lower or "view" in query_lower):
            try:
                from raven_ai_agent.api.bom_fixer import get_bom_details
                
                bom_name = bom_match.group(1)
                
                # First try regular BOM
                result = get_bom_details(bom_name)
                
                # If not found, try BOM Creator
                if not result["success"] and "not found" in result.get("message", "").lower():
                    if frappe.db.exists("BOM Creator", bom_name):
                        from raven_ai_agent.agents.bom_creator_agent import BOMCreatorAgent
                        bc_agent = BOMCreatorAgent()
                        bc_result = bc_agent.get_bom_creator(bom_name)
                        
                        if bc_result["success"]:
                            site_name = frappe.local.site
                            bc = frappe.get_doc("BOM Creator", bom_name)
                            
                            bc_link = f"https://{site_name}/app/bom-creator/{bom_name}"
                            item_link = f"https://{site_name}/app/item/{bc.item_code}"
                            
                            status_icon = {"Draft": "📝", "Submitted": "✅", "In Progress": "⏳", "Completed": "✅"}.get(bc.status, "❓")
                            
                            msg = f"🏗️ **BOM Creator: [{bom_name}]({bc_link})**\n\n"
                            msg += f"  Product: **[{bc.item_code}]({item_link})**\n"
                            msg += f"  Status: {status_icon} {bc.status}\n"
                            msg += f"  Raw Material Cost: ${bc.raw_material_cost or 0:,.2f}\n\n"
                            
                            msg += f"**Items ({len(bc.items)}):** [📋 View All]({bc_link}#items)\n\n"
                            msg += "| # | Item Code | Description | Qty | UOM |\n"
                            msg += "|---|-----------|-------------|-----|-----|\n"
                            display_limit = 25
                            for idx, item in enumerate(bc.items[:display_limit], 1):
                                item_url = f"https://{site_name}/app/item/{item.item_code}"
                                desc = (item.item_name or item.item_code)[:30]
                                msg += f"| {idx} | [{item.item_code}]({item_url}) | {desc} | {item.qty or 1} | {item.uom or '-'} |\n"
                            
                            if len(bc.items) > display_limit:
                                remaining = len(bc.items) - display_limit
                                msg += f"\n[📦 View {remaining} more items...]({bc_link}#items)\n"
                            
                            return {
                                "success": True, 
                                "message": msg,
                                "link_doctype": "BOM Creator",
                                "link_document": bom_name
                            }
                        else:
                            return {"success": False, "error": bc_result["error"]}
                
                if not result["success"]:
                    return {"success": False, "error": result["message"]}
                
                # Format output with clickable links
                site_name = frappe.local.site
                status_icon = {"Draft": "📝", "Submitted": "✅", "Cancelled": "❌"}.get(result["status_text"], "❓")
                
                bom_link = f"https://{site_name}/app/bom/{bom_name}"
                item_link = f"https://{site_name}/app/item/{result['item']}"
                
                msg = f"📋 **BOM: [{bom_name}]({bom_link})**\n\n"
                msg += f"  Product: **[{result['item']}]({item_link})**\n"
                msg += f"  Status: {status_icon} {result['status_text']} (docstatus={result['docstatus']})\n"
                msg += f"  Active: {'Yes' if result['is_active'] else 'No'} | Default: {'Yes' if result['is_default'] else 'No'}\n"
                msg += f"  Quantity: {result['quantity']} | Total Cost: ${result['total_cost']:,.2f}\n\n"
                
                msg += f"**Items ({len(result['items'])}):**\n\n"
                for item in result["items"]:
                    is_label = item["item_code"].startswith("LBL")
                    icon = "🏷️" if is_label else "📦"
                    item_url = f"https://{site_name}/app/item/{item['item_code']}"
                    msg += f"{item['idx']}. {icon} **[{item['item_code']}]({item_url})**\n"
                    msg += f"   {item['item_name']}\n"
                    msg += f"   Qty: {item['qty']} {item['uom']} | Rate: ${item['rate']:,.2f} | Amount: ${item['amount']:,.2f}\n\n"
                
                if result["operations"]:
                    msg += f"---\n\n**Operations ({len(result['operations'])}):**\n\n"
                    for op in result["operations"]:
                        op_link = f"https://{site_name}/app/operation/{op['operation']}"
                        ws_link = f"https://{site_name}/app/workstation/{op['workstation']}"
                        msg += f"{op['idx']}. ⚙️ **[{op['operation']}]({op_link})**\n"
                        msg += f"   Workstation: [{op['workstation']}]({ws_link}) | Time: {op['time_in_mins']} mins\n\n"
                
                return {"success": True, "message": msg}
                
            except Exception as e:
                return {"success": False, "error": f"BOM Details Error: {str(e)}"}
        
        # ==================== BOM LABEL FIXER ====================
        
        # Check BOM labels for item
        if "check bom" in query_lower or "fix bom" in query_lower or "bom label" in query_lower:
            try:
                from raven_ai_agent.api.bom_fixer import check_and_fix_item, fix_multiple_items, force_fix_submitted_bom
                
                # Extract item code(s)
                item_match = re.search(r'(?:for|item|items?)\s+([^\s,]+(?:\s*,\s*[^\s,]+)*)', query, re.IGNORECASE)
                bom_match = re.search(r'(BOM-[^\s]+)', query, re.IGNORECASE)
                
                # Force fix specific BOM
                if "force" in query_lower and bom_match:
                    bom_name = bom_match.group(1)
                    label_match = re.search(r'label\s+(LBL[^\s]+)', query, re.IGNORECASE)
                    if label_match:
                        label_code = label_match.group(1)
                    else:
                        # Try to derive from BOM name
                        base = bom_name.replace("BOM-", "").split("-")[0]
                        label_code = f"LBL{base}"
                    
                    result = force_fix_submitted_bom(bom_name, label_code)
                    if result["success"]:
                        return {"success": True, "message": f"⚡ **FORCE FIX RESULT**\n\n{result['message']}"}
                    else:
                        return {"success": False, "error": result["message"]}
                
                # Check/fix single item
                elif item_match:
                    items_str = item_match.group(1)
                    items = [i.strip() for i in items_str.split(",")]
                    
                    auto_fix = "fix" in query_lower or is_confirm
                    
                    if len(items) == 1:
                        result = check_and_fix_item(items[0], auto_fix=auto_fix)
                        
                        msg = f"🏭 **BOM LABEL CHECK FOR {items[0]}**\n\n"
                        msg += f"  Label Item: `{result['label_code']}` {'✅ Exists' if result['label_exists'] else '❌ Missing'}\n"
                        msg += f"  BOMs Found: {len(result['boms_found'])}\n\n"
                        
                        if result['boms_fixed']:
                            msg += "**Fixed:**\n"
                            for fix in result['boms_fixed']:
                                msg += f"  ✅ {fix['bom']}: {fix['action']}\n"
                        
                        if result['boms_skipped']:
                            msg += "\n**Skipped/Pending:**\n"
                            for skip in result['boms_skipped']:
                                msg += f"  ⏭️ {skip['bom']}: {skip['reason']}\n"
                        
                        if result['errors']:
                            msg += "\n**Errors:**\n"
                            for err in result['errors']:
                                msg += f"  ❌ {err}\n"
                        
                        if not auto_fix and any(s.get('action_needed') for s in result.get('boms_skipped', [])):
                            msg += "\n💡 Use `@ai fix bom for " + items[0] + "` to auto-fix"
                        
                        return {"success": True, "message": msg}
                    else:
                        # Multiple items
                        result = fix_multiple_items(items, auto_fix=auto_fix)
                        
                        msg = f"🏭 **BOM LABEL BULK CHECK** ({result['mode']})\n\n"
                        msg += f"  Items: {result['total_items']}\n"
                        msg += f"  BOMs Fixed: {result['boms_fixed']}\n"
                        msg += f"  BOMs Skipped: {result['boms_skipped']}\n"
                        msg += f"  Errors: {result['errors']}\n"
                        
                        if not auto_fix:
                            msg += "\n💡 Use `@ai fix bom for items ...` to auto-fix"
                        
                        return {"success": True, "message": msg}
                
                else:
                    return {
                        "success": True,
                        "message": """🏭 **BOM LABEL FIXER**

**Commands:**
• `@ai check bom for 0302` - Check single item
• `@ai fix bom for 0302` - Auto-fix single item
• `@ai check bom for items 0302, 0417, 0433` - Check multiple
• `@ai fix bom for items 0302, 0417, 0433` - Fix multiple
• `@ai force fix bom BOM-0302-001 label LBL0302` - Force SQL fix

**How it works:**
1. Checks if label item (LBLxxxx) exists
2. Finds all BOMs for the item
3. Draft BOMs: Adds label directly
4. Submitted BOMs: Cancel → Amend → Add Label → Submit
5. Cancelled BOMs: Suggests creating new version"""
                    }
                    
            except Exception as e:
                return {"success": False, "error": f"BOM Fixer Error: {str(e)}"}
        
        # ==================== END BOM LABEL FIXER ====================
        
        # ==================== BOM CANCEL / REVERT TO DRAFT ====================
        
        # Cancel BOM or Revert cancelled BOM to Draft
        bom_match = re.search(r'(BOM-[^\s]+)', query, re.IGNORECASE)
        if bom_match and ("cancel" in query_lower or "revert" in query_lower or "to draft" in query_lower or "undraft" in query_lower):
            try:
                bom_name = bom_match.group(1)
                bom = frappe.get_doc("BOM", bom_name)
                
                # Case 1: Cancel submitted BOM
                if "cancel" in query_lower and bom.docstatus == 1:
                    if not is_confirm:
                        return {
                            "requires_confirmation": True,
                            "preview": f"⚠️ **CANCEL BOM {bom_name}?**\n\n  Item: {bom.item}\n  Status: Submitted\n\nThis will cancel the BOM. Say 'confirm' or use `!` prefix."
                        }
                    
                    bom.cancel()
                    frappe.db.commit()
                    return {
                        "success": True,
                        "message": f"✅ BOM **{bom_name}** has been cancelled.\n\n💡 Use `@ai !revert bom {bom_name} to draft` to make it editable again."
                    }
                
                # Case 2: Revert cancelled BOM to Draft
                if ("revert" in query_lower or "to draft" in query_lower or "undraft" in query_lower) and bom.docstatus == 2:
                    if not is_confirm:
                        return {
                            "requires_confirmation": True,
                            "preview": f"🔄 **REVERT BOM {bom_name} TO DRAFT?**\n\n  Item: {bom.item}\n  Current Status: Cancelled (docstatus=2)\n\nThis will reset the BOM to Draft status so you can edit it. Say 'confirm' or use `!` prefix."
                        }
                    
                    # Reset BOM to draft via SQL
                    frappe.db.sql("""
                        UPDATE `tabBOM` 
                        SET docstatus = 0, is_active = 0, is_default = 0
                        WHERE name = %s
                    """, bom_name)
                    
                    # Reset child tables
                    frappe.db.sql("UPDATE `tabBOM Item` SET docstatus = 0 WHERE parent = %s", bom_name)
                    frappe.db.sql("UPDATE `tabBOM Operation` SET docstatus = 0 WHERE parent = %s", bom_name)
                    frappe.db.sql("UPDATE `tabBOM Explosion Item` SET docstatus = 0 WHERE parent = %s", bom_name)
                    frappe.db.sql("UPDATE `tabBOM Scrap Item` SET docstatus = 0 WHERE parent = %s", bom_name)
                    
                    frappe.db.commit()
                    
                    return {
                        "success": True,
                        "message": f"✅ BOM **{bom_name}** reverted to Draft!\n\n  Item: {bom.item}\n  Status: Draft (docstatus=0)\n  is_active: No\n  is_default: No\n\n📝 You can now edit the BOM in ERPNext."
                    }
                
                # Case 3: Already in the target state
                if bom.docstatus == 0:
                    return {"success": True, "message": f"BOM **{bom_name}** is already in Draft status."}
                
                if "cancel" in query_lower and bom.docstatus == 2:
                    return {"success": True, "message": f"BOM **{bom_name}** is already Cancelled.\n\n💡 Use `@ai !revert bom {bom_name} to draft` to make it editable."}
                
                if ("revert" in query_lower or "to draft" in query_lower) and bom.docstatus == 1:
                    return {"success": False, "error": f"BOM **{bom_name}** is Submitted. Cancel it first with `@ai !cancel bom {bom_name}`"}
                
            except frappe.DoesNotExistError:
                return {"success": False, "error": f"BOM **{bom_name}** not found."}
            except Exception as e:
                return {"success": False, "error": f"BOM operation failed: {str(e)}"}
        
        # ==================== END BOM CANCEL / REVERT ====================

        return None
