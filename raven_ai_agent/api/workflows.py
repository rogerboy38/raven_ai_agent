"""
ERPNext Workflow Operations
Level 2/3 Autonomy - Document Creation & Workflow Transitions
"""
import frappe
import json
from typing import Dict, List, Optional
from frappe.utils import nowdate, add_days


class WorkflowExecutor:
    """Execute ERPNext workflow operations with confirmation"""
    
    def __init__(self, user: str):
        self.user = user
        self.site_name = frappe.local.site
    
    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable link"""
        slug = doctype.lower().replace(" ", "-")
        return f"https://{self.site_name}/app/{slug}/{name}"
    
    # ========== QUOTATION TO SALES ORDER ==========
    def get_quotation_details(self, quotation_name: str) -> Dict:
        """Get quotation details for conversion"""
        try:
            doc = frappe.get_doc("Quotation", quotation_name)
            return {
                "success": True,
                "quotation": {
                    "name": doc.name,
                    "customer": doc.party_name,
                    "grand_total": doc.grand_total,
                    "currency": doc.currency,
                    "items": [{
                        "item_code": item.item_code,
                        "item_name": item.item_name,
                        "qty": item.qty,
                        "rate": item.rate,
                        "amount": item.amount
                    } for item in doc.items],
                    "status": doc.status,
                    "link": self.make_link("Quotation", doc.name)
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def create_sales_order_from_quotation(self, quotation_name: str, confirm: bool = False) -> Dict:
        """Convert Quotation to Sales Order"""
        if not confirm:
            # Preview mode - show what will be created
            details = self.get_quotation_details(quotation_name)
            if not details["success"]:
                return details
            
            q = details["quotation"]
            return {
                "success": True,
                "requires_confirmation": True,
                "action": "create_sales_order",
                "preview": f"""
**Creating Sales Order from Quotation {q['name']}**

| Field | Value |
|-------|-------|
| Customer | {q['customer']} |
| Grand Total | {q['currency']} {q['grand_total']:,.2f} |
| Items | {len(q['items'])} line(s) |

**Items:**
""" + "\n".join([f"- {item['item_code']}: {item['qty']} × {item['rate']:,.2f} = {item['amount']:,.2f}" for item in q['items']]) + """

