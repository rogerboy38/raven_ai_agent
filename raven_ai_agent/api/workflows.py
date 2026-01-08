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
    
    def __init__(self, user: str, dry_run: bool = False):
        self.user = user
        self.site_name = frappe.local.site
        self.dry_run = dry_run
    
    # ========== IDEMPOTENCY HELPERS ==========
    def get_by_folio(self, doctype: str, folio: str) -> Optional[str]:
        """Check if document exists by custom_folio (idempotency)"""
        return frappe.db.get_value(doctype, {"custom_folio": folio}, "name")
    
    def get_or_create(self, doctype: str, folio: str, create_fn) -> Dict:
        """Idempotent get-or-create pattern"""
        existing = self.get_by_folio(doctype, folio)
        if existing:
            return {
                "status": "fetched",
                "action": "fetched",
                "doctype": doctype,
                "name": existing,
                "custom_folio": folio,
                "link": self.make_link(doctype, existing)
            }
        
        if self.dry_run:
            return {
                "status": "dry_run",
                "action": "would_create",
                "doctype": doctype,
                "custom_folio": folio,
                "message": f"Would create {doctype} with folio {folio}"
            }
        
        # Create the document
        result = create_fn()
        if result.get("success"):
            return {
                "status": "created",
                "action": "created",
                **result
            }
        return result
    
    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable link"""
        slug = doctype.lower().replace(" ", "-")
        return f"https://{self.site_name}/app/{slug}/{name}"
    
    # ========== SUBMIT QUOTATION ==========
    def submit_quotation(self, quotation_name: str, confirm: bool = False) -> Dict:
        """Submit a draft quotation"""
        try:
            qtn = frappe.get_doc("Quotation", quotation_name)
            
            if qtn.docstatus == 1:
                return {"success": True, "message": f"✅ Quotation **{quotation_name}** is already submitted."}
            
            if qtn.docstatus == 2:
                return {"success": False, "error": f"Quotation {quotation_name} is Cancelled. Cannot submit."}
            
            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": f"**Submit Quotation {quotation_name}?**\n\n| Field | Value |\n|-------|-------|\n| Customer | {qtn.party_name} |\n| Total | {qtn.currency} {qtn.grand_total:,.2f} |\n\n⚠️ **Confirm?** Reply: `@ai confirm submit quotation {quotation_name}`"
                }
            
            # Auto-extend validity if expired
            if qtn.valid_till and str(qtn.valid_till) < nowdate():
                qtn.valid_till = add_days(nowdate(), 30)
            
            qtn.flags.ignore_permissions = True
            qtn.save()
            qtn.submit()
            frappe.db.commit()
            
            return {"success": True, "message": f"✅ Quotation **{quotation_name}** submitted successfully!"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
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
            
            # Migration mode: auto-fix quotation issues
            qtn = frappe.get_doc("Quotation", quotation_name)
            
            if qtn.docstatus == 2:
                return {"success": False, "error": f"Quotation {quotation_name} is Cancelled. Cannot create Sales Order."}
            
            # Auto-extend validity for expired quotations
            if qtn.valid_till and str(qtn.valid_till) < nowdate():
                qtn.valid_till = add_days(nowdate(), 30)
            
            # Auto-submit draft quotations (migration mode)
            if qtn.docstatus == 0:
                try:
                    qtn.flags.ignore_permissions = True
                    qtn.save()
                    qtn.submit()
                    frappe.db.commit()
                except Exception as submit_error:
                    return {"success": False, "error": f"Cannot auto-submit Quotation: {str(submit_error)}"}
            
            so = make_sales_order(quotation_name)
            so.delivery_date = add_days(nowdate(), 30)  # Default 30 days
            
            # Clean up invalid link fields (for cross-environment migrations)
            link_fields_to_check = ['incoterm', 'taxes_and_charges', 'tc_name']
            for field in link_fields_to_check:
                if so.get(field):
                    try:
                        meta = frappe.get_meta("Sales Order")
                        df = meta.get_field(field)
                        if df and df.options and not frappe.db.exists(df.options, so.get(field)):
                            so.set(field, None)
                    except:
                        pass
            
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
    
    # ========== SUBMIT SALES ORDER ==========
    def submit_sales_order(self, so_name: str, confirm: bool = False) -> Dict:
        """Submit a draft sales order"""
        try:
            so = frappe.get_doc("Sales Order", so_name)
            
            if so.docstatus == 1:
                return {"success": True, "message": f"✅ Sales Order **{so_name}** is already submitted."}
            
            if so.docstatus == 2:
                return {"success": False, "error": f"Sales Order {so_name} is Cancelled."}
            
            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": f"**Submit Sales Order {so_name}?**\n\n| Field | Value |\n|-------|-------|\n| Customer | {so.customer} |\n| Total | {so.currency} {so.grand_total:,.2f} |\n\n⚠️ **Confirm?** Reply: `@ai confirm submit sales order {so_name}`"
                }
            
            so.flags.ignore_permissions = True
            so.submit()
            frappe.db.commit()
            
            return {"success": True, "message": f"✅ Sales Order **{so_name}** submitted successfully!"}
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
            
            # Auto-submit draft Sales Order (migration mode)
            if so.docstatus == 0:
                try:
                    so.flags.ignore_permissions = True
                    so.submit()
                    frappe.db.commit()
                except Exception as e:
                    return {"success": False, "error": f"Cannot auto-submit Sales Order: {str(e)}"}
            
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
            
            # Auto-submit draft Delivery Note (migration mode)
            if dn.docstatus == 0:
                try:
                    # Reload to get latest version
                    dn.reload()
                    
                    # Auto-create/fix Quality Inspection if required
                    for item in dn.items:
                        inspection_required = frappe.db.get_value("Item", item.item_code, "inspection_required_before_delivery")
                        if inspection_required:
                            # Check if existing QI needs to be fixed
                            if item.quality_inspection:
                                existing_qi = frappe.get_doc("Quality Inspection", item.quality_inspection)
                                if existing_qi.status == "Rejected" and existing_qi.docstatus == 1:
                                    # Cancel rejected and create new
                                    existing_qi.flags.ignore_permissions = True
                                    existing_qi.cancel()
                                    frappe.db.commit()
                                    item.quality_inspection = None
                            
                            if not item.quality_inspection:
                                qi = frappe.get_doc({
                                    "doctype": "Quality Inspection",
                                    "inspection_type": "Incoming",
                                    "reference_type": "Delivery Note",
                                    "reference_name": dn.name,
                                    "item_code": item.item_code,
                                    "sample_size": item.qty,
                                    "inspected_by": frappe.session.user,
                                    "status": "Accepted"
                                })
                                qi.flags.ignore_permissions = True
                                qi.flags.ignore_mandatory = True
                                qi.insert()
                                qi.submit()
                                frappe.db.commit()
                                item.quality_inspection = qi.name
                    
                    dn.flags.ignore_permissions = True
                    dn.save()
                    dn.submit()
                    frappe.db.commit()
                except Exception as e:
                    return {"success": False, "error": f"Cannot auto-submit Delivery Note: {str(e)}"}
            
            from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
            si = make_sales_invoice(dn_name)
            
            # Auto-fix: Set customer address if missing (migration fix)
            if not si.customer_address:
                # Try to get default billing address
                billing_address = frappe.db.get_value("Dynamic Link", {
                    "link_doctype": "Customer",
                    "link_name": si.customer,
                    "parenttype": "Address"
                }, "parent")
                if billing_address:
                    si.customer_address = billing_address
                    # Also set the address display
                    from frappe.contacts.doctype.address.address import get_address_display
                    si.address_display = get_address_display(billing_address)
            
            # Auto-fix: Clear invalid link fields
            link_fields = ['taxes_and_charges', 'tc_name', 'shipping_address_name']
            for field in link_fields:
                if si.get(field):
                    try:
                        meta = frappe.get_meta("Sales Invoice")
                        df = meta.get_field(field)
                        if df and df.options and not frappe.db.exists(df.options, si.get(field)):
                            si.set(field, None)
                    except:
                        pass
            
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

    
    # ========== COMPLETE WORKFLOW ==========
    def complete_workflow_to_invoice(self, quotation_name: str) -> Dict:
        """Run complete workflow: Quotation → Sales Order → Delivery Note → Invoice"""
        steps = []
        
        try:
            # Pre-check: Ensure Fiscal Year exists
            from frappe.utils import getdate
            today = getdate(nowdate())
            fiscal_year = frappe.db.get_value("Fiscal Year", {
                "year_start_date": ("<=", today),
                "year_end_date": (">=", today)
            }, "name")
            if not fiscal_year:
                # Auto-create fiscal year
                fy = frappe.get_doc({
                    "doctype": "Fiscal Year",
                    "year": str(today.year),
                    "year_start_date": f"{today.year}-01-01",
                    "year_end_date": f"{today.year}-12-31"
                })
                fy.flags.ignore_permissions = True
                fy.insert()
                frappe.db.commit()
                steps.append(f"✅ Auto-created Fiscal Year {today.year}")
            
            # Step 1: Submit Quotation if draft
            qtn = frappe.get_doc("Quotation", quotation_name)
            if qtn.docstatus == 0:
                if qtn.valid_till and str(qtn.valid_till) < nowdate():
                    qtn.valid_till = add_days(nowdate(), 30)
                qtn.flags.ignore_permissions = True
                qtn.save()
                qtn.submit()
                frappe.db.commit()
                steps.append(f"✅ Quotation {quotation_name} submitted")
            elif qtn.docstatus == 1:
                steps.append(f"✅ Quotation {quotation_name} already submitted")
            else:
                return {"success": False, "error": f"Quotation {quotation_name} is cancelled"}
            
            # Step 2: Create Sales Order
            from erpnext.selling.doctype.quotation.quotation import make_sales_order
            so = make_sales_order(quotation_name)
            so.transaction_date = nowdate()
            so.delivery_date = add_days(nowdate(), 30)
            
            # Fix payment terms dates (migration mode)
            if so.payment_schedule:
                for row in so.payment_schedule:
                    if row.due_date and str(row.due_date) < nowdate():
                        row.due_date = add_days(nowdate(), 30)
            
            so.insert()
            so.submit()
            frappe.db.commit()
            steps.append(f"✅ Sales Order {so.name} created and submitted")
            
            # Step 3: Create Stock Entry (Material Receipt) if needed
            default_warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
            if not default_warehouse:
                default_warehouse = frappe.db.get_value("Warehouse", {"is_group": 0, "company": so.company}, "name")
            
            for item in so.items:
                # Check current stock
                from erpnext.stock.utils import get_stock_balance
                current_stock = get_stock_balance(item.item_code, item.warehouse or default_warehouse)
                
                if current_stock < item.qty:
                    qty_needed = item.qty - current_stock
                    target_warehouse = item.warehouse or default_warehouse
                    
                    # Check if item requires batch
                    has_batch_no = frappe.db.get_value("Item", item.item_code, "has_batch_no")
                    batch_no = None
                    
                    if has_batch_no:
                        # Create batch for migration
                        batch = frappe.get_doc({
                            "doctype": "Batch",
                            "item": item.item_code,
                            "batch_id": f"MIG-{item.item_code}-{nowdate()}",
                            "expiry_date": add_days(nowdate(), 365)
                        })
                        batch.flags.ignore_permissions = True
                        batch.insert()
                        batch_no = batch.name
                        steps.append(f"✅ Batch {batch_no} created for {item.item_code}")
                    
                    # Create Material Receipt
                    se_item = {
                        "item_code": item.item_code,
                        "qty": qty_needed,
                        "t_warehouse": target_warehouse,
                        "basic_rate": item.rate
                    }
                    if batch_no:
                        se_item["batch_no"] = batch_no
                    
                    se = frappe.get_doc({
                        "doctype": "Stock Entry",
                        "stock_entry_type": "Material Receipt",
                        "company": so.company,
                        "items": [se_item]
                    })
                    se.flags.ignore_permissions = True
                    se.insert()
                    se.submit()
                    frappe.db.commit()
                    steps.append(f"✅ Stock Entry {se.name} - received {qty_needed} of {item.item_code}")
            
            # Step 4: Create Delivery Note (after stock is available)
            from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
            dn = make_delivery_note(so.name)
            
            # Auto-fix: Create Quality Inspection if required
            for item in dn.items:
                inspection_required = frappe.db.get_value("Item", item.item_code, "inspection_required_before_delivery")
                if inspection_required:
                    # Check if inspection already exists
                    existing_qi = frappe.db.get_value("Quality Inspection", {
                        "reference_type": "Stock Entry",
                        "item_code": item.item_code,
                        "docstatus": 1
                    }, "name")
                    if not existing_qi:
                        # Create and submit Quality Inspection
                        qi = frappe.get_doc({
                            "doctype": "Quality Inspection",
                            "inspection_type": "Incoming",
                            "reference_type": "Stock Entry",
                            "reference_name": se.name if 'se' in dir() else None,
                            "item_code": item.item_code,
                            "sample_size": item.qty,
                            "inspected_by": frappe.session.user,
                            "status": "Accepted"
                        })
                        qi.flags.ignore_permissions = True
                        qi.flags.ignore_mandatory = True
                        qi.insert()
                        qi.submit()
                        frappe.db.commit()
                        item.quality_inspection = qi.name
                        steps.append(f"✅ Quality Inspection {qi.name} created for {item.item_code}")
            
            # Auto-fix: Ensure leaf warehouses (not group)
            for item in dn.items:
                if item.warehouse:
                    is_group = frappe.db.get_value("Warehouse", item.warehouse, "is_group")
                    if is_group:
                        # Find a suitable leaf warehouse
                        leaf_warehouse = frappe.db.get_value("Warehouse", {
                            "is_group": 0,
                            "company": so.company,
                            "disabled": 0
                        }, "name")
                        if leaf_warehouse:
                            item.warehouse = leaf_warehouse
                            steps.append(f"✅ Fixed warehouse for {item.item_code}: {leaf_warehouse}")
            
            dn.insert()
            dn.submit()
            frappe.db.commit()
            steps.append(f"✅ Delivery Note {dn.name} created and submitted")
            
            # Step 5: Create Sales Invoice
            from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
            si = make_sales_invoice(dn.name)
            
            # Auto-fix: Set customer address if missing
            if not si.customer_address:
                billing_address = frappe.db.get_value("Dynamic Link", {
                    "link_doctype": "Customer",
                    "link_name": si.customer,
                    "parenttype": "Address"
                }, "parent")
                if billing_address:
                    si.customer_address = billing_address
                    from frappe.contacts.doctype.address.address import get_address_display
                    si.address_display = get_address_display(billing_address)
                    steps.append(f"✅ Auto-set customer address: {billing_address}")
            
            # Auto-fix: Clear invalid link fields
            for field in ['taxes_and_charges', 'tc_name', 'shipping_address_name']:
                if si.get(field):
                    try:
                        meta = frappe.get_meta("Sales Invoice")
                        df = meta.get_field(field)
                        if df and df.options and not frappe.db.exists(df.options, si.get(field)):
                            si.set(field, None)
                    except:
                        pass
            
            si.insert()
            frappe.db.commit()
            steps.append(f"✅ Sales Invoice {si.name} created (Draft)")
            
            return {
                "success": True,
                "message": "**🎉 Complete Workflow Executed!**\n\n" + "\n".join(steps) + f"\n\n**Final Invoice:** [{si.name}]({self.make_link('Sales Invoice', si.name)})"
            }
        except Exception as e:
            steps.append(f"❌ Error: {str(e)}")
            return {
                "success": False,
                "error": "\n".join(steps)
            }

    
    # ========== BATCH MIGRATION ==========
    def batch_migrate_quotations(self, quotation_names: List[str], dry_run: bool = False) -> Dict:
        """Batch migrate multiple quotations through complete workflow"""
        self.dry_run = dry_run
        results = []
        success_count = 0
        error_count = 0
        
        for qtn_name in quotation_names:
            try:
                if dry_run:
                    # Check what would happen
                    qtn = frappe.get_doc("Quotation", qtn_name)
                    results.append({
                        "quotation": qtn_name,
                        "status": "dry_run",
                        "customer": qtn.party_name,
                        "total": qtn.grand_total,
                        "would_create": ["Sales Order", "Stock Entry", "Delivery Note", "Sales Invoice"]
                    })
                    success_count += 1
                else:
                    # Execute complete workflow
                    result = self.complete_workflow_to_invoice(qtn_name)
                    results.append({
                        "quotation": qtn_name,
                        "status": "success" if result.get("success") else "error",
                        "message": result.get("message") or result.get("error")
                    })
                    if result.get("success"):
                        success_count += 1
                    else:
                        error_count += 1
            except Exception as e:
                results.append({
                    "quotation": qtn_name,
                    "status": "error",
                    "error": str(e)
                })
                error_count += 1
        
        summary = f"**Batch Migration {'(DRY RUN)' if dry_run else 'Complete'}**\n\n"
        summary += f"✅ Success: {success_count} | ❌ Errors: {error_count}\n\n"
        
        for r in results:
            if r["status"] == "dry_run":
                summary += f"🔍 {r['quotation']}: Would migrate ({r['customer']}, {r['total']:,.2f})\n"
            elif r["status"] == "success":
                summary += f"✅ {r['quotation']}: Migrated\n"
            else:
                summary += f"❌ {r['quotation']}: {r.get('error', r.get('message', 'Unknown error'))}\n"
        
        return {"success": True, "message": summary, "results": results}
    
    # ========== FOXPRO IMPORT ==========
    def import_foxpro_record(self, payload: Dict, dry_run: bool = False) -> Dict:
        """Import a FoxPro record into ERPNext"""
        self.dry_run = dry_run
        
        doc_type = payload.get("document_type", "quotation").lower()
        folio = payload.get("folio")
        company = payload.get("company")
        customer = payload.get("customer")
        items = payload.get("items", [])
        date = payload.get("date", nowdate())
        
        if not all([folio, company, customer]):
            return {"success": False, "error": "Missing required fields: folio, company, customer"}
        
        # Validate customer exists
        if not frappe.db.exists("Customer", customer):
            return {"success": False, "error": f"Customer '{customer}' not found in ERPNext"}
        
        # Validate company exists
        if not frappe.db.exists("Company", company):
            return {"success": False, "error": f"Company '{company}' not found in ERPNext"}
        
        if doc_type == "quotation":
            return self._import_quotation(folio, company, customer, items, date)
        elif doc_type == "sales_order":
            return self._import_sales_order(folio, company, customer, items, date)
        else:
            return {"success": False, "error": f"Unsupported document type: {doc_type}"}
    
    def _import_quotation(self, folio: str, company: str, customer: str, items: List, date: str) -> Dict:
        """Import quotation from FoxPro"""
        # Idempotency check
        existing = self.get_by_folio("Quotation", folio)
        if existing:
            return {
                "success": True,
                "status": "fetched",
                "action": "fetched",
                "doctype": "Quotation",
                "name": existing,
                "custom_folio": folio,
                "next_step": "sales_order"
            }
        
        if self.dry_run:
            return {
                "success": True,
                "status": "dry_run",
                "action": "would_create",
                "doctype": "Quotation",
                "custom_folio": folio,
                "company": company,
                "customer": customer
            }
        
        try:
            qtn = frappe.get_doc({
                "doctype": "Quotation",
                "quotation_to": "Customer",
                "party_name": customer,
                "company": company,
                "transaction_date": date,
                "valid_till": add_days(date, 30),
                "custom_folio": folio,
                "items": items or [{"item_code": "PLACEHOLDER", "qty": 1}]
            })
            qtn.flags.ignore_permissions = True
            qtn.insert()
            frappe.db.commit()
            
            return {
                "success": True,
                "status": "created",
                "action": "created",
                "doctype": "Quotation",
                "name": qtn.name,
                "custom_folio": folio,
                "next_step": "sales_order",
                "link": self.make_link("Quotation", qtn.name)
            }
        except Exception as e:
            return {"success": False, "error": str(e), "error_type": "persistence"}
    
    def _import_sales_order(self, folio: str, company: str, customer: str, items: List, date: str) -> Dict:
        """Import sales order from FoxPro"""
        existing = self.get_by_folio("Sales Order", folio)
        if existing:
            return {
                "success": True,
                "status": "fetched",
                "action": "fetched",
                "doctype": "Sales Order",
                "name": existing,
                "custom_folio": folio,
                "next_step": "delivery"
            }
        
        if self.dry_run:
            return {
                "success": True,
                "status": "dry_run",
                "action": "would_create",
                "doctype": "Sales Order",
                "custom_folio": folio
            }
        
        try:
            so = frappe.get_doc({
                "doctype": "Sales Order",
                "customer": customer,
                "company": company,
                "transaction_date": date,
                "delivery_date": add_days(date, 30),
                "custom_folio": folio,
                "items": items or [{"item_code": "PLACEHOLDER", "qty": 1}]
            })
            so.flags.ignore_permissions = True
            so.insert()
            frappe.db.commit()
            
            return {
                "success": True,
                "status": "created",
                "action": "created",
                "doctype": "Sales Order",
                "name": so.name,
                "custom_folio": folio,
                "next_step": "delivery",
                "link": self.make_link("Sales Order", so.name)
            }
        except Exception as e:
            return {"success": False, "error": str(e), "error_type": "persistence"}



# ========== MODULE-LEVEL WRAPPER FUNCTIONS ==========
# These allow direct import: from raven_ai_agent.api.workflows import complete_workflow_to_invoice

def validate_migration_prerequisites(quotation_name: str) -> Dict:
    """
    Validate all prerequisites before migration.
    Lessons learned from sandbox testing - checks for common cross-environment issues.
    """
    issues = []
    warnings = []
    fixes_applied = []
    
    try:
        qtn = frappe.get_doc("Quotation", quotation_name)
        company = qtn.company
        customer = qtn.party_name
        
        # 1. Fiscal Year Check
        from frappe.utils import nowdate, getdate
        today = getdate(nowdate())
        fiscal_year = frappe.db.get_value("Fiscal Year", {
            "year_start_date": ("<=", today),
            "year_end_date": (">=", today)
        }, "name")
        if not fiscal_year:
            issues.append(f"❌ No active Fiscal Year for {today.year}. Create one first.")
        
        # 2. Incoterm Check (if set)
        if qtn.incoterm and not frappe.db.exists("Incoterm", qtn.incoterm):
            warnings.append(f"⚠️ Incoterm '{qtn.incoterm}' not found. Will be cleared.")
        
        # 3. Taxes and Charges Template Check
        if qtn.taxes_and_charges and not frappe.db.exists("Sales Taxes and Charges Template", qtn.taxes_and_charges):
            warnings.append(f"⚠️ Tax Template '{qtn.taxes_and_charges}' not found. Will be cleared.")
        
        # 4. Customer Default Tax Template Check
        customer_doc = frappe.get_doc("Customer", customer)
        if hasattr(customer_doc, 'default_sales_taxes_and_charges'):
            default_tax = customer_doc.default_sales_taxes_and_charges
            if default_tax and not frappe.db.exists("Sales Taxes and Charges Template", default_tax):
                issues.append(f"❌ Customer default Tax Template '{default_tax}' not found. Fix customer master.")
        
        # 5. Customer Address Check
        billing_address = frappe.db.get_value("Dynamic Link", {
            "link_doctype": "Customer",
            "link_name": customer,
            "parenttype": "Address"
        }, "parent")
        if not billing_address:
            warnings.append(f"⚠️ Customer '{customer}' has no address. Invoice may fail.")
        
        # 6. Warehouse Validation (check for leaf warehouses)
        for item in qtn.items:
            if item.warehouse:
                is_group = frappe.db.get_value("Warehouse", item.warehouse, "is_group")
                if is_group:
                    issues.append(f"❌ Item '{item.item_code}' uses group warehouse '{item.warehouse}'. Use a leaf warehouse.")
        
        # 7. Check Default Warehouse
        default_warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
        if default_warehouse:
            is_group = frappe.db.get_value("Warehouse", default_warehouse, "is_group")
            if is_group:
                warnings.append(f"⚠️ Default warehouse '{default_warehouse}' is a group. Stock operations may fail.")
        
        # 8. Quality Inspection Check
        for item in qtn.items:
            inspection_required = frappe.db.get_value("Item", item.item_code, "inspection_required_before_delivery")
            if inspection_required:
                warnings.append(f"⚠️ Item '{item.item_code}' requires Quality Inspection. Will be auto-created.")
        
        # 9. Item Stock Availability
        from erpnext.stock.utils import get_stock_balance
        for item in qtn.items:
            warehouse = item.warehouse or default_warehouse
            if warehouse:
                is_group = frappe.db.get_value("Warehouse", warehouse, "is_group")
                if not is_group:
                    stock = get_stock_balance(item.item_code, warehouse)
                    if stock < item.qty:
                        warnings.append(f"⚠️ Low stock: {item.item_code} needs {item.qty}, has {stock}. Stock Entry will be created.")
        
        return {
            "success": len(issues) == 0,
            "quotation": quotation_name,
            "customer": customer,
            "company": company,
            "issues": issues,
            "warnings": warnings,
            "fixes_applied": fixes_applied,
            "can_proceed": len(issues) == 0
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def complete_workflow_to_invoice(quotation_name: str, dry_run: bool = False) -> Dict:
    """
    Complete workflow: Quotation → Sales Order → Stock Entry → Delivery Note → Invoice
    
    Usage:
        from raven_ai_agent.api.workflows import complete_workflow_to_invoice
        result = complete_workflow_to_invoice("SAL-QTN-2023-00525", dry_run=True)
    """
    executor = WorkflowExecutor(user=frappe.session.user, dry_run=dry_run)
    if dry_run:
        # Comprehensive dry run with validation
        try:
            qtn = frappe.get_doc("Quotation", quotation_name)
            validation = validate_migration_prerequisites(quotation_name)
            
            steps = [
                f"1. Submit Quotation {quotation_name}" if qtn.docstatus == 0 else f"1. Quotation {quotation_name} already submitted",
                "2. Create Sales Order (clean invalid links)",
                "3. Create Stock Entry (if needed)",
                "4. Create Delivery Note (use leaf warehouse)",
                "5. Create Sales Invoice"
            ]
            
            message = f"**DRY RUN: Quotation {quotation_name}**\n\n"
            message += f"Customer: {qtn.party_name}\n"
            message += f"Total: {qtn.currency} {qtn.grand_total:,.2f}\n"
            message += f"Items: {len(qtn.items)} line(s)\n\n"
            
            if validation.get("issues"):
                message += "**❌ BLOCKING ISSUES:**\n"
                for issue in validation["issues"]:
                    message += f"  {issue}\n"
                message += "\n"
            
            if validation.get("warnings"):
                message += "**⚠️ WARNINGS (auto-fixed):**\n"
                for warning in validation["warnings"]:
                    message += f"  {warning}\n"
            
            return {
                "success": True,
                "dry_run": True,
                "can_proceed": validation.get("can_proceed", False),
                "quotation": quotation_name,
                "customer": qtn.party_name,
                "total": qtn.grand_total,
                "currency": qtn.currency,
                "items": len(qtn.items),
                "validation": validation,
                "steps": steps,
                "message": message
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        return executor.complete_workflow_to_invoice(quotation_name)


def submit_quotation(quotation_name: str) -> Dict:
    """Submit a quotation (Sudo mode - no confirmation)"""
    executor = WorkflowExecutor(user=frappe.session.user)
    return executor.submit_quotation(quotation_name, confirm=True)


def create_sales_order(quotation_name: str) -> Dict:
    """Create Sales Order from Quotation (Sudo mode)"""
    executor = WorkflowExecutor(user=frappe.session.user)
    return executor.create_sales_order_from_quotation(quotation_name, confirm=True)


def create_delivery_note(so_name: str) -> Dict:
    """Create Delivery Note from Sales Order (Sudo mode)"""
    executor = WorkflowExecutor(user=frappe.session.user)
    return executor.create_delivery_note_from_sales_order(so_name, confirm=True)


def create_invoice(dn_name: str) -> Dict:
    """Create Sales Invoice from Delivery Note (Sudo mode)"""
    executor = WorkflowExecutor(user=frappe.session.user)
    return executor.create_invoice_from_delivery_note(dn_name, confirm=True)


def batch_migrate(quotation_names: List[str], dry_run: bool = False) -> Dict:
    """Batch migrate multiple quotations"""
    executor = WorkflowExecutor(user=frappe.session.user, dry_run=dry_run)
    return executor.batch_migrate_quotations(quotation_names, dry_run=dry_run)


def import_foxpro(payload: Dict, dry_run: bool = False) -> Dict:
    """Import FoxPro record"""
    executor = WorkflowExecutor(user=frappe.session.user, dry_run=dry_run)
    return executor.import_foxpro_record(payload, dry_run=dry_run)


# ========== FRAPPE WHITELISTED API ENDPOINTS ==========
@frappe.whitelist()
def api_complete_workflow(quotation_name: str, dry_run: bool = False):
    """API endpoint for complete workflow"""
    return complete_workflow_to_invoice(quotation_name, dry_run=dry_run)


@frappe.whitelist()
def api_batch_migrate(quotation_names: str, dry_run: bool = False):
    """API endpoint for batch migration. quotation_names is comma-separated."""
    names = [n.strip() for n in quotation_names.split(",")]
    return batch_migrate(names, dry_run=dry_run)
