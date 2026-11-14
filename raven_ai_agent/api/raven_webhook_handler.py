"""
V13.6.0 P3 Migration: Raven Webhook Handlers
Original Server Scripts: /api/method/raven_webhook_handler.handle, Raven Webhook Handler Script
Type: Whitelisted APIs
"""

import hmac

import frappe

# ============================================================
# Handler 1: /api/method/raven_webhook_handler.handle
# ============================================================

from frappe import whitelist
import frappe

def _require_secret():
    """TASKS-344 N-11: every guest webhook here needs the shared secret. An UNSET secret refuses (None == None
    used to pass); constant-time compare."""
    expected = frappe.conf.get("raven_webhook_secret")
    if not expected:
        frappe.throw("Webhook secret not configured", frappe.AuthenticationError)
    secret = frappe.get_request_header("X-Raven-Secret")
    if not secret or not hmac.compare_digest(str(secret).encode("utf-8"), str(expected).encode("utf-8")):
        frappe.throw("Invalid secret", frappe.AuthenticationError)


@frappe.whitelist(allow_guest=True)
def handle_webhook(**kwargs):
    _require_secret()
    try:
        data = frappe.request.get_json()
        
        # Validate the request if needed
        # Process the webhook data
        
        return {"success": True, "message": "Webhook processed"}
    except Exception as e:
        frappe.log_error(title="Raven Webhook Error")
        return {"success": False, "error": str(e)}

# ============================================================
# Handler 2: Raven Webhook Handler Script
# ============================================================

@frappe.whitelist(allow_guest=True)
def handle():
    _require_secret()
    
    data = frappe.request.get_json()
    # Process your webhook data here
    
    return {"status": "success"}
def validate(doc, method):
    # Auto-set the webhook handler link in child table
    for row in doc.get("trigger_events", []):
        if not row.webhook_handler:
            row.webhook_handler = doc.name
    
    # Validate at least one trigger is enabled
    if not any(row.enabled for row in doc.get("trigger_events", [])):
        frappe.throw("Please enable at least one trigger event", title="Configuration Error")
        # (TASKS-344 N-11: handle_sales_order_webhook and create_installation_project removed: dead, no caller;
        #  the first called undefined verify_webhook(), the second was a guest-callable insert of a Project)
# In hooks.py
def handle_sales_order(doc, method):
    if doc.doctype == 'Sales Order' and doc.workflow_state == 'Submitted':
        frappe.enqueue(
            'your_app.webhooks.process_sales_order',
            sales_order=doc.name
        )

def process_sales_order(sales_order):
    doc = frappe.get_doc('Sales Order', sales_order)
    
    payload = {
        'event': 'order_submitted',
        'order_id': doc.name,
        'customer': doc.customer_name,
        'amount': doc.grand_total
    }
    
    # Send to Raven or external system
    frappe.make_post_request(
        url='https://your-endpoint.com/webhook',
        data=payload,
        headers={'Authorization': 'Bearer your-token'}
    )