⚠️ **Confirm?** Reply: `@ai confirm create sales order from """ + quotation_name + "`"
            }
        
        # Execute creation
        try:
            from erpnext.selling.doctype.quotation.quotation import make_sales_order
            
            # Auto-extend validity for expired quotations (migration mode)
            valid_till = frappe.db.get_value("Quotation", quotation_name, "valid_till")
            if valid_till and str(valid_till) < nowdate():
                frappe.db.set_value("Quotation", quotation_name, "valid_till", add_days(nowdate(), 30))
                frappe.db.commit()
            
            so = make_sales_order(quotation_name)
            so.delivery_date = add_days(nowdate(), 30)  # Default 30 days
            so.insert()
            frappe.db.commit()
            
            return {
                "success": True,
                "message": f"✅ Sales Order **{so.name}** created from Quotation {quotation_name}",
                "sales_order": {
                    "name": so.name,
                    "customer": so.customer,
                    "grand_total": so.grand_total,
                    "link": self.make_link("Sales Order", so.name)
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== SALES ORDER TO WORK ORDER ==========
    def get_sales_order_details(self, so_name: str) -> Dict:
        """Get Sales Order details for Work Order creation"""
        try:
            doc = frappe.get_doc("Sales Order", so_name)
            items_with_bom = []
            for item in doc.items:
                bom = frappe.db.get_value("BOM", {"item": item.item_code, "is_active": 1, "is_default": 1}, "name")
                items_with_bom.append({
                    "item_code": item.item_code,
                    "item_name": item.item_name,
                    "qty": item.qty,
                    "bom": bom,
                    "has_bom": bool(bom)
                })
            
            return {
                "success": True,
                "sales_order": {
                    "name": doc.name,
                    "customer": doc.customer,
                    "items": items_with_bom,
                    "link": self.make_link("Sales Order", doc.name)
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def create_work_orders_from_sales_order(self, so_name: str, confirm: bool = False) -> Dict:
        """Create Work Orders for items with BOM"""
        details = self.get_sales_order_details(so_name)
        if not details["success"]:
            return details
        
        so = details["sales_order"]
        items_with_bom = [i for i in so["items"] if i["has_bom"]]
        
        if not items_with_bom:
            return {
                "success": False,
                "error": f"No items in Sales Order {so_name} have active BOMs"
            }
        
        if not confirm:
            return {
                "success": True,
                "requires_confirmation": True,
                "action": "create_work_orders",
                "preview": f"""
**Creating Work Orders from Sales Order {so_name}**

**Items with BOMs ({len(items_with_bom)}):**
""" + "\n".join([f"- {i['item_code']}: Qty {i['qty']}, BOM: {i['bom']}" for i in items_with_bom]) + """

⚠️ **Confirm?** Reply: `@ai confirm create work orders from """ + so_name + "`"
            }
        
        # Execute creation
        created_wos = []
        try:
            for item in items_with_bom:
                wo = frappe.get_doc({
                    "doctype": "Work Order",
                    "production_item": item["item_code"],
                    "bom_no": item["bom"],
                    "qty": item["qty"],
                    "sales_order": so_name,
                    "wip_warehouse": frappe.db.get_single_value("Manufacturing Settings", "default_wip_warehouse"),
                    "fg_warehouse": frappe.db.get_single_value("Manufacturing Settings", "default_fg_warehouse")
                })
                wo.insert()
                created_wos.append({
                    "name": wo.name,
                    "item": item["item_code"],
                    "qty": item["qty"],
                    "link": self.make_link("Work Order", wo.name)
                })
            
            frappe.db.commit()
            
            return {
                "success": True,
                "message": f"✅ Created {len(created_wos)} Work Order(s) from Sales Order {so_name}",
                "work_orders": created_wos
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== WORK ORDER STOCK ENTRY ==========
    def create_stock_entry_for_work_order(self, wo_name: str, purpose: str = "Material Transfer for Manufacture", confirm: bool = False) -> Dict:
        """Create Stock Entry for Work Order"""
        try:
            wo = frappe.get_doc("Work Order", wo_name)
            
            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "action": "create_stock_entry",
                    "preview": f"""
**Creating Stock Entry for Work Order {wo_name}**

| Field | Value |
|-------|-------|
| Purpose | {purpose} |
| Item | {wo.production_item} |
| Qty | {wo.qty} |
| BOM | {wo.bom_no} |

⚠️ **Confirm?** Reply: `@ai confirm stock entry for """ + wo_name + "`"
                }
            
            # Execute
            from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
            se = make_stock_entry(wo_name, purpose, wo.qty)
            se.insert()
            frappe.db.commit()
            
            return {
                "success": True,
                "message": f"✅ Stock Entry **{se.name}** created for Work Order {wo_name}",
                "stock_entry": {
                    "name": se.name,
                    "purpose": se.stock_entry_type,
                    "link": self.make_link("Stock Entry", se.name)
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== DELIVERY NOTE ==========
    def create_delivery_note_from_sales_order(self, so_name: str, confirm: bool = False) -> Dict:
        """Create Delivery Note from Sales Order"""
        try:
            so = frappe.get_doc("Sales Order", so_name)
            
            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "action": "create_delivery_note",
                    "preview": f"""
**Creating Delivery Note from Sales Order {so_name}**

| Field | Value |
|-------|-------|
| Customer | {so.customer} |
| Items | {len(so.items)} line(s) |
| Grand Total | {so.currency} {so.grand_total:,.2f} |

⚠️ **Confirm?** Reply: `@ai confirm delivery note from """ + so_name + "`"
                }
            
            from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
            dn = make_delivery_note(so_name)
            dn.insert()
            frappe.db.commit()
            
            return {
                "success": True,
                "message": f"✅ Delivery Note **{dn.name}** created from Sales Order {so_name}",
                "delivery_note": {
                    "name": dn.name,
                    "customer": dn.customer,
                    "link": self.make_link("Delivery Note", dn.name)
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== SALES INVOICE ==========
    def create_invoice_from_delivery_note(self, dn_name: str, confirm: bool = False) -> Dict:
        """Create Sales Invoice from Delivery Note"""
        try:
            dn = frappe.get_doc("Delivery Note", dn_name)
            
            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "action": "create_invoice",
                    "preview": f"""
**Creating Sales Invoice from Delivery Note {dn_name}**

| Field | Value |
|-------|-------|
| Customer | {dn.customer} |
| Items | {len(dn.items)} line(s) |
| Grand Total | {dn.currency} {dn.grand_total:,.2f} |

⚠️ **Confirm?** Reply: `@ai confirm invoice from """ + dn_name + "`"
                }
            
            from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
            si = make_sales_invoice(dn_name)
            si.insert()
            frappe.db.commit()
            
            return {
                "success": True,
                "message": f"✅ Sales Invoice **{si.name}** created from Delivery Note {dn_name}",
                "invoice": {
                    "name": si.name,
                    "customer": si.customer,
                    "grand_total": si.grand_total,
                    "link": self.make_link("Sales Invoice", si.name)
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== WORKFLOW STATUS ==========
    def get_workflow_status(self, quotation_name: str = None, so_name: str = None) -> Dict:
        """Get complete workflow status for a document chain"""
        result = {"success": True, "chain": []}
        
        try:
            if quotation_name:
                q = frappe.get_doc("Quotation", quotation_name)
                result["chain"].append({
                    "doctype": "Quotation",
                    "name": q.name,
                    "status": q.status,
                    "link": self.make_link("Quotation", q.name)
                })
                
                # Find linked Sales Orders
                sos = frappe.get_list("Sales Order Item", 
                    filters={"prevdoc_docname": quotation_name},
                    fields=["parent"],
                    distinct=True
                )
                for so in sos:
                    so_name = so.parent
            
            if so_name:
                so_doc = frappe.get_doc("Sales Order", so_name)
                result["chain"].append({
                    "doctype": "Sales Order",
                    "name": so_doc.name,
                    "status": so_doc.status,
                    "link": self.make_link("Sales Order", so_doc.name)
                })
                
                # Find Work Orders
                wos = frappe.get_list("Work Order",
                    filters={"sales_order": so_name},
                    fields=["name", "status", "production_item", "qty"]
                )
                for wo in wos:
                    result["chain"].append({
                        "doctype": "Work Order",
                        "name": wo.name,
                        "status": wo.status,
                        "item": wo.production_item,
                        "qty": wo.qty,
                        "link": self.make_link("Work Order", wo.name)
                    })
                
                # Find Delivery Notes
                dns = frappe.get_list("Delivery Note Item",
                    filters={"against_sales_order": so_name},
                    fields=["parent"],
                    distinct=True
                )
                for dn in dns:
                    dn_doc = frappe.get_doc("Delivery Note", dn.parent)
                    result["chain"].append({
                        "doctype": "Delivery Note",
                        "name": dn_doc.name,
                        "status": dn_doc.status,
                        "link": self.make_link("Delivery Note", dn_doc.name)
                    })
                
                # Find Invoices
                sis = frappe.get_list("Sales Invoice Item",
                    filters={"sales_order": so_name},
                    fields=["parent"],
                    distinct=True
                )
                for si in sis:
                    si_doc = frappe.get_doc("Sales Invoice", si.parent)
                    result["chain"].append({
                        "doctype": "Sales Invoice",
                        "name": si_doc.name,
                        "status": si_doc.status,
                        "link": self.make_link("Sales Invoice", si_doc.name)
                    })
            
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
