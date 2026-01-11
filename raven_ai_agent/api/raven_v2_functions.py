"""
Raven v2 AI Agent Function Definitions

These functions expose Raymond-Lucy Agent capabilities through Raven v2's
function calling system. Each function can be invoked by the AI agent
to perform ERPNext operations.

Reference: https://ravenchat.ai/docs/function-calling
"""
import frappe
import json
from typing import Optional, Dict, List

# ============================================================================
# MEMORY OPERATIONS - Raven v2 Functions
# ============================================================================

@frappe.whitelist()
def search_memories(query: str, limit: int = 5) -> str:
    """
    Search AI Memory for relevant facts and context.
    
    Args:
        query: Search query for semantic memory search
        limit: Maximum number of memories to return
        
    Returns:
        JSON string with matching memories
    """
    user = frappe.session.user
    
    memories = frappe.get_list(
        "AI Memory",
        filters={"user": user},
        fields=["content", "importance", "source", "creation"],
        order_by="creation desc",
        limit=limit
    )
    
    return json.dumps({
        "success": True,
        "memories": memories,
        "count": len(memories)
    }, default=str)


@frappe.whitelist()
def store_memory(content: str, importance: str = "Normal", source: str = "Raven Chat") -> str:
    """
    Store a fact in AI Memory (Memento Protocol).
    
    Args:
        content: The fact or information to remember
        importance: Priority level (Critical, High, Normal, Low)
        source: Where this memory came from
        
    Returns:
        JSON string confirming storage
    """
    user = frappe.session.user
    
    doc = frappe.get_doc({
        "doctype": "AI Memory",
        "user": user,
        "content": content,
        "importance": importance,
        "memory_type": "Fact",
        "source": source
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    
    return json.dumps({
        "success": True,
        "memory_id": doc.name,
        "message": f"Stored memory with importance: {importance}"
    })


# ============================================================================
# ERPNEXT CONTEXT - Raven v2 Functions
# ============================================================================

@frappe.whitelist()
def get_recent_documents(doctype: str, limit: int = 10) -> str:
    """
    Get recent documents of a specific type.
    
    Args:
        doctype: ERPNext DocType (Sales Invoice, Sales Order, etc.)
        limit: Maximum documents to return
        
    Returns:
        JSON string with document list
    """
    try:
        # Get common fields based on doctype
        common_fields = ["name", "creation", "modified", "owner"]
        
        docs = frappe.get_list(
            doctype,
            fields=common_fields,
            order_by="creation desc",
            limit=limit
        )
        
        site = frappe.local.site
        for doc in docs:
            doc["link"] = f"https://{site}/app/{frappe.scrub(doctype)}/{doc['name']}"
        
        return json.dumps({
            "success": True,
            "doctype": doctype,
            "documents": docs,
            "count": len(docs)
        }, default=str)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@frappe.whitelist()
def get_document_details(doctype: str, name: str) -> str:
    """
    Get full details of a specific document.
    
    Args:
        doctype: ERPNext DocType
        name: Document name/ID
        
    Returns:
        JSON string with document data
    """
    try:
        doc = frappe.get_doc(doctype, name)
        
        # Check permission
        if not frappe.has_permission(doctype, "read", doc=doc):
            return json.dumps({
                "success": False,
                "error": "Permission denied"
            })
        
        site = frappe.local.site
        
        return json.dumps({
            "success": True,
            "doctype": doctype,
            "name": name,
            "data": doc.as_dict(),
            "link": f"https://{site}/app/{frappe.scrub(doctype)}/{name}"
        }, default=str)
        
    except frappe.DoesNotExistError:
        return json.dumps({
            "success": False,
            "error": f"{doctype} '{name}' not found"
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })


# ============================================================================
# WORKFLOW OPERATIONS - Raven v2 Functions
# ============================================================================

@frappe.whitelist()
def execute_workflow(action: str, document_name: str, **kwargs) -> str:
    """
    Execute a workflow command on a document.
    
    Args:
        action: Workflow action (submit_quotation, create_sales_order, etc.)
        document_name: The document to operate on
        **kwargs: Additional parameters for the action
        
    Returns:
        JSON string with operation result
    """
    try:
        from raven_ai_agent.api.workflows import WorkflowExecutor
        
        user = frappe.session.user
        executor = WorkflowExecutor(user)
        
        # Map action to executor method
        action_map = {
            "submit_quotation": lambda: executor.submit_quotation(document_name, confirm=True),
            "create_sales_order": lambda: executor.create_sales_order_from_quotation(document_name, confirm=True),
            "submit_sales_order": lambda: executor.submit_sales_order(document_name, confirm=True),
            "create_work_orders": lambda: executor.create_work_orders_from_sales_order(document_name, confirm=True),
            "create_delivery_note": lambda: executor.create_delivery_note_from_sales_order(document_name, confirm=True),
            "workflow_status": lambda: executor.get_workflow_status(
                quotation_name=document_name if document_name.startswith("SAL-QTN") else None,
                so_name=document_name if document_name.startswith("SAL-ORD") else None
            )
        }
        
        if action not in action_map:
            return json.dumps({
                "success": False,
                "error": f"Unknown action: {action}",
                "available_actions": list(action_map.keys())
            })
        
        result = action_map[action]()
        return json.dumps(result, default=str)
        
    except Exception as e:
        frappe.log_error(f"execute_workflow error: {str(e)}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@frappe.whitelist()
def complete_workflow_to_invoice(quotation_name: str, dry_run: bool = False) -> str:
    """
    Complete full workflow: Quotation -> Sales Order -> Work Order -> Delivery Note -> Invoice
    
    Args:
        quotation_name: The quotation to process (e.g., SAL-QTN-2024-00001)
        dry_run: If True, preview without executing
        
    Returns:
        JSON string with workflow result
    """
    try:
        from raven_ai_agent.api.workflows import complete_workflow_to_invoice as workflow_func
        
        result = workflow_func(quotation_name, dry_run=dry_run)
        return json.dumps(result, default=str)
        
    except Exception as e:
        frappe.log_error(f"complete_workflow_to_invoice error: {str(e)}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


# ============================================================================
# TDS & BOM OPERATIONS - Raven v2 Functions
# ============================================================================

@frappe.whitelist()
def resolve_tds_bom(sales_item: str, customer: str = None) -> str:
    """
    Resolve TDS Product Specification to BOM for a sales item.
    
    Args:
        sales_item: Sales item code (e.g., "0307")
        customer: Optional customer name
        
    Returns:
        JSON with TDS -> Production Item -> BOM mapping
    """
    try:
        from raven_ai_agent.api.workflows import resolve_tds_bom as resolve_func
        
        result = resolve_func(sales_item, customer)
        return json.dumps(result, default=str)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@frappe.whitelist()
def submit_bom_creator(bom_creator_name: str) -> str:
    """
    Submit a BOM Creator to generate BOMs.
    
    Args:
        bom_creator_name: Name of the BOM Creator document
        
    Returns:
        JSON with submission result and created BOMs
    """
    try:
        from raven_ai_agent.agents.bom_creator_agent import submit_bom_creator as submit_func
        
        result = submit_func(bom_creator_name)
        return json.dumps(result, default=str)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })


# ============================================================================
# FUNCTION REGISTRY - For Raven v2 Discovery
# ============================================================================

def get_available_functions() -> List[Dict]:
    """
    Return list of available functions for Raven v2 discovery.
    
    This follows OpenAI function calling format for compatibility.
    """
    return [
        {
            "name": "search_memories",
            "description": "Search AI Memory for relevant facts and user context",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results", "default": 5}
                },
                "required": ["query"]
            }
        },
        {
            "name": "store_memory",
            "description": "Store a fact in AI Memory for future reference",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Fact to remember"},
                    "importance": {"type": "string", "enum": ["Critical", "High", "Normal", "Low"]},
                    "source": {"type": "string", "description": "Source of the memory"}
                },
                "required": ["content"]
            }
        },
        {
            "name": "get_recent_documents",
            "description": "Get recent documents of a specific ERPNext DocType",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctype": {"type": "string", "description": "ERPNext DocType name"},
                    "limit": {"type": "integer", "description": "Max documents", "default": 10}
                },
                "required": ["doctype"]
            }
        },
        {
            "name": "execute_workflow",
            "description": "Execute workflow action on a document",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["submit_quotation", "create_sales_order", "submit_sales_order", 
                                "create_work_orders", "create_delivery_note", "workflow_status"]
                    },
                    "document_name": {"type": "string", "description": "Document name to operate on"}
                },
                "required": ["action", "document_name"]
            }
        },
        {
            "name": "complete_workflow_to_invoice",
            "description": "Complete full workflow from Quotation to Invoice",
            "parameters": {
                "type": "object",
                "properties": {
                    "quotation_name": {"type": "string", "description": "Quotation name (SAL-QTN-XXXX)"},
                    "dry_run": {"type": "boolean", "description": "Preview without executing", "default": False}
                },
                "required": ["quotation_name"]
            }
        },
        {
            "name": "resolve_tds_bom",
            "description": "Resolve TDS Product Specification to BOM for manufacturing",
            "parameters": {
                "type": "object",
                "properties": {
                    "sales_item": {"type": "string", "description": "Sales item code"},
                    "customer": {"type": "string", "description": "Customer name (optional)"}
                },
                "required": ["sales_item"]
            }
        },
        {
            "name": "submit_bom_creator",
            "description": "Submit BOM Creator to generate Bill of Materials",
            "parameters": {
                "type": "object",
                "properties": {
                    "bom_creator_name": {"type": "string", "description": "BOM Creator document name"}
                },
                "required": ["bom_creator_name"]
            }
        }
    ]


@frappe.whitelist()
def list_functions() -> str:
    """API endpoint to list available functions for Raven v2."""
    return json.dumps({
        "success": True,
        "functions": get_available_functions()
    })
