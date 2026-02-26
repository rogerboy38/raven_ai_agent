"""
Manufacturing SOP Commands + Stock Entry Management
"""
import frappe
import json
import re
import requests
from typing import Optional, Dict, List


class ManufacturingMixin:
    """Mixin for _handle_manufacturing_commands"""

    def _handle_manufacturing_commands(self, query: str, query_lower: str) -> Optional[Dict]:
        """Dispatched from execute_workflow_command"""
        # ==================== MANUFACTURING SOP COMMANDS ====================
        
        # Show Work Orders
        if "show work order" in query_lower or "list work order" in query_lower or "mis ordenes" in query_lower:
            try:
                work_orders = frappe.get_list("Work Order",
                    filters={"docstatus": ["<", 2]},
                    fields=["name", "production_item", "qty", "produced_qty", "status", "planned_start_date"],
                    order_by="modified desc",
                    limit=20
                )
                if work_orders:
                    site_name = frappe.local.site
                    msg = "📋 **ACTIVE WORK ORDERS**\n\n"
                    msg += "| Work Order | Product | Progress | Status | Start Date |\n"
                    msg += "|------------|---------|----------|--------|------------|\n"
                    for wo in work_orders:
                        progress = f"{wo.produced_qty or 0}/{wo.qty}"
                        wo_link = f"[{wo.name}](https://{site_name}/app/work-order/{wo.name})"
                        start_date = str(wo.planned_start_date or '-')
                        msg += f"| {wo_link} | {wo.production_item} | {progress} | {wo.status} | {start_date} |\n"
                    return {"success": True, "message": msg}
                return {"success": True, "message": "No active work orders found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Work Order
        if "create work order" in query_lower or "crear orden de produccion" in query_lower:
            # Extract item and quantity: @ai create work order for ITEM-001 qty 100
            item_match = re.search(r'(?:for|para)\s+([^\s]+)', query, re.IGNORECASE)
            qty_match = re.search(r'(?:qty|quantity|cantidad)\s+(\d+)', query, re.IGNORECASE)
            
            if item_match:
                item_code = item_match.group(1).strip()
                qty = int(qty_match.group(1)) if qty_match else 1
                
                try:
                    # Check if item exists and has BOM
                    if not frappe.db.exists("Item", item_code):
                        return {"success": False, "error": f"Item '{item_code}' not found."}
                    
                    bom = frappe.db.get_value("BOM", {"item": item_code, "is_active": 1, "is_default": 1}, "name")
                    if not bom:
                        return {"success": False, "error": f"No active BOM found for '{item_code}'. Create a BOM first."}
                    
                    if not is_confirm:
                        return {
                            "requires_confirmation": True,
                            "preview": f"🏭 CREATE WORK ORDER?\n\n  Item: {item_code}\n  BOM: {bom}\n  Qty: {qty}\n\nSay 'confirm' to proceed."
                        }
                    
                    wo = frappe.get_doc({
                        "doctype": "Work Order",
                        "production_item": item_code,
                        "bom_no": bom,
                        "qty": qty,
                        "wip_warehouse": frappe.db.get_single_value("Manufacturing Settings", "default_wip_warehouse"),
                        "fg_warehouse": frappe.db.get_single_value("Manufacturing Settings", "default_fg_warehouse")
                    })
                    wo.insert()
                    site_name = frappe.local.site
                    wo_link = f"https://{site_name}/app/work-order/{wo.name}"
                    return {
                        "success": True,
                        "message": f"✅ Work Order created: **[{wo.name}]({wo_link})**\n\n  Item: {item_code}\n  Qty: {qty}\n  Status: {wo.status}"
                    }
                except Exception as e:
                    return {"success": False, "error": str(e)}
        
        # Reserve Stock for Work Order
        wo_match = re.search(r'(MFG-WO-\d+|LOTE-\d+|P-VTA-\d+|WO-[^\s]+)', query, re.IGNORECASE)
        if wo_match and ("reserve stock" in query_lower or "reservar" in query_lower):
            try:
                wo_name = wo_match.group(1)
                wo = frappe.get_doc("Work Order", wo_name)
                
                if wo.docstatus != 1:
                    return {"success": False, "error": f"Work Order {wo_name} must be submitted first."}
                
                # Check material availability
                available_items = []
                unavailable_items = []
                for item in wo.required_items:
                    available = frappe.db.get_value("Bin", 
                        {"item_code": item.item_code, "warehouse": item.source_warehouse},
                        "actual_qty") or 0
                    if available >= item.required_qty:
                        available_items.append(f"✅ {item.item_code}: {item.required_qty}")
                    else:
                        unavailable_items.append(f"❌ {item.item_code}: Need {item.required_qty}, Have {available}")
                
                if unavailable_items:
                    return {
                        "success": False,
                        "error": f"Cannot reserve - insufficient stock:\n" + "\n".join(unavailable_items)
                    }
                
                # In ERPNext, stock reservation is typically done via Stock Reservation Entry
                # For now, we'll just confirm materials are available
                return {
                    "success": True,
                    "message": f"✅ Materials verified for **{wo_name}**\n\nAll items available:\n" + "\n".join(available_items) + "\n\n💡 Use `@ai issue materials for {wo_name}` to transfer to WIP warehouse."
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Start Production / Submit Work Order
        if wo_match and ("start production" in query_lower or "submit work order" in query_lower or "submit wo" in query_lower or "iniciar produccion" in query_lower or "release" in query_lower or "submit" in query_lower):
            try:
                wo_name = wo_match.group(1)
                wo = frappe.get_doc("Work Order", wo_name)
                
                if wo.status == "In Process":
                    return {"success": True, "message": f"✅ Work Order **{wo_name}** is already in process."}
                
                if wo.docstatus == 1:
                    return {"success": True, "message": f"✅ Work Order **{wo_name}** is already submitted.\n\n  Status: {wo.status}"}
                
                if wo.docstatus == 2:
                    return {"success": False, "error": f"Work Order {wo_name} is cancelled and cannot be submitted."}
                
                # Check if linked Sales Order is cancelled
                if wo.sales_order:
                    so_status = frappe.db.get_value("Sales Order", wo.sales_order, "docstatus")
                    if so_status == 2:
                        return {
                            "success": False,
                            "error": f"Cannot submit Work Order **{wo_name}** - linked Sales Order **{wo.sales_order}** is cancelled.\n\n💡 **Options:**\n1. Unlink the SO: `@ai unlink sales order from {wo_name}`\n2. Create a new WO without SO link"
                        }
                
                if wo.docstatus == 0:
                    if not is_confirm:
                        return {
                            "requires_confirmation": True,
                            "preview": f"🚀 START PRODUCTION FOR {wo_name}?\n\n  Item: {wo.production_item}\n  Qty: {wo.qty}\n  Sales Order: {wo.sales_order or 'None'}\n\nThis will submit the Work Order. Say 'confirm' or use `!` prefix to proceed."
                        }
                    wo.submit()
                    return {
                        "success": True,
                        "message": f"✅ Work Order **{wo_name}** submitted and started!\n\n  Status: {wo.status}\n  Item: {wo.production_item}"
                    }
                
                return {"success": True, "message": f"Work Order **{wo_name}** status: {wo.status}"}
            except Exception as e:
                error_msg = str(e)
                if "cancelled" in error_msg.lower():
                    return {"success": False, "error": f"Cannot submit - linked document is cancelled.\n\n**Error:** {error_msg}\n\n💡 Unlink the cancelled document first."}
                return {"success": False, "error": str(e)}
        
        # Unlink Sales Order from Work Order
        if wo_match and ("unlink" in query_lower and "sales order" in query_lower):
            try:
                wo_name = wo_match.group(1)
                wo = frappe.get_doc("Work Order", wo_name)
                
                if not wo.sales_order:
                    return {"success": True, "message": f"Work Order **{wo_name}** has no linked Sales Order."}
                
                old_so = wo.sales_order
                
                if wo.docstatus != 0:
                    return {"success": False, "error": f"Cannot modify submitted Work Order {wo_name}. Cancel it first or create a new one."}
                
                if not is_confirm:
                    return {
                        "requires_confirmation": True,
                        "preview": f"🔗 UNLINK SALES ORDER FROM {wo_name}?\n\n  Current SO: {old_so}\n\nThis will remove the SO link. Say 'confirm' or use `!` prefix."
                    }
                
                wo.sales_order = None
                wo.sales_order_item = None
                wo.save()
                frappe.db.commit()
                
                return {
                    "success": True,
                    "message": f"✅ Unlinked Sales Order **{old_so}** from Work Order **{wo_name}**\n\nYou can now submit the Work Order."
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Show Job Cards for Work Order
        if wo_match and ("job card" in query_lower or "tarjeta" in query_lower or "operations" in query_lower):
            try:
                wo_name = wo_match.group(1)
                job_cards = frappe.get_list("Job Card",
                    filters={"work_order": wo_name},
                    fields=["name", "operation", "workstation", "status", "for_quantity", "total_completed_qty"],
                    order_by="sequence_id"
                )
                if job_cards:
                    site_name = frappe.local.site
                    jc_list = []
                    for jc in job_cards:
                        progress = f"{jc.total_completed_qty or 0}/{jc.for_quantity}"
                        jc_link = f"https://{site_name}/app/job-card/{jc.name}"
                        jc_list.append(f"• **[{jc.name}]({jc_link})**\n   {jc.operation} · {jc.workstation or 'N/A'} · {progress} · {jc.status}")
                    return {
                        "success": True,
                        "message": f"🎫 **JOB CARDS FOR {wo_name}**\n\n" + "\n\n".join(jc_list)
                    }
                return {"success": True, "message": f"No job cards found for {wo_name}. Work order may not have routing defined."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Update Progress for Work Order
        if wo_match and ("update progress" in query_lower or "report progress" in query_lower or "actualizar avance" in query_lower):
            qty_match = re.search(r'(?:qty|quantity|cantidad)\s+(\d+)', query, re.IGNORECASE)
            if qty_match:
                produced_qty = int(qty_match.group(1))
                try:
                    wo_name = wo_match.group(1)
                    wo = frappe.get_doc("Work Order", wo_name)
                    
                    if wo.docstatus != 1:
                        return {"success": False, "error": f"Work Order {wo_name} must be submitted first."}
                    
                    remaining = wo.qty - (wo.produced_qty or 0)
                    if produced_qty > remaining:
                        return {"success": False, "error": f"Cannot produce {produced_qty}. Only {remaining} remaining."}
                    
                    if not is_confirm:
                        return {
                            "requires_confirmation": True,
                            "preview": f"📊 UPDATE PROGRESS FOR {wo_name}?\n\n  Current: {wo.produced_qty or 0}/{wo.qty}\n  Adding: {produced_qty}\n  New Total: {(wo.produced_qty or 0) + produced_qty}/{wo.qty}\n\nSay 'confirm' to proceed."
                        }
                    
                    # Create manufacture stock entry for the quantity
                    se = frappe.get_doc({
                        "doctype": "Stock Entry",
                        "stock_entry_type": "Manufacture",
                        "work_order": wo_name,
                        "from_bom": 1,
                        "bom_no": wo.bom_no,
                        "fg_completed_qty": produced_qty
                    })
                    se.get_items()
                    se.insert()
                    se.submit()
                    
                    return {
                        "success": True,
                        "message": f"✅ Progress updated for **{wo_name}**\n\n  Produced: {produced_qty}\n  Stock Entry: {se.name}\n  New Total: {(wo.produced_qty or 0) + produced_qty}/{wo.qty}"
                    }
                except Exception as e:
                    return {"success": False, "error": str(e)}
        
        # Material Status for Work Order
        # Match various WO formats: MFG-WO-02725, LOTE-00225, P-VTA-00425, WO-XXX
        wo_match = re.search(r'(MFG-WO-\d+|LOTE-\d+|P-VTA-\d+|WO-[^\s]+)', query, re.IGNORECASE)
        if wo_match and ("material status" in query_lower or "component" in query_lower or "disponibilidad" in query_lower):
            try:
                wo_name = wo_match.group(1)
                wo = frappe.get_doc("Work Order", wo_name)
                items_status = []
                for item in wo.required_items:
                    available = frappe.db.get_value("Bin", 
                        {"item_code": item.item_code, "warehouse": item.source_warehouse},
                        "actual_qty") or 0
                    status = "✅" if available >= item.required_qty else "❌"
                    items_status.append(f"  {status} {item.item_code}: Need {item.required_qty}, Available {available}")
                
                return {
                    "success": True,
                    "message": f"📦 MATERIAL STATUS FOR {wo_name}:\n" + "\n".join(items_status)
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Issue Materials for Work Order
        if wo_match and ("issue material" in query_lower or "emitir material" in query_lower):
            try:
                wo_name = wo_match.group(1)
                wo = frappe.get_doc("Work Order", wo_name)
                
                if not is_confirm:
                    items_preview = [f"  - {i.item_code}: {i.required_qty} {i.stock_uom}" for i in wo.required_items[:5]]
                    return {
                        "requires_confirmation": True,
                        "preview": f"📤 ISSUE MATERIALS FOR {wo_name}?\n\nItems:\n" + "\n".join(items_preview) + "\n\nSay 'confirm' or use '!' prefix to proceed."
                    }
                
                # Create Stock Entry
                se = frappe.get_doc({
                    "doctype": "Stock Entry",
                    "stock_entry_type": "Material Transfer for Manufacture",
                    "work_order": wo_name,
                    "from_bom": 1,
                    "bom_no": wo.bom_no,
                    "fg_completed_qty": wo.qty
                })
                se.get_items()
                se.insert()
                se.submit()
                
                return {
                    "success": True,
                    "message": f"✅ Material Issue created: {se.name}\n\nItems transferred to WIP warehouse."
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Finish Work Order / Complete Production (Manufacture Entry)
        if wo_match and ("finish work order" in query_lower or "complete production" in query_lower or "finalizar" in query_lower or "completar" in query_lower):
            try:
                wo_name = wo_match.group(1)
                wo = frappe.get_doc("Work Order", wo_name)
                
                remaining = wo.qty - (wo.produced_qty or 0)
                if remaining <= 0:
                    return {"success": True, "message": f"✅ Work Order {wo_name} already completed!"}
                
                if not is_confirm:
                    return {
                        "requires_confirmation": True,
                        "preview": f"🏭 COMPLETE PRODUCTION FOR {wo_name}?\n\n  Item: {wo.production_item}\n  Quantity: {remaining}\n  Target: {wo.fg_warehouse}\n\nSay 'confirm' to create Manufacture entry."
                    }
                
                # Create Manufacture Stock Entry
                se = frappe.get_doc({
                    "doctype": "Stock Entry",
                    "stock_entry_type": "Manufacture",
                    "work_order": wo_name,
                    "from_bom": 1,
                    "bom_no": wo.bom_no,
                    "fg_completed_qty": remaining
                })
                se.get_items()
                se.insert()
                se.submit()
                
                return {
                    "success": True,
                    "message": f"✅ Production completed: {se.name}\n\n  {wo.production_item}: {remaining} units to {wo.fg_warehouse}"
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Quality Check
        if "quality" in query_lower and ("check" in query_lower or "inspection" in query_lower or "calidad" in query_lower):
            try:
                # Get recent quality inspections
                qis = frappe.get_list("Quality Inspection",
                    filters={"docstatus": ["<", 2]},
                    fields=["name", "item_code", "status", "inspected_by", "modified"],
                    order_by="modified desc",
                    limit=10
                )
                if qis:
                    qi_list = [f"• **{qi.name}**\n   {qi.item_code} · {qi.status}" for qi in qis]
                    return {
                        "success": True,
                        "message": f"🔍 **RECENT QUALITY INSPECTIONS**\n\n" + "\n\n".join(qi_list)
                    }
                return {"success": True, "message": "No quality inspections found. Create one in Quality > Quality Inspection."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # BOM Cost Report
        if "bom cost" in query_lower or "cost report" in query_lower or "costo bom" in query_lower:
            try:
                boms = frappe.get_list("BOM",
                    filters={"is_active": 1, "is_default": 1},
                    fields=["name", "item", "total_cost", "operating_cost", "raw_material_cost"],
                    limit=10
                )
                if boms:
                    bom_list = []
                    for bom in boms:
                        bom_list.append(f"  - {bom.name} ({bom.item})\n    Materials: ${bom.raw_material_cost:,.2f} | Operations: ${bom.operating_cost:,.2f} | Total: ${bom.total_cost:,.2f}")
                    return {
                        "success": True,
                        "message": f"💰 BOM COST REPORT:\n" + "\n\n".join(bom_list)
                    }
                return {"success": True, "message": "No active BOMs found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Troubleshooting Guide
        if "troubleshoot" in query_lower or "problem" in query_lower or "issue" in query_lower:
            troubleshoot_guide = """🔧 **MANUFACTURING TROUBLESHOOTING GUIDE**

📦 **INSUFFICIENT STOCK**
→ `@ai material status for [WO]` → Create Material Request → Generate Purchase Order

🔍 **QUALITY FAILURE**
→ Create Quality Inspection (Rejected) → Stock Entry to Quarantine → Document in QI notes

💰 **COST VARIANCE >5%**
→ `@ai show BOM cost report` → Compare with actual costs → Check Stock Ledger

⚠️ **WORK ORDER STUCK**
→ Check materials issued → Verify no pending QI → `@ai workflow status for [WO]`"""
            return {"success": True, "message": troubleshoot_guide}
        
        # ==================== STOCK ENTRY MANAGEMENT ====================
        
        # Material Receipt - Create stock entry to add inventory
        se_match = re.search(r'(MAT-STE-\d{4}-\d+|STE-\d+)', query, re.IGNORECASE)
        item_match = re.search(r'(ITEM[_-]?\d+)', query, re.IGNORECASE)
        
        if ("material receipt" in query_lower or "receive material" in query_lower or "add stock" in query_lower) and item_match:
            try:
                item_code = item_match.group(1).upper().replace("-", "_")
                warehouse_match = re.search(r'warehouse[:\s]+([^\n,]+)', query, re.IGNORECASE)
                qty_match = re.search(r'qty[:\s]*(\d+\.?\d*)|quantity[:\s]*(\d+\.?\d*)|(\d+\.?\d*)\s*(?:units?|pcs?|qty)', query, re.IGNORECASE)
                price_match = re.search(r'price[:\s]*\$?(\d+\.?\d*)|rate[:\s]*\$?(\d+\.?\d*)|\$(\d+\.?\d*)', query, re.IGNORECASE)
                
                target_warehouse = warehouse_match.group(1).strip() if warehouse_match else "FG to Sell Warehouse - AMB-W"
                qty = float(qty_match.group(1) or qty_match.group(2) or qty_match.group(3)) if qty_match else 1
                price = float(price_match.group(1) or price_match.group(2) or price_match.group(3)) if price_match else None
                
                # Check if item exists
                if not frappe.db.exists("Item", item_code):
                    return {"success": False, "error": f"Item {item_code} not found"}
                
                # Get item valuation rate if no price specified
                if not price:
                    price = frappe.db.get_value("Item", item_code, "valuation_rate") or 0
                
                if not is_confirm:
                    price_info = f"  Price: ${price:.2f}" if price else "  Price: (auto)"
                    return {
                        "requires_confirmation": True,
                        "preview": f"📥 MATERIAL RECEIPT?\n\n  Item: {item_code}\n  Qty: {qty}\n{price_info}\n  Warehouse: {target_warehouse}\n\nSay 'confirm' or use '!' prefix to proceed. (Tip: Use `@ai !command` to skip confirmation)"
                    }
                
                # Look for existing batch first, create if not found
                existing_batches = frappe.get_all("Batch",
                    filters={"item": item_code},
                    fields=["name"],
                    order_by="creation desc",
                    limit=1
                )
                
                if existing_batches:
                    batch_id = existing_batches[0]["name"]
                else:
                    # Create new batch - let Frappe auto-name it (LOTE###)
                    batch = frappe.get_doc({
                        "doctype": "Batch",
                        "item": item_code
                    })
                    batch.insert(ignore_permissions=True)
                    batch_id = batch.name
                
                # Create Material Receipt with price
                se = frappe.get_doc({
                    "doctype": "Stock Entry",
                    "stock_entry_type": "Material Receipt",
                    "purpose": "Material Receipt"
                })
                
                # Set movement type if field exists
                if hasattr(se, 'custom_movement_type'):
                    se.custom_movement_type = "561"
                
                item_entry = {
                    "item_code": item_code,
                    "qty": qty,
                    "t_warehouse": target_warehouse,
                    "batch_no": batch_id
                }
                
                if price:
                    item_entry["basic_rate"] = price
                    item_entry["valuation_rate"] = price
                
                se.append("items", item_entry)
                se.insert(ignore_permissions=True)
                se.submit()
                
                total_value = qty * price if price else 0
                return {
                    "success": True,
                    "message": f"✅ Material Receipt created: **{se.name}**\n\n  Item: {item_code}\n  Qty: {qty}\n  Price: ${price:.2f}\n  Total: ${total_value:.2f}\n  Batch: {batch_id}\n  Warehouse: {target_warehouse}"
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Convert Stock Entry to Material Receipt
        if se_match and ("convert" in query_lower and "material receipt" in query_lower):
            try:
                se_name = se_match.group(1)
                se = frappe.get_doc("Stock Entry", se_name)
                
                if se.docstatus != 0:
                    return {"success": False, "error": f"Stock Entry {se_name} is not a Draft (docstatus: {se.docstatus})"}
                
                if not is_confirm:
                    return {
                        "requires_confirmation": True,
                        "preview": f"🔄 CONVERT TO MATERIAL RECEIPT?\n\n  Entry: {se_name}\n  Current Type: {se.stock_entry_type}\n  Items: {len(se.items)}\n\nSay 'confirm' or use '!' prefix to proceed. (Tip: Use `@ai !command` to skip confirmation)"
                    }
                
                # Convert to Material Receipt
                se.stock_entry_type = "Material Receipt"
                se.purpose = "Material Receipt"
                
                # Set movement type if field exists
                if hasattr(se, 'custom_movement_type'):
                    se.custom_movement_type = "561"
                
                for item in se.items:
                    item.s_warehouse = None  # Clear source warehouse
                    if not item.t_warehouse:
                        item.t_warehouse = "FG to Sell Warehouse - AMB-W"
                    # Find existing batch or create new one
                    if item.item_code and not item.batch_no:
                        existing_batches = frappe.get_all("Batch",
                            filters={"item": item.item_code},
                            fields=["name"],
                            order_by="creation desc",
                            limit=1
                        )
                        if existing_batches:
                            item.batch_no = existing_batches[0]["name"]
                        else:
                            batch = frappe.get_doc({
                                "doctype": "Batch",
                                "item": item.item_code
                            })
                            batch.insert(ignore_permissions=True)
                            item.batch_no = batch.name
                
                se.save()
                se.submit()
                
                return {
                    "success": True,
                    "message": f"✅ Converted to Material Receipt: **{se_name}**\n\n  Type: Material Receipt\n  Items: {len(se.items)}\n  Status: Submitted"
                }
            except Exception as e:
                frappe.db.rollback()
                return {"success": False, "error": str(e)}
        
        # Verify Stock Entries
        if "verify stock entr" in query_lower or "check stock entr" in query_lower:
            try:
                entries = frappe.get_list("Stock Entry",
                    filters={"purpose": "Material Receipt"},
                    fields=["name", "posting_date", "docstatus", "total_qty", "stock_entry_type"],
                    order_by="modified desc",
                    limit=20
                )
                
                submitted = [e for e in entries if e.docstatus == 1]
                draft = [e for e in entries if e.docstatus == 0]
                
                msg = f"📊 **STOCK ENTRY VERIFICATION**\n\n  ✅ Submitted: {len(submitted)}\n  📝 Draft: {len(draft)}\n  📦 Total: {len(entries)}"
                
                if draft:
                    draft_list = [f"  - {e.name}" for e in draft[:5]]
                    msg += f"\n\n**Draft Entries:**\n" + "\n".join(draft_list)
                
                return {"success": True, "message": msg}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Check Stock Ledger Impact
        if ("stock ledger" in query_lower or "stock balance" in query_lower) and ("check" in query_lower or "impact" in query_lower or "show" in query_lower):
            try:
                warehouse = "FG to Sell Warehouse - AMB-W"
                warehouse_match = re.search(r'warehouse[:\s]+([^\n,]+)', query, re.IGNORECASE)
                if warehouse_match:
                    warehouse = warehouse_match.group(1).strip()
                
                ledger = frappe.get_list("Stock Ledger Entry",
                    filters={"warehouse": warehouse},
                    fields=["item_code", "actual_qty", "qty_after_transaction", "posting_date", "voucher_no"],
                    order_by="posting_date desc",
                    limit=15
                )
                
                if ledger:
                    ledger_list = [f"• **{l.item_code}**\n   Qty: {l.actual_qty:+.0f} → Balance: {l.qty_after_transaction:.0f}\n   {l.voucher_no}" for l in ledger]
                    return {
                        "success": True,
                        "message": f"📈 **STOCK LEDGER - {warehouse}**\n\n" + "\n\n".join(ledger_list)
                    }
                return {"success": True, "message": f"No stock ledger entries found for {warehouse}"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # List Batches
        if "list batch" in query_lower or "show batch" in query_lower:
            try:
                batches = frappe.get_list("Batch",
                    fields=["name", "item", "batch_qty", "expiry_date", "creation"],
                    order_by="creation desc",
                    limit=20
                )
                
                if batches:
                    batch_list = [f"• **{b.name}**\n   Item: {b.item} · Qty: {b.batch_qty or 0}" for b in batches]
                    return {
                        "success": True,
                        "message": f"📦 **RECENT BATCHES**\n\n" + "\n\n".join(batch_list)
                    }
                return {"success": True, "message": "No batches found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # ==================== END STOCK ENTRY MANAGEMENT ====================
        
        # ==================== END MANUFACTURING SOP ====================

        return None
