#!/usr/bin/env python3
"""
Debug script to run on sandbox bench console to understand the issue.
This script simulates what _ensure_customer_address_and_contact does
and shows exactly what's happening.
"""

import frappe

def debug_payment_submit(pe_name):
    print(f"\n{'='*70}")
    print(f"DEBUG: Payment Entry Submit Chain for {pe_name}")
    print(f"{'='*70}\n")
    
    pe = frappe.get_doc("Payment Entry", pe_name)
    
    # Step 1: Get customer
    customer_name = pe.party
    customer = frappe.get_doc("Customer", customer_name)
    
    print(f"1. CUSTOMER: {customer_name}")
    print(f"   customer_primary_address: {getattr(customer, 'customer_primary_address', 'NONE')}")
    print(f"   customer_primary_contact: {getattr(customer, 'customer_primary_contact', 'NONE')}")
    
    # Step 2: Check if we need to trace
    needs_address = not getattr(customer, 'customer_primary_address', None)
    needs_contact = not getattr(customer, 'customer_primary_contact', None)
    
    print(f"\n2. NEEDS TRACING?")
    print(f"   Address needed: {needs_address}")
    print(f"   Contact needed: {needs_contact}")
    
    # Step 3: Trace through PE -> SI -> SO chain
    if needs_address or needs_contact:
        print(f"\n3. TRACING PE -> SI -> SO chain:")
        
        for ref in pe.references:
            if ref.reference_doctype == "Sales Invoice":
                si_name = ref.reference_name
                si = frappe.get_doc("Sales Invoice", si_name)
                
                print(f"\n   📄 Sales Invoice: {si_name}")
                print(f"      SI.customer_address: {getattr(si, 'customer_address', 'NONE')}")
                print(f"      SI.shipping_address_name: {getattr(si, 'shipping_address_name', 'NONE')}")
                print(f"      SI.contact_person: {getattr(si, 'contact_person', 'NONE')}")
                
                for item in si.items:
                    so_name = getattr(item, 'sales_order', None)
                    if so_name:
                        so = frappe.get_doc("Sales Order", so_name)
                        print(f"\n      📋 Sales Order: {so_name}")
                        print(f"         SO.customer_address: {getattr(so, 'customer_address', 'NONE')}")
                        print(f"         SO.shipping_address_name: {getattr(so, 'shipping_address_name', 'NONE')}")
                        print(f"         SO.contact_person: {getattr(so, 'contact_person', 'NONE')}")
                        
                        # Try Quotation
                        for so_item in so.items:
                            qtn_name = getattr(so_item, 'prevdoc_docname', None)
                            if qtn_name:
                                try:
                                    qtn = frappe.get_doc("Quotation", qtn_name)
                                    print(f"\n         📋 Quotation: {qtn_name}")
                                    print(f"            QTN.customer_address: {getattr(qtn, 'customer_address', 'NONE')}")
                                    print(f"            QTN.contact_person: {getattr(qtn, 'contact_person', 'NONE')}")
                                except:
                                    pass
    
    # Step 4: Check PE state
    print(f"\n4. PAYMENT ENTRY STATE:")
    print(f"   party_address: {getattr(pe, 'party_address', 'NONE')}")
    print(f"   contact_person: {getattr(pe, 'contact_person', 'NONE')}")
    
    # Step 5: Try to fix and save
    print(f"\n5. ATTEMPTING FIX:")
    fixed = []
    
    if not getattr(customer, 'customer_primary_address', None):
        # Try to find from SI -> SO -> QTN chain
        for ref in pe.references:
            if ref.reference_doctype == "Sales Invoice":
                si = frappe.get_doc("Sales Invoice", ref.reference_name)
                
                # Try SO first
                for item in si.items:
                    so_name = getattr(item, 'sales_order', None)
                    if so_name:
                        so = frappe.get_doc("Sales Order", so_name)
                        if getattr(so, 'customer_address', None):
                            customer.customer_primary_address = so.customer_address
                            fixed.append(f"Set customer_primary_address from SO: {so.customer_address}")
                            break
                        elif getattr(so, 'shipping_address_name', None):
                            customer.customer_primary_address = so.shipping_address_name
                            fixed.append(f"Set customer_primary_address from SO shipping: {so.shipping_address_name}")
                            break
                
                # Fallback to SI
                if not getattr(customer, 'customer_primary_address', None):
                    if getattr(si, 'customer_address', None):
                        customer.customer_primary_address = si.customer_address
                        fixed.append(f"Set customer_primary_address from SI: {si.customer_address}")
                    elif getattr(si, 'shipping_address_name', None):
                        customer.customer_primary_address = si.shipping_address_name
                        fixed.append(f"Set customer_primary_address from SI shipping: {si.shipping_address_name}")
    
    if not getattr(customer, 'customer_primary_contact', None):
        for ref in pe.references:
            if ref.reference_doctype == "Sales Invoice":
                si = frappe.get_doc("Sales Invoice", ref.reference_name)
                for item in si.items:
                    so_name = getattr(item, 'sales_order', None)
                    if so_name:
                        so = frappe.get_doc("Sales Order", so_name)
                        if getattr(so, 'contact_person', None):
                            customer.customer_primary_contact = so.contact_person
                            fixed.append(f"Set customer_primary_contact from SO: {so.contact_person}")
                            break
                if not getattr(customer, 'customer_primary_contact', None):
                    if getattr(si, 'contact_person', None):
                        customer.customer_primary_contact = si.contact_person
                        fixed.append(f"Set customer_primary_contact from SI: {si.contact_person}")
    
    print(f"   Fixed items: {fixed}")
    
    if fixed:
        print(f"   Saving customer...")
        customer.save(ignore_permissions=True)
        frappe.db.commit()
        print(f"   ✓ Customer saved")
        
        # Now set on PE
        if not getattr(pe, 'party_address', None):
            if getattr(customer, 'customer_primary_address', None):
                pe.party_address = customer.customer_primary_address
                fixed.append(f"Set pe.party_address: {customer.customer_primary_address}")
        
        if not getattr(pe, 'contact_person', None):
            if getattr(customer, 'customer_primary_contact', None):
                pe.contact_person = customer.customer_primary_contact
                fixed.append(f"Set pe.contact_person: {customer.customer_primary_contact}")
        
        print(f"   Saving PE...")
        pe.save(ignore_permissions=True)
        frappe.db.commit()
        print(f"   ✓ PE saved")
        
        print(f"\n6. FINAL STATE:")
        print(f"   customer.customer_primary_address: {getattr(customer, 'customer_primary_address', 'NONE')}")
        print(f"   customer.customer_primary_contact: {getattr(customer, 'customer_primary_contact', 'NONE')}")
        print(f"   pe.party_address: {getattr(pe, 'party_address', 'NONE')}")
        print(f"   pe.contact_person: {getattr(pe, 'contact_person', 'NONE')}")
    
    print(f"\n7. ATTEMPTING SUBMIT...")
    try:
        pe.reload()
        pe.submit()
        frappe.db.commit()
        print(f"   ✓ SUBMIT SUCCESS!")
    except Exception as e:
        print(f"   ❌ SUBMIT FAILED: {e}")
    
    print(f"\n{'='*70}")

if __name__ == "__main__":
    import sys
    pe_name = sys.argv[1] if len(sys.argv) > 1 else "ACC-PAY-2026-00014"
    frappe.init(site="sandbox.sysmayal.cloud")
    frappe.connect()
    frappe.set_user("Administrator")
    debug_payment_submit(pe_name)