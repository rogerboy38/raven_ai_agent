"""
Quotation Management - Fix + Update + TDS
"""
import frappe
import json
import re
import requests
from typing import Optional, Dict, List


class QuotationMixin:
    """Mixin for _handle_quotation_commands"""

    def _handle_quotation_commands(self, query: str, query_lower: str) -> Optional[Dict]:
        """Dispatched from execute_workflow_command"""
        # ==================== FIX QUOTATION (Cancelled → Draft) ====================
        
        # Fix quotation range: @ai !fix quotation from SAL-QTN-2024-00752 to SAL-QTN-2024-00760
        if "fix" in query_lower and "quotation" in query_lower and "from" in query_lower and "to" in query_lower:
            range_match = re.search(r'from\s+(SAL-QTN-(\d+)-(\d+))\s+to\s+(SAL-QTN-(\d+)-(\d+))', query, re.IGNORECASE)
            if range_match:
                start_name = range_match.group(1).upper()
                start_year = range_match.group(2)
                start_num = int(range_match.group(3))
                end_name = range_match.group(4).upper()
                end_year = range_match.group(5)
                end_num = int(range_match.group(6))
                
                # Validate same year
                if start_year != end_year:
                    return {"success": False, "error": "Range must be within the same year."}
                
                if start_num > end_num:
                    return {"success": False, "error": f"Invalid range: start ({start_num}) > end ({end_num})"}
                
                if end_num - start_num > 50:
                    return {"success": False, "error": "Range too large (max 50 quotations at once)."}
                
                site_name = frappe.local.site
                fixed = []
                skipped = []
                errors = []
                
                for num in range(start_num, end_num + 1):
                    qtn_name = f"SAL-QTN-{start_year}-{num:05d}"
                    try:
                        qtn = frappe.get_doc("Quotation", qtn_name)
                        if qtn.docstatus == 2:  # Cancelled
                            frappe.db.sql("""
                                UPDATE `tabQuotation` 
                                SET docstatus = 0, status = 'Draft'
                                WHERE name = %s
                            """, qtn_name)
                            frappe.db.sql("UPDATE `tabQuotation Item` SET docstatus = 0 WHERE parent = %s", qtn_name)
                            fixed.append(f"[{qtn_name}](https://{site_name}/app/quotation/{qtn_name})")
                        elif qtn.docstatus == 0:
                            skipped.append(f"{qtn_name} (already Draft)")
                        elif qtn.docstatus == 1:
                            skipped.append(f"{qtn_name} (Submitted)")
                    except frappe.DoesNotExistError:
                        errors.append(f"{qtn_name} (not found)")
                    except Exception as e:
                        errors.append(f"{qtn_name} ({str(e)[:30]})")
                
                frappe.db.commit()
                
                msg = f"🔧 **BATCH FIX QUOTATIONS** ({start_name} → {end_name})\n\n"
                if fixed:
                    msg += f"✅ **Fixed ({len(fixed)}):**\n" + "\n".join([f"  • {q}" for q in fixed]) + "\n\n"
                if skipped:
                    msg += f"⏭️ **Skipped ({len(skipped)}):**\n" + "\n".join([f"  • {q}" for q in skipped]) + "\n\n"
                if errors:
                    msg += f"❌ **Errors ({len(errors)}):**\n" + "\n".join([f"  • {q}" for q in errors])
                
                return {"success": True, "message": msg}
        
        # Fix single quotation: @ai fix quotation SAL-QTN-XXXX or @ai !fix quotation SAL-QTN-XXXX
        if "fix" in query_lower and "quotation" in query_lower:
            qtn_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
            if qtn_match:
                qtn_name = qtn_match.group(1).upper()
                try:
                    qtn = frappe.get_doc("Quotation", qtn_name)
                    site_name = frappe.local.site
                    qtn_link = f"https://{site_name}/app/quotation/{qtn_name}"
                    
                    # Case 1: Quotation is cancelled - revert to draft
                    if qtn.docstatus == 2:
                        if not is_confirm:
                            return {
                                "requires_confirmation": True,
                                "preview": f"🔧 **FIX QUOTATION {qtn_name}?**\n\n  Customer: {qtn.party_name}\n  Status: Cancelled (docstatus=2)\n  Total: ${qtn.grand_total:,.2f}\n\nThis will reset the quotation to Draft so you can modify it.\n\n⚠️ Use `@ai !fix quotation {qtn_name}` or say 'confirm' to proceed."
                            }
                        
                        # Reset quotation to draft via SQL
                        frappe.db.sql("""
                            UPDATE `tabQuotation` 
                            SET docstatus = 0, status = 'Draft'
                            WHERE name = %s
                        """, qtn_name)
                        
                        # Reset child tables
                        frappe.db.sql("UPDATE `tabQuotation Item` SET docstatus = 0 WHERE parent = %s", qtn_name)
                        
                        frappe.db.commit()
                        
                        return {
                            "success": True,
                            "message": f"✅ Quotation **[{qtn_name}]({qtn_link})** fixed!\n\n  Customer: {qtn.party_name}\n  Status: Draft (docstatus=0)\n  Total: ${qtn.grand_total:,.2f}\n\n📝 You can now edit the quotation in ERPNext."
                        }
                    
                    # Case 2: Already in draft
                    elif qtn.docstatus == 0:
                        return {
                            "success": True,
                            "message": f"✅ Quotation **[{qtn_name}]({qtn_link})** is already in Draft status.\n\n  Customer: {qtn.party_name}\n  Status: {qtn.status}"
                        }
                    
                    # Case 3: Submitted - needs to be cancelled first
                    elif qtn.docstatus == 1:
                        return {
                            "success": False,
                            "error": f"Quotation **[{qtn_name}]({qtn_link})** is Submitted.\n\nTo fix it:\n1. Cancel it first in ERPNext\n2. Then run `@ai !fix quotation {qtn_name}`"
                        }
                    
                except frappe.DoesNotExistError:
                    return {"success": False, "error": f"Quotation **{qtn_name}** not found."}
                except Exception as e:
                    return {"success": False, "error": f"Failed to fix quotation: {str(e)}"}
        
        # ==================== END FIX QUOTATION ====================
        
        # ==================== UPDATE QUOTATION ITEM & TDS ====================
        
        # Template items mapping to their variants
        TEMPLATE_VARIANTS = {
            "0323": "0323 INNOVALOE ALOE VERA GEL SPRAY DRIED POWDER 200:1 ORGANIC-ORGC-Aloin NMT 0.1 PPM (0.5% ST)-100/50",
            "0310": "0310-NLT 10% PS",
            "0803": "0803- KOSHER-ORGANIC-LAS3-HADS NMT 2 PPM-ACM 15/20",
            "0335": "0335-BTW 8-10%-NMT 1 PPM",
        }
        
        # Update quotation item: @ai !update quotation SAL-QTN-XXXX item ITEM-CODE [customer CUSTOMER]
        if ("update" in query_lower and "quotation" in query_lower and "item" in query_lower) or \
           ("actualizar" in query_lower and "cotizacion" in query_lower):
            qtn_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
            item_match = re.search(r'item\s+(\S+)', query, re.IGNORECASE)
            customer_match = re.search(r'customer\s+(.+?)(?:\s*$)', query, re.IGNORECASE)
            
            frappe.logger().info(f"[AI Agent] Update quotation: qtn_match={qtn_match}, item_match={item_match}")
            
            if qtn_match and item_match:
                qtn_name = qtn_match.group(1).upper()
                new_item_code = item_match.group(1).strip()
                customer_override = customer_match.group(1).strip() if customer_match else None
                
                try:
                    # Check if item is a template - use variant instead
                    if new_item_code in TEMPLATE_VARIANTS:
                        new_item_code = TEMPLATE_VARIANTS[new_item_code]
                    
                    # Verify item exists
                    if not frappe.db.exists("Item", new_item_code):
                        return {"success": False, "error": f"Item **{new_item_code}** not found."}
                    
                    # Get quotation
                    qtn = frappe.get_doc("Quotation", qtn_name)
                    site_name = frappe.local.site
                    qtn_link = f"https://{site_name}/app/quotation/{qtn_name}"
                    
                    # Must be in draft
                    if qtn.docstatus != 0:
                        return {"success": False, "error": f"Quotation **{qtn_name}** must be in Draft. Use `@ai !fix quotation {qtn_name}` first."}
                    
                    # Get customer name for TDS lookup
                    customer_name = customer_override or qtn.party_name or ""
                    customer_keyword = customer_name.split()[0].upper() if customer_name else ""
                    
                    # Get new item details
                    new_item = frappe.get_doc("Item", new_item_code)
                    
                    # TDS Lookup Logic (priority: customer-specific > item > parent TDS MASTER)
                    tds_name = None
                    
                    # Get base item code (first 4 chars like "0334")
                    base_item_code = new_item_code.split("-")[0].split()[0][:4] if new_item_code else ""
                    
                    # 1. Try customer-specific TDS using LIKE search
                    if customer_keyword and base_item_code:
                        tds_list = frappe.db.sql("""
                            SELECT name FROM `tabTDS Product Specification`
                            WHERE name LIKE %s
                            ORDER BY name
                        """, (f"{base_item_code}%",), as_dict=True)
                        
                        for t in tds_list:
                            if customer_keyword in t.name.upper():
                                tds_name = t.name
                                break
                    
                    # 2. Try exact item TDS
                    if not tds_name and base_item_code:
                        if frappe.db.exists("TDS Product Specification", base_item_code):
                            tds_name = base_item_code
                    
                    # 3. Try parent TDS MASTER
                    if not tds_name and len(base_item_code) >= 2:
                        parent_code = base_item_code[:2] + "00"
                        tds_master = f"{parent_code} TDS MASTER"
                        if frappe.db.exists("TDS Product Specification", tds_master):
                            tds_name = tds_master
                    
                    if not is_confirm:
                        preview = f"📝 **UPDATE QUOTATION ITEM?**\n\n"
                        preview += f"  Quotation: [{qtn_name}]({qtn_link})\n"
                        preview += f"  Customer: {customer_name}\n\n"
                        preview += f"  **Current Item(s):** {', '.join([f'{i.item_code} (qty:{i.qty}, rate:{i.rate})' for i in qtn.items])}\n"
                        preview += f"  **New Item:** {new_item_code}\n"
                        preview += f"  **TDS:** {tds_name or '⚠️ Not found'}\n\n"
                        preview += f"Use `@ai !update quotation {qtn_name} item {new_item_code}` to proceed."
                        return {"requires_confirmation": True, "preview": preview}
                    
                    # Update items - ONLY change item_code, item_name, and TDS
                    # PRESERVE: qty, rate, amount, uom, and all other fields
                    for item in qtn.items:
                        item.item_code = new_item_code
                        item.item_name = new_item.item_name
                        # Set TDS if field exists (can be None to clear it)
                        if hasattr(item, 'custom_tds_amb'):
                            item.custom_tds_amb = tds_name
                    
                    # Also update quotation-level TDS AMB if it exists
                    if hasattr(qtn, 'custom_tds_amb'):
                        qtn.custom_tds_amb = tds_name
                    
                    qtn.flags.ignore_validate = True
                    qtn.save()
                    frappe.db.commit()
                    
                    return {
                        "success": True,
                        "message": f"✅ Quotation **[{qtn_name}]({qtn_link})** updated!\n\n  Item: {new_item_code}\n  TDS: {tds_name or 'Not set'}\n  Customer: {customer_name}"
                    }
                    
                except frappe.DoesNotExistError:
                    return {"success": False, "error": f"Quotation **{qtn_name}** not found."}
                except Exception as e:
                    frappe.db.rollback()
                    return {"success": False, "error": f"Failed to update quotation: {str(e)}"}
            else:
                # Pattern didn't match - provide usage help
                return {
                    "success": False,
                    "error": "**Usage:** `@ai !update quotation SAL-QTN-YYYY-NNNNN item ITEM-CODE`\n\nExample: `@ai !update quotation SAL-QTN-2024-00753 item 0307`"
                }
        
        # ==================== END UPDATE QUOTATION ITEM & TDS ====================
        
        # Create Supplier from research: @ai create supplier [name]
        if "create supplier" in query_lower or "crear proveedor" in query_lower:
            # Extract supplier name from query (remove suffixes)
            name_match = re.search(r'(?:create supplier|crear proveedor)\s+["\']?(.+?)["\']?\s*$', query, re.IGNORECASE)
            if name_match:
                supplier_name = name_match.group(1).strip()
                # Clean up trailing keywords
                for suffix in [" if exist update", " if exists update", " si existe actualizar", 
                              " with address", " con direccion", " with", " con", " update"]:
                    if supplier_name.lower().endswith(suffix):
                        supplier_name = supplier_name[:-len(suffix)].strip()
                
                # Check for update mode
                update_if_exists = any(kw in query_lower for kw in ["if exist", "if exists", "update", "actualizar"])
                
                try:
                    # Check if supplier already exists
                    existing_supplier = frappe.db.get_value("Supplier", {"supplier_name": supplier_name}, "name")
                    
                    if existing_supplier and not update_if_exists:
                        return {
                            "success": False,
                            "error": f"Supplier '{supplier_name}' already exists. Add 'if exist update' to update it."
                        }
                    
                    # Search for company address info
                    address_info = {}
                    search_with_address = "with address" in query_lower or "con direccion" in query_lower
                    
                    if search_with_address:
                        frappe.logger().info(f"[AI Agent] Searching address for: {supplier_name}")
                        search_result = self.duckduckgo_search(f"{supplier_name} address contact location direccion")
                        
                        # Try to parse address components from search results
                        if search_result and "No search results" not in search_result:
                            # Extract phone numbers
                            phone_match = re.search(r'[\+]?[\d\s\-\(\)]{10,}', search_result)
                            if phone_match:
                                address_info['phone'] = phone_match.group(0).strip()
                            
                            # Extract email
                            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', search_result)
                            if email_match:
                                address_info['email'] = email_match.group(0)
                            
                            # Extract postal code (Mexican 5 digits, or other formats)
                            postal_match = re.search(r'\b(\d{5})\b', search_result)
                            if postal_match:
                                address_info['pincode'] = postal_match.group(1)
                            
                            # Try to extract street address (common patterns)
                            street_patterns = [
                                r'((?:Calle|Av\.|Ave\.|Avenida|Carretera|Carr\.|Blvd\.|Boulevard|Via|C/)[^\n,]{5,50})',
                                r'((?:No\.|Num\.|#)\s*\d+[^\n,]{0,30})',
                                r'(\d+\s+[A-Z][a-z]+\s+(?:Street|St\.|Avenue|Ave\.|Road|Rd\.))',
                            ]
                            for pattern in street_patterns:
                                street_match = re.search(pattern, search_result, re.IGNORECASE)
                                if street_match:
                                    address_info['address_line1'] = street_match.group(1).strip()[:100]
                                    break
                            
                            # Try to extract city (common Mexican cities or patterns)
                            city_patterns = [
                                r'\b(San Luis Potos[ií]|Monterrey|Guadalajara|Ciudad de M[eé]xico|CDMX|Tijuana|Puebla|Le[oó]n|Zapopan|Quer[eé]taro|M[eé]rida|Toluca|Aguascalientes|Chihuahua|Hermosillo|Saltillo|Morelia|Culiac[aá]n)\b',
                                r',\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?),\s*(?:Mexico|MX)',
                            ]
                            for pattern in city_patterns:
                                city_match = re.search(pattern, search_result, re.IGNORECASE)
                                if city_match:
                                    address_info['city'] = city_match.group(1).strip()
                                    break
                            
                            # Store raw search for address creation
                            address_info['raw_search'] = search_result[:1500]
                    
                    # Detect country from name or search
                    country = "Mexico"  # Default
                    if any(c in supplier_name.lower() for c in ["italia", "italy"]):
                        country = "Italy"
                    elif any(c in supplier_name.lower() for c in ["china", "chinese"]):
                        country = "China"
                    elif any(c in supplier_name.lower() for c in ["india", "indian"]):
                        country = "India"
                    elif any(c in supplier_name.lower() for c in ["usa", "america", "united states"]):
                        country = "United States"
                    
                    # Create or update supplier
                    if existing_supplier:
                        supplier = frappe.get_doc("Supplier", existing_supplier)
                        supplier.country = country
                        supplier.save(ignore_permissions=False)
                        result_msg = f"✅ Updated Supplier: **{supplier_name}** (ID: {supplier.name})\n"
                    else:
                        supplier = frappe.get_doc({
                            "doctype": "Supplier",
                            "supplier_name": supplier_name,
                            "supplier_group": "All Supplier Groups",
                            "supplier_type": "Company",
                            "country": country
                        })
                        supplier.insert(ignore_permissions=False)
                        result_msg = f"✅ Created Supplier: **{supplier_name}** (ID: {supplier.name})\n"
                    
                    result_msg += f"📍 Country: {country}\n"
                    
                    # Create or update address if we found info
                    if address_info.get('raw_search'):
                        try:
                            # Check for existing address
                            existing_addr = frappe.db.get_value("Dynamic Link", 
                                {"link_doctype": "Supplier", "link_name": supplier.name, "parenttype": "Address"}, 
                                "parent")
                            
                            # Prepare address data from extracted info
                            addr_line1 = address_info.get('address_line1', 'To be updated')
                            addr_city = address_info.get('city', 'To be updated')
                            addr_pincode = address_info.get('pincode', '00000')
                            addr_phone = address_info.get('phone', '')
                            addr_email = address_info.get('email', 'update@needed.com')
                            
                            if existing_addr:
                                address_doc = frappe.get_doc("Address", existing_addr)
                                if addr_line1 != 'To be updated':
                                    address_doc.address_line1 = addr_line1
                                if addr_city != 'To be updated':
                                    address_doc.city = addr_city
                                if addr_pincode != '00000':
                                    address_doc.pincode = addr_pincode
                                if addr_phone:
                                    address_doc.phone = addr_phone
                                if addr_email and addr_email != 'update@needed.com':
                                    address_doc.email_id = addr_email
                                address_doc.save(ignore_permissions=False)
                                result_msg += f"📧 Address updated:\n  📍 {addr_line1}\n  🏙️ {addr_city}, {addr_pincode}\n  📞 {addr_phone}\n"
                            else:
                                address_doc = frappe.get_doc({
                                    "doctype": "Address",
                                    "address_title": supplier_name,
                                    "address_type": "Billing",
                                    "address_line1": addr_line1,
                                    "city": addr_city,
                                    "pincode": addr_pincode,
                                    "country": country,
                                    "phone": addr_phone or '',
                                    "email_id": addr_email or 'update@needed.com',
                                    "links": [{
                                        "link_doctype": "Supplier",
                                        "link_name": supplier.name
                                    }]
                                })
                                address_doc.insert(ignore_permissions=False)
                                result_msg += f"📧 Address created:\n  📍 {addr_line1}\n  🏙️ {addr_city}, {addr_pincode}\n  📞 {addr_phone}\n"
                            
                            result_msg += f"\n**Web Search Results (update address manually):**\n{address_info['raw_search'][:500]}..."
                        except Exception as addr_err:
                            result_msg += f"\n⚠️ Could not auto-create address: {str(addr_err)}"
                    
                    result_msg += "\n\nYou can now add more details in ERPNext."
                    
                    return {
                        "success": True,
                        "message": result_msg
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Failed to create supplier: {str(e)}"
                    }
        
        return None
    

        return None
