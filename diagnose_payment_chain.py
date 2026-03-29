#!/usr/bin/env python3
"""
Diagnostic script to trace Payment Entry -> Sales Invoice -> Sales Order chain
to understand why customer address isn't being found.
"""

import frappe

def diagnose_payment_entry_chain(pe_name):
    print(f"\n{'='*60}")
    print(f"DIAGNOSTIC: Tracing Payment Entry chain for {pe_name}")
    print(f"{'='*60}\n")
    
    try:
        # 1. Get Payment Entry
        pe = frappe.get_doc("Payment Entry", pe_name)
        print(f"📋 Payment Entry: {pe.name}")
        print(f"   Party: {pe.party}")
        print(f"   Party Name: {pe.party_name}")
        print(f"   party_address: {getattr(pe, 'party_address', 'NOT SET')}")
        print(f"   contact_person: {getattr(pe, 'contact_person', 'NOT SET')}")
        print()
        
        # 2. Get Customer and check primary address
        customer = frappe.get_doc("Customer", pe.party)
        print(f"👤 Customer: {customer.name}")
        print(f"   customer_primary_address: {getattr(customer, 'customer_primary_address', 'NOT SET')}")
        print(f"   customer_primary_contact: {getattr(customer, 'customer_primary_contact', 'NOT SET')}")
        print()
        
        if customer.customer_primary_address:
            addr = frappe.get_doc("Address", customer.customer_primary_address)
            print(f"   Address: {addr.name}")
            print(f"   Address Line 1: {getattr(addr, 'address_line1', 'N/A')}")
            print(f"   City: {getattr(addr, 'city', 'N/A')}")
            print(f"   Country: {getattr(addr, 'country', 'N/A')}")
            print(f"   Pincode: {getattr(addr, 'pincode', 'N/A')}")
        print()
        
        # 3. Get References from PE
        print(f"📄 Payment References ({len(pe.references)} items):")
        for ref in pe.references:
            print(f"   - {ref.reference_doctype}: {ref.reference_name}")
            print(f"     Allocated: {ref.allocated_amount}")
            
            if ref.reference_doctype == "Sales Invoice":
                si = frappe.get_doc("Sales Invoice", ref.reference_name)
                print(f"\n   📋 Sales Invoice: {si.name}")
                print(f"      Customer: {si.customer}")
                print(f"      customer_address: {getattr(si, 'customer_address', 'NOT SET')}")
                print(f"      shipping_address_name: {getattr(si, 'shipping_address_name', 'NOT SET')}")
                print(f"      contact_person: {getattr(si, 'contact_person', 'NOT SET')}")
                print()
                
                # 4. Check SI Items for Sales Order
                print(f"   📦 Sales Invoice Items ({len(si.items)} items):")
                for idx, item in enumerate(si.items):
                    so_name = getattr(item, 'sales_order', None)
                    print(f"      Item {idx+1}: {item.item_code}")
                    print(f"           sales_order: {so_name or 'NOT SET'}")
                    print(f"           prevdoc_docname: {getattr(item, 'prevdoc_docname', 'NOT SET')}")
                    
                    if so_name:
                        # 5. Get Sales Order
                        so = frappe.get_doc("Sales Order", so_name)
                        print(f"\n      📋 Sales Order: {so.name}")
                        print(f"         customer_address: {getattr(so, 'customer_address', 'NOT SET')}")
                        print(f"         shipping_address_name: {getattr(so, 'shipping_address_name', 'NOT SET')}")
                        print(f"         contact_person: {getattr(so, 'contact_person', 'NOT SET')}")
                        print()
                        
                        # 6. Check SO Items for Quotation
                        print(f"      📄 Sales Order Items ({len(so.items)} items):")
                        for so_idx, so_item in enumerate(so.items):
                            qtn_name = getattr(so_item, 'prevdoc_docname', None)
                            print(f"         SO Item {so_idx+1}: {so_item.item_code}")
                            print(f"            prevdoc_docname: {qtn_name or 'NOT SET'}")
                            
                            if qtn_name:
                                try:
                                    qtn = frappe.get_doc("Quotation", qtn_name)
                                    print(f"\n         📋 Quotation: {qtn.name}")
                                    print(f"            customer_address: {getattr(qtn, 'customer_address', 'NOT SET')}")
                                    print(f"            contact_person: {getattr(qtn, 'contact_person', 'NOT SET')}")
                                except Exception as e:
                                    print(f"         ⚠️ Quotation {qtn_name} not found: {e}")
                        print()
                print()
        
        print(f"\n{'='*60}")
        print("SUMMARY: What should happen in _ensure_customer_address_and_contact")
        print(f"{'='*60}")
        print("""
The function should:
1. Check if customer.customer_primary_address is set
   - If NOT set, trace to find it from PE -> SI -> SO -> QTN chain
2. Check if customer.customer_primary_contact is set
   - If NOT set, trace to find it from PE -> SI -> SO -> QTN chain
3. Set customer.customer_primary_address if found
4. Set customer.customer_primary_contact if found
5. Save customer
6. Set pe.party_address and pe.contact_person
7. Save pe
        """)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    pe_name = sys.argv[1] if len(sys.argv) > 1 else "ACC-PAY-2026-00014"
    frappe.init(site="sandbox.sysmayal.cloud")
    frappe.connect()
    diagnose_payment_entry_chain(pe_name)