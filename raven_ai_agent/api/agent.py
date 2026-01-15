"""
Raymond-Lucy AI Agent Core
Anti-Hallucination + Persistent Memory + Autonomy Slider
"""
import frappe
import json
import re
import requests
from typing import Optional, Dict, List
from openai import OpenAI
from bs4 import BeautifulSoup

# Import vector store for semantic search
try:
    from raven_ai_agent.utils.vector_store import VectorStore
    VECTOR_SEARCH_ENABLED = True
except ImportError:
    VECTOR_SEARCH_ENABLED = False

# Import workflow executor
try:
    from raven_ai_agent.api.workflows import WorkflowExecutor
    WORKFLOWS_ENABLED = True
except ImportError:
    WORKFLOWS_ENABLED = False

SYSTEM_PROMPT = """
You are an AI assistant for ERPNext operating under the "Raymond-Lucy Protocol v2.0".

## ARCHITECTURE: LLM OS MODEL
- Context Window = RAM (limited, resets each session)
- Vector DB = Hard Drive (persistent memory via AI Memory doctype)
- Tools = ERPNext APIs and Frappe framework

## CORE PRINCIPLES

### 1. RAYMOND PROTOCOL (Anti-Hallucination)
- NEVER fabricate ERPNext data - always query the database
- ALWAYS cite document names and field values
- EXPRESS confidence: HIGH/MEDIUM/LOW/UNCERTAIN
- Use frappe.db queries to verify facts

### 2. MEMENTO PROTOCOL (Fact Storage)
Store important facts about user preferences and context:
- CRITICAL: User roles, permissions, company context
- HIGH: Recent transactions, workflow states
- NORMAL: Preferences, past queries

### 3. LUCY PROTOCOL (Context Continuity)
- Load user's morning briefing at session start
- Reference past conversations naturally
- Generate session summaries

### 4. KARPATHY PROTOCOL (Autonomy Slider)
- LEVEL 1 (COPILOT): Suggest, explain, query data
- LEVEL 2 (COMMAND): Execute specific operations with confirmation
- LEVEL 3 (AGENT): Multi-step workflows (requires explicit permission)

## ERPNEXT SPECIFIC RULES
1. Always verify doctypes exist before querying
2. Check user permissions before showing sensitive data
3. Use frappe.get_doc() for single documents
4. Use frappe.get_list() for multiple documents
5. Format currency/dates according to user's locale

## RESPONSE FORMAT
[CONFIDENCE: HIGH/MEDIUM/LOW/UNCERTAIN] [AUTONOMY: LEVEL 1/2/3]

{Your response - be concise and actionable}

When showing documents:
- Include clickable links if provided in context
- Format as a clean list with key info (name, customer/party, amount, date, status)
- Use markdown formatting for clarity

## EXTERNAL WEB ACCESS
- You CAN fetch data from external URLs if the user provides a specific URL in their query
- Example: "find address from http://www.barentz.com/contact" will fetch that website's content
- You CAN also do web searches without URLs using keywords like "search", "find", "look up"
- Example: "search for barentz italia address" will search the web and return results
- When web search results are provided, summarize the relevant information for the user

## DYNAMIC DATA ACCESS
- You have access to any ERPNext doctype the user has permission to view
- The system auto-detects which doctypes are relevant based on keywords in the query
- If no data is found, it means either no records exist or user lacks permission

## CRITICAL RULES - MUST FOLLOW
- NEVER say "hold on", "please wait", "let me check", "searching now", "I will perform" - you CANNOT do follow-up queries
- NEVER promise to search or fetch data - the search has ALREADY been done BEFORE your response
- If you see "⭐ WEB SEARCH RESULTS" or "⭐ EXTERNAL WEB DATA" in context, IMMEDIATELY extract and present the information
- ALWAYS assume LEVEL 1 for read-only queries about addresses, contacts, websites, or any information lookup
- Do NOT ask "Would you like to proceed with a web search?" - the search is ALREADY DONE
- Extract and present the relevant information from the provided context
- If data is not in the provided context, say "I don't have that data available"

[Sources: Document names queried]
"""

CAPABILITIES_LIST = """
## 🤖 AI Agent Capabilities

### 📊 ERPNext Data Access
- `@ai show my quotations` - View your quotations, sales orders, work orders
- `@ai show pending deliveries` - Delivery notes, stock levels, inventory
- `@ai best selling items` - Sales analytics and reports
- `@ai TDS resolution for [item]` - Tax and compliance info

### 🌐 Web Research
- `@ai search [topic]` - Web search for any topic
- `@ai find suppliers for [product]` - Find manufacturers/suppliers
- `@ai extract from [URL]` - Extract data from any website
- `@ai who are the players in [market]` - Market research

### 📝 Create ERPNext Records
- `@ai create supplier [name]` - Create basic supplier
- `@ai create supplier [name] with address` - Search web & create with address
- `@ai save this research` - Cache research to AI Memory

### 🔧 Workflows (Level 2-3)
- `@ai convert quotation [name] to sales order` - Document conversion
- `@ai create work order for [item]` - Manufacturing workflows
- `!command` - Force execute without confirmation

### 🏭 Manufacturing SOP
- `@ai show work orders` - List active work orders
- `@ai create work order for [item] qty [n]` - Create new work order
- `@ai material status for [WO]` - Check component availability
- `@ai reserve stock for [WO]` - Reserve materials for work order
- `@ai submit work order [WO]` - Submit/start work order
- `@ai show job cards for [WO]` - List job cards/operations
- `@ai update progress for [WO] qty [n]` - Report production progress
- `@ai issue materials for [WO]` - Create Stock Entry (Material Issue)
- `@ai finish work order [WO]` - Complete production & receive goods
- `@ai quality check` - Show recent Quality Inspections
- `@ai show BOM cost report` - Compare estimated vs actual costs

**Stock Entry Management:**
- `@ai material receipt [ITEM] qty [n] price $[x]` - Create Material Receipt entry with price
- `@ai convert [STE] to material receipt` - Convert draft to Material Receipt
- `@ai verify stock entries` - Check submitted vs draft entries
- `@ai check stock ledger` - Show recent stock ledger entries
- `@ai list batches` - Show recently created batches
- `@ai troubleshoot` - Manufacturing troubleshooting guide

### 🔄 Sales-to-Purchase Cycle SOP
- `@ai show opportunities` - List sales opportunities
- `@ai create opportunity for [customer]` - Create new sales opportunity
- `@ai check inventory for [SO]` - Check item availability for Sales Order
- `@ai create material request for [SO]` - Create Material Request from SO
- `@ai show material requests` - List pending material requests
- `@ai create rfq from [MR]` - Create Request for Quotation
- `@ai show rfqs` - List RFQs and their status
- `@ai show supplier quotations` - List supplier quotations
- `@ai create po from [SQ]` - Create Purchase Order from Supplier Quotation
- `@ai receive goods for [PO]` - Create Purchase Receipt
- `@ai create purchase invoice for [PO]` - Bill against Purchase Order
- `@ai create delivery note for [SO]` - Ship items to customer
- `@ai create sales invoice for [SO/DN]` - Invoice the customer

### 📦 Sales Order Follow-up Bot
Use `@sales_order_follow_up` for dedicated SO tracking:
- `@sales_order_follow_up pending` - List all pending Sales Orders
- `@sales_order_follow_up status [SO]` - Detailed SO status
- `@sales_order_follow_up check inventory [SO]` - Check stock availability
- `@sales_order_follow_up next steps [SO]` - Recommended actions
- `@sales_order_follow_up track [SO]` - Full purchase cycle tracking

### 📋 BOM Management
- `@ai show bom BOM-XXXX` - View all items, operations, costs
- `@ai !cancel bom BOM-XXXX` - Cancel submitted BOM
- `@ai !revert bom BOM-XXXX to draft` - Reset cancelled BOM to draft
- `@ai check bom for [item]` - Check BOM label status
- `@ai fix bom for [item]` - Auto-fix missing labels
- `@ai force fix bom BOM-XXX label LBLXXX` - Force SQL insert

### 🏗️ BOM Creator
- `@ai !submit bom BOM-XXXX` - Submit BOM Creator to generate BOMs
- `@ai validate bom BOM-XXXX` - Validate BOM Creator before submission
- `@ai create bom from tds [TDS-NAME]` - Create BOM Creator from TDS

### 📄 Document Actions
- `@ai !submit Sales Order SO-XXXX` - Submit sales order
- `@ai !submit Work Order MFG-WO-XXXX` - Submit work order
- `@ai unlink sales order from MFG-WO-XXXX` - Remove SO link from WO

### ℹ️ Help
- `@ai help` or `@ai capabilities` - Show this list
- `@ai what can you do` - Show capabilities

Type your question and I'll help!
"""


class RaymondLucyAgent:
    """Main AI Agent class implementing the protocol"""
    
    def __init__(self, user: str):
        self.user = user
        self.settings = self._get_settings()
        self.client = OpenAI(api_key=self.settings.get("openai_api_key"))
        self.model = self.settings.get("model", "gpt-4o-mini")
        self.autonomy_level = 1  # Default to COPILOT
        
    def _get_settings(self) -> Dict:
        """Load AI Agent Settings"""
        try:
            settings = frappe.get_single("AI Agent Settings")
            return {
                "openai_api_key": settings.get_password("openai_api_key"),
                "model": settings.model or "gpt-4o-mini",
                "max_tokens": settings.max_tokens or 2000,
                "confidence_threshold": settings.confidence_threshold or 0.7
            }
        except Exception:
            return {}
    
    def get_morning_briefing(self) -> str:
        """Lucy Protocol: Load context at session start"""
        # Get user's critical memories
        memories = frappe.get_list(
            "AI Memory",
            filters={"user": self.user, "importance": ["in", ["Critical", "High"]]},
            fields=["content", "importance", "source"],
            order_by="creation desc",
            limit=10
        )
        
        # Get latest summary
        summaries = frappe.get_list(
            "AI Memory",
            filters={"user": self.user, "memory_type": "Summary"},
            fields=["content"],
            order_by="creation desc",
            limit=1
        )
        
        briefing = "## Morning Briefing\n\n"
        
        if summaries:
            briefing += f"**Last Session Summary:**\n{summaries[0].content}\n\n"
        
        if memories:
            briefing += "**Key Facts:**\n"
            for m in memories:
                briefing += f"- [{m.importance}] {m.content}\n"
        
        return briefing
    
    def search_memories(self, query: str, limit: int = 5) -> List[Dict]:
        """RAG: Search relevant memories using vector similarity"""
        if VECTOR_SEARCH_ENABLED:
            try:
                vector_store = VectorStore()
                return vector_store.search_similar(
                    user=self.user,
                    query=query,
                    limit=limit,
                    similarity_threshold=self.settings.get("confidence_threshold", 0.7)
                )
            except Exception:
                pass  # Fallback to keyword search
        
        # Fallback: Simple keyword search
        memories = frappe.get_list(
            "AI Memory",
            filters={
                "user": self.user,
                "content": ["like", f"%{query}%"]
            },
            fields=["content", "importance", "source", "creation"],
            order_by="creation desc",
            limit=limit
        )
        return memories
    
    def tattoo_fact(self, content: str, importance: str = "Normal", source: str = None):
        """Memento Protocol: Store important fact with embedding"""
        if VECTOR_SEARCH_ENABLED:
            try:
                vector_store = VectorStore()
                return vector_store.store_memory_with_embedding(
                    user=self.user,
                    content=content,
                    importance=importance,
                    source=source
                )
            except Exception:
                pass  # Fallback to basic storage
        
        # Fallback: Store without embedding
        doc = frappe.get_doc({
            "doctype": "AI Memory",
            "user": self.user,
            "content": content,
            "importance": importance,
            "memory_type": "Fact",
            "source": source or "Conversation"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    
    # Doctype keyword mappings for dynamic detection
    DOCTYPE_KEYWORDS = {
        "Sales Invoice": ["invoice", "factura", "billing", "invoiced"],
        "Sales Order": ["sales order", "orden de venta", "so-", "pedido"],
        "Purchase Order": ["purchase order", "orden de compra", "po-"],
        "Purchase Invoice": ["purchase invoice", "factura de compra"],
        "Quotation": ["quotation", "quote", "cotización", "cotizacion"],
        "Customer": ["customer", "client", "cliente"],
        "Supplier": ["supplier", "vendor", "proveedor"],
        "Item": ["item", "product", "artículo", "articulo", "producto"],
        "Stock Entry": ["stock entry", "stock", "inventario", "inventory"],
        "Delivery Note": ["delivery", "shipping", "entrega", "envío"],
        "Purchase Receipt": ["purchase receipt", "receipt", "recepción"],
        "Work Order": ["work order", "manufacturing", "production", "producción"],
        "BOM": ["bom", "bill of material", "lista de materiales"],
        "Quality Inspection": ["quality", "inspection", "qc", "calidad", "inspección"],
        "Material Request": ["material request", "requisición", "requisicion"],
        "Lead": ["lead", "prospecto"],
        "Opportunity": ["opportunity", "oportunidad"],
        "Address": ["address", "dirección", "direccion"],
        "Contact": ["contact", "contacto"],
        "Employee": ["employee", "empleado"],
        "Warehouse": ["warehouse", "almacén", "almacen"],
        "Batch": ["batch", "lote"],
        "Serial No": ["serial", "serie"],
        "Payment Entry": ["payment", "pago"],
        "Journal Entry": ["journal", "asiento", "diario"],
    }
    
    def detect_doctype_from_query(self, query: str) -> List[str]:
        """Detect which doctypes the user is asking about"""
        query_lower = query.lower()
        detected = []
        for doctype, keywords in self.DOCTYPE_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                detected.append(doctype)
        return detected
    
    def query_doctype_with_permissions(self, doctype: str, query: str, limit: int = 10) -> List[Dict]:
        """Query a doctype if user has permissions"""
        try:
            # Check if user has read permission
            if not frappe.has_permission(doctype, "read"):
                return []
            
            # Get standard fields for the doctype
            meta = frappe.get_meta(doctype)
            fields = ["name"]
            
            # Add common useful fields if they exist
            common_fields = ["customer", "supplier", "grand_total", "total", "status", 
                           "transaction_date", "posting_date", "modified", "creation",
                           "item_code", "item_name", "customer_name", "party_name",
                           "territory", "company", "owner"]
            for field in common_fields:
                if meta.has_field(field):
                    fields.append(field)
            
            # Build filters based on query context
            filters = {}
            
            # Check for specific document name patterns in query
            query_upper = query.upper()
            name_patterns = re.findall(r'[A-Z]{2,4}[-\s]?\d{4,}[-\w]*', query_upper)
            if name_patterns:
                filters["name"] = ["like", f"%{name_patterns[0]}%"]
            
            # Query the doctype
            results = frappe.get_list(
                doctype,
                filters=filters if filters else {"docstatus": ["<", 2]},
                fields=list(set(fields)),
                order_by="modified desc",
                limit=limit
            )
            
            # Add links to results
            site_name = frappe.local.site
            doctype_slug = doctype.lower().replace(" ", "-")
            for r in results:
                r["link"] = f"https://{site_name}/app/{doctype_slug}/{r['name']}"
                r["_doctype"] = doctype
            
            return results
        except Exception as e:
            frappe.logger().error(f"Error querying {doctype}: {str(e)}")
            return []
    
    def get_available_doctypes(self) -> List[str]:
        """Get list of doctypes user has permission to access"""
        available = []
        for doctype in self.DOCTYPE_KEYWORDS.keys():
            try:
                if frappe.has_permission(doctype, "read"):
                    available.append(doctype)
            except:
                pass
        return available
    
    def duckduckgo_search(self, query: str, max_results: int = 5) -> str:
        """Search the web using DuckDuckGo (no API key required)"""
        try:
            # Use DuckDuckGo HTML search
            search_url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
            response = requests.get(search_url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            
            if response.status_code != 200:
                return f"Search failed: HTTP {response.status_code}"
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            # Parse DuckDuckGo HTML results
            for idx, result in enumerate(soup.find_all('div', class_='result')[:max_results], 1):
                title_tag = result.find('a', class_='result__a')
                snippet_tag = result.find('a', class_='result__snippet')
                
                if title_tag:
                    title = title_tag.get_text(strip=True)
                    raw_link = title_tag.get('href', '')
                    # Extract actual URL from DuckDuckGo redirect
                    if 'uddg=' in raw_link:
                        try:
                            from urllib.parse import unquote, parse_qs, urlparse
                            parsed = urlparse(raw_link)
                            params = parse_qs(parsed.query)
                            link = unquote(params.get('uddg', [raw_link])[0])
                        except:
                            link = raw_link
                    else:
                        link = raw_link
                    snippet = snippet_tag.get_text(strip=True) if snippet_tag else ''
                    results.append(f"**{idx}. {title}**\n🔗 {link}\n📝 {snippet}")
            
            if results:
                return "\n\n".join(results)
            else:
                return f"No search results found for: {query}"
                
        except Exception as e:
            frappe.logger().error(f"[AI Agent] DuckDuckGo search error: {str(e)}")
            return f"Search error: {str(e)}"
    
    def search_web(self, query: str, url: str = None) -> str:
        """Search the web or extract info from a specific URL"""
        try:
            if url:
                # Fetch specific URL with redirects
                response = requests.get(url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5"
                }, allow_redirects=True)
                
                frappe.logger().info(f"[AI Agent] Web request to {url}: status={response.status_code}")
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extract text content
                    for script in soup(["script", "style", "nav", "footer", "header"]):
                        script.decompose()
                    
                    extracted_data = []
                    
                    # Extract tables (for supplier lists, data tables)
                    tables = soup.find_all('table')
                    for table in tables[:3]:  # Max 3 tables
                        rows = table.find_all('tr')
                        table_text = []
                        for row in rows[:20]:  # Max 20 rows per table
                            cells = row.find_all(['td', 'th'])
                            row_text = ' | '.join(cell.get_text(strip=True) for cell in cells)
                            if row_text.strip():
                                table_text.append(row_text)
                        if table_text:
                            extracted_data.append("TABLE:\n" + "\n".join(table_text))
                    
                    # Extract lists (ul/ol) with company/supplier info
                    for lst in soup.find_all(['ul', 'ol'])[:5]:
                        items = lst.find_all('li')[:15]
                        list_items = [li.get_text(strip=True) for li in items if li.get_text(strip=True)]
                        if list_items and any(len(item) > 10 for item in list_items):
                            extracted_data.append("LIST:\n" + "\n".join(list_items))
                    
                    # Look for address/contact content
                    for tag in soup.find_all(['address', 'div', 'p', 'span']):
                        text = tag.get_text(strip=True)
                        if any(kw in text.lower() for kw in ['address', 'street', 'via', 'piazza', 'italy', 'italia', 'contact', 'location', 'supplier', 'manufacturer', 'company']):
                            if text not in extracted_data and len(text) > 20:
                                extracted_data.append(text)
                    
                    if extracted_data:
                        return f"Extracted from {url}:\n" + "\n\n".join(extracted_data[:15])
                    
                    # Fallback to general text
                    text = soup.get_text(separator=' ', strip=True)
                    return f"Content from {url}:\n{text[:4000]}"
                else:
                    return f"Could not fetch {url}: HTTP {response.status_code}"
            else:
                # Perform DuckDuckGo search for general queries
                return self.duckduckgo_search(query)
        except requests.exceptions.Timeout:
            return f"Web request timed out for {url}"
        except requests.exceptions.RequestException as e:
            return f"Web request failed for {url}: {str(e)}"
        except Exception as e:
            frappe.logger().error(f"[AI Agent] Web search error: {str(e)}")
            return f"Web search error: {str(e)}"
    
    def get_erpnext_context(self, query: str) -> str:
        """Raymond Protocol: Get verified ERPNext data based on user permissions"""
        context = []
        query_lower = query.lower()
        
        # Check for URL in query - fetch external website data
        url_match = re.search(r'https?://[^\s<>"\']+', query)
        if url_match:
            url = url_match.group(0).rstrip('.,;:')  # Clean trailing punctuation
            frappe.logger().info(f"[AI Agent] Fetching URL: {url}")
            web_content = self.search_web(query, url)
            if web_content and not web_content.startswith("Web search error"):
                context.insert(0, f"⭐ EXTERNAL WEB DATA (from {url}):\n{web_content}")
                frappe.logger().info(f"[AI Agent] Web content fetched: {len(web_content)} chars")
        
        # Check for web search intent (no URL but wants external info)
        search_keywords = ["search", "buscar", "find on web", "google", "look up", "search for", "search web", "find"]
        external_entities = ["barentz", "legosan", "website", "company info", "address", "contact", "ubicacion", "direccion", "indirizzo"]
        
        # Market research / external knowledge patterns
        market_keywords = ["market", "mercado", "players", "competitors", "suppliers", "manufacturers", 
                          "companies", "industry", "trend", "price", "pricing", "region", "country"]
        question_patterns = ["who are", "what are", "which", "list of", "tell me about", "information about",
                            "quienes son", "cuales son", "dime sobre"]
        
        # Check if query asks about external market/industry data
        is_market_question = (
            any(mk in query_lower for mk in market_keywords) and
            any(qp in query_lower for qp in question_patterns)
        )
        
        needs_web_search = (
            any(kw in query_lower for kw in search_keywords) or
            (any(ent in query_lower for ent in external_entities) and not url_match) or
            is_market_question
        )
        
        if needs_web_search and not url_match:
            # Extract search terms - remove common words
            search_terms = query_lower
            for word in ["@ai", "search", "find", "buscar", "look up", "web", "on", "for", "the", "a", "an"]:
                search_terms = re.sub(r'\b' + re.escape(word) + r'\b', ' ', search_terms)
            search_terms = " ".join(search_terms.split())  # Clean whitespace
            
            if len(search_terms) > 3:
                frappe.logger().info(f"[AI Agent] Web search for: {search_terms}")
                search_results = self.duckduckgo_search(search_terms)
                if search_results and "No search results" not in search_results:
                    context.insert(0, f"⭐ WEB SEARCH RESULTS:\n{search_results}")
        
        # Dynamic doctype detection - query any relevant doctypes user has permission to
        detected_doctypes = self.detect_doctype_from_query(query)
        for doctype in detected_doctypes:
            results = self.query_doctype_with_permissions(doctype, query)
            if results:
                context.append(f"{doctype} Data: {json.dumps(results, default=str)}")
        
        # Also run specific keyword-based queries for backward compatibility
        
        if any(word in query_lower for word in ["invoice", "sales", "revenue"]):
            invoices = frappe.get_list(
                "Sales Invoice",
                filters={"docstatus": 1},
                fields=["name", "customer", "grand_total", "posting_date"],
                order_by="posting_date desc",
                limit=5
            )
            if invoices:
                context.append(f"Recent Sales Invoices: {json.dumps(invoices, default=str)}")
        
        if any(word in query_lower for word in ["customer", "client"]):
            customers = frappe.get_list(
                "Customer",
                fields=["name", "customer_name", "territory"],
                limit=10
            )
            if customers:
                context.append(f"Customers: {json.dumps(customers, default=str)}")
        
        if any(word in query_lower for word in ["item", "product", "stock"]):
            items = frappe.get_list(
                "Item",
                fields=["name", "item_name", "stock_uom"],
                limit=10
            )
            if items:
                context.append(f"Items: {json.dumps(items, default=str)}")
        
        if any(word in query_lower for word in ["order", "purchase"]):
            orders = frappe.get_list(
                "Purchase Order",
                filters={"docstatus": ["<", 2]},
                fields=["name", "supplier", "grand_total", "status"],
                order_by="creation desc",
                limit=5
            )
            if orders:
                context.append(f"Purchase Orders: {json.dumps(orders, default=str)}")
        
        if any(word in query_lower for word in ["quotation", "quote", "cotización", "cotizacion"]):
            quotations = frappe.get_list(
                "Quotation",
                filters={"docstatus": ["<", 2]},
                fields=["name", "party_name", "grand_total", "status", "transaction_date", "valid_till"],
                order_by="creation desc",
                limit=10
            )
            if quotations:
                site_name = frappe.local.site
                for q in quotations:
                    q["link"] = f"https://{site_name}/app/quotation/{q['name']}"
                context.append(f"Quotations: {json.dumps(quotations, default=str)}")
        
        if any(word in query_lower for word in ["sales order", "orden de venta"]):
            sales_orders = frappe.get_list(
                "Sales Order",
                filters={"docstatus": ["<", 2]},
                fields=["name", "customer", "grand_total", "status", "transaction_date"],
                order_by="creation desc",
                limit=10
            )
            if sales_orders:
                site_name = frappe.local.site
                for so in sales_orders:
                    so["link"] = f"https://{site_name}/app/sales-order/{so['name']}"
                context.append(f"Sales Orders: {json.dumps(sales_orders, default=str)}")
        
        if any(word in query_lower for word in ["work order", "manufacturing", "production"]):
            work_orders = frappe.get_list(
                "Work Order",
                filters={"docstatus": ["<", 2]},
                fields=["name", "production_item", "qty", "status", "sales_order"],
                order_by="creation desc",
                limit=10
            )
            if work_orders:
                site_name = frappe.local.site
                for wo in work_orders:
                    wo["link"] = f"https://{site_name}/app/work-order/{wo['name']}"
                context.append(f"Work Orders: {json.dumps(work_orders, default=str)}")
        
        if any(word in query_lower for word in ["delivery", "shipping", "shipment"]):
            delivery_notes = frappe.get_list(
                "Delivery Note",
                filters={"docstatus": ["<", 2]},
                fields=["name", "customer", "grand_total", "status", "posting_date"],
                order_by="creation desc",
                limit=10
            )
            if delivery_notes:
                site_name = frappe.local.site
                for dn in delivery_notes:
                    dn["link"] = f"https://{site_name}/app/delivery-note/{dn['name']}"
                context.append(f"Delivery Notes: {json.dumps(delivery_notes, default=str)}")
        
        # Quality Inspection
        if any(word in query_lower for word in ["quality", "inspection", "qc", "inspeccion", "inspección", "calidad"]):
            inspections = frappe.get_list(
                "Quality Inspection",
                filters={"docstatus": ["<", 2]},
                fields=["name", "inspection_type", "reference_type", "reference_name", "status", "modified"],
                order_by="modified desc",
                limit=10
            )
            if inspections:
                site_name = frappe.local.site
                for qi in inspections:
                    qi["link"] = f"https://{site_name}/app/quality-inspection/{qi['name']}"
                context.append(f"Quality Inspections: {json.dumps(inspections, default=str)}")
            else:
                context.append("Quality Inspections: No records found")
        
        # TDS / Tax related to Sales Orders
        if any(word in query_lower for word in ["tds", "tax", "impuesto"]):
            # Get recent sales orders that might need TDS resolution
            sales_orders = frappe.get_list(
                "Sales Order",
                filters={"docstatus": ["<", 2]},
                fields=["name", "customer", "grand_total", "status", "taxes_and_charges"],
                order_by="creation desc",
                limit=10
            )
            if sales_orders:
                site_name = frappe.local.site
                for so in sales_orders:
                    so["link"] = f"https://{site_name}/app/sales-order/{so['name']}"
                context.append(f"Sales Orders (for TDS): {json.dumps(sales_orders, default=str)}")
        
        # Best selling / most sold items
        if any(word in query_lower for word in ["best sell", "most sold", "top sell", "vendido", "más vendido", "popular"]):
            try:
                top_items = frappe.db.sql("""
                    SELECT soi.item_code, soi.item_name, SUM(soi.qty) as total_qty, SUM(soi.amount) as total_amount
                    FROM `tabSales Order Item` soi
                    JOIN `tabSales Order` so ON soi.parent = so.name
                    WHERE so.docstatus = 1
                    GROUP BY soi.item_code, soi.item_name
                    ORDER BY total_qty DESC
                    LIMIT 10
                """, as_dict=True)
                if top_items:
                    context.append(f"Best Selling Items: {json.dumps(top_items, default=str)}")
            except Exception as e:
                context.append(f"Could not fetch best selling items: {str(e)}")
        
        # Customer-specific sales report
        customer_match = None
        for word in ["barentz", "legosan", "lorand"]:  # Add common customer names
            if word in query_lower:
                customer_match = word
                break
        
        if customer_match or any(word in query_lower for word in ["report", "reporte", "sales for"]):
            # Try to extract customer name from query
            if customer_match:
                customers = frappe.get_list(
                    "Customer",
                    filters={"name": ["like", f"%{customer_match}%"]},
                    fields=["name", "customer_name"],
                    limit=1
                )
                if customers:
                    customer_name = customers[0]["name"]
                    sales_data = frappe.get_list(
                        "Sales Order",
                        filters={"customer": customer_name, "docstatus": 1},
                        fields=["name", "grand_total", "transaction_date", "status"],
                        order_by="transaction_date desc",
                        limit=20
                    )
                    if sales_data:
                        site_name = frappe.local.site
                        for s in sales_data:
                            s["link"] = f"https://{site_name}/app/sales-order/{s['name']}"
                        context.append(f"Sales for {customer_name}: {json.dumps(sales_data, default=str)}")
        
        return "\n".join(context) if context else "No specific ERPNext data found for this query."
    
    def determine_autonomy(self, query: str) -> int:
        """Karpathy Protocol: Determine appropriate autonomy level"""
        query_lower = query.lower()
        
        # Level 3 keywords (dangerous operations)
        if any(word in query_lower for word in ["delete", "cancel", "submit", "create invoice", "payment"]):
            return 3
        
        # Level 2 keywords (modifications/workflow)
        if any(word in query_lower for word in ["update", "change", "modify", "set", "add", "convert", "create", "confirm"]):
            return 2
        
        # Default to Level 1 (read-only)
        return 1
    
    def execute_workflow_command(self, query: str) -> Optional[Dict]:
        """Parse and execute workflow commands"""
        frappe.logger().info(f"[Workflow] Checking query: {query}, WORKFLOWS_ENABLED: {WORKFLOWS_ENABLED}")
        
        if not WORKFLOWS_ENABLED:
            frappe.logger().info("[Workflow] Workflows disabled")
            return None
        
        query_lower = query.lower()
        executor = WorkflowExecutor(self.user)
        
        # Check for confirmation
        is_confirm = any(word in query_lower for word in ["confirm", "yes", "proceed", "do it", "execute"])
        
        # Force mode with ! prefix (like sudo)
        is_force = query.startswith("!")
        if is_force:
            is_confirm = True
            query = query.lstrip("!").strip()
            query_lower = query.lower()
        
        # Auto-confirm for privileged users (Sales Manager, etc.)
        privileged_roles = ["Sales Manager", "Manufacturing Manager", "Stock Manager", "Accounts Manager", "System Manager"]
        user_roles = frappe.get_roles(self.user)
        if any(role in user_roles for role in privileged_roles):
            is_confirm = True
        
        # Quotation patterns
        qtn_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
        frappe.logger().info(f"[Workflow] qtn_match: {qtn_match}, 'sales order' in query: {'sales order' in query_lower}")
        
        # Dry-run mode
        is_dry_run = "--dry-run" in query_lower or "dry run" in query_lower
        if is_dry_run:
            executor.dry_run = True
        
        # Complete workflow: Quotation → Invoice
        if qtn_match and "complete" in query_lower and ("workflow" in query_lower or "invoice" in query_lower):
            from raven_ai_agent.api.workflows import complete_workflow_to_invoice
            return complete_workflow_to_invoice(qtn_match.group(1).upper(), dry_run=is_dry_run)
        
        # Batch migration: multiple quotations
        batch_match = re.findall(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
        if len(batch_match) > 1 and ("batch" in query_lower or "migrate" in query_lower):
            return executor.batch_migrate_quotations([q.upper() for q in batch_match], dry_run=is_dry_run)
        
        # Submit quotation
        if qtn_match and "submit" in query_lower and "quotation" in query_lower:
            frappe.logger().info(f"[Workflow] Submitting quotation {qtn_match.group(1)}, confirm={is_confirm}")
            return executor.submit_quotation(qtn_match.group(1).upper(), confirm=is_confirm)
        
        # Quotation to Sales Order
        if qtn_match and "sales order" in query_lower:
            frappe.logger().info(f"[Workflow] Creating SO from {qtn_match.group(1)}, confirm={is_confirm}")
            return executor.create_sales_order_from_quotation(qtn_match.group(1).upper(), confirm=is_confirm)
        
        # Sales Order patterns - supports SAL-ORD-YYYY-NNNNN and SO-XXXXX-NAME formats
        so_match = re.search(r'(SAL-ORD-\d+-\d+|SO-[\w\-]+)', query, re.IGNORECASE)
        
        # Submit Sales Order
        if so_match and "submit" in query_lower and "sales order" in query_lower:
            return executor.submit_sales_order(so_match.group(1).upper(), confirm=is_confirm)
        
        # Sales Order to Work Order
        if so_match and "work order" in query_lower:
            return executor.create_work_orders_from_sales_order(so_match.group(1).upper(), confirm=is_confirm)
        
        # Stock Entry for Work Order
        wo_match = re.search(r'(MFG-WO-\d+|LOTE-\d+|P-VTA-\d+|WO-[^\s]+)', query, re.IGNORECASE)
        if wo_match and any(word in query_lower for word in ["stock entry", "material transfer", "manufacture"]):
            return executor.create_stock_entry_for_work_order(wo_match.group(1).upper(), confirm=is_confirm)
        
        # Delivery Note from Sales Order
        if so_match and any(word in query_lower for word in ["delivery", "ship", "deliver"]):
            return executor.create_delivery_note_from_sales_order(so_match.group(1).upper(), confirm=is_confirm)
        
        # Invoice from Delivery Note
        dn_match = re.search(r'(MAT-DN-\d+-\d+|DN-\d+)', query, re.IGNORECASE)
        if dn_match and "invoice" in query_lower:
            return executor.create_invoice_from_delivery_note(dn_match.group(1).upper(), confirm=is_confirm)
        
        # Workflow status
        if "workflow status" in query_lower or "track" in query_lower:
            q_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
            so_match = re.search(r'(SAL-ORD-\d+-\d+)', query, re.IGNORECASE)
            return executor.get_workflow_status(
                quotation_name=q_match.group(1).upper() if q_match else None,
                so_name=so_match.group(1).upper() if so_match else None
            )
        
        # BOM Creator: submit bom creator BOM-XXXX
        if "submit" in query_lower and "bom" in query_lower:
            bom_match = re.search(r'(BOM-[^\s]+)', query, re.IGNORECASE)
            if bom_match:
                bom_name = bom_match.group(1)
                # URL decode if needed (e.g., %2F -> /)
                import urllib.parse
                bom_name = urllib.parse.unquote(bom_name)
                
                from raven_ai_agent.agents.bom_creator_agent import submit_bom_creator
                result = submit_bom_creator(bom_name)
                if result.get("success"):
                    return {
                        "success": True,
                        "message": result.get("message", f"✅ BOM Creator '{bom_name}' submitted successfully!")
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("error", "Failed to submit BOM Creator")
                    }
        
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
                    wo_list = []
                    for wo in work_orders:
                        progress = f"{wo.produced_qty or 0}/{wo.qty}"
                        wo_link = f"https://{site_name}/app/work-order/{wo.name}"
                        wo_list.append(f"• **[{wo.name}]({wo_link})**\n   {wo.production_item} · {progress} · {wo.status}")
                    return {
                        "success": True,
                        "message": f"📋 **ACTIVE WORK ORDERS**\n\n" + "\n\n".join(wo_list)
                    }
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
        
        # ==================== BOM COMMANDS ====================
        
        # Show BOM details (all items)
        bom_match = re.search(r'(BOM-[^\s]+)', query, re.IGNORECASE)
        if bom_match and ("show" in query_lower or "details" in query_lower or "items" in query_lower or "view" in query_lower):
            try:
                from raven_ai_agent.api.bom_fixer import get_bom_details
                
                bom_name = bom_match.group(1)
                result = get_bom_details(bom_name)
                
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
        
        # ==================== DIRECT WEB SEARCH ====================
        
        # Direct web search that shows raw results
        if query_lower.startswith("search ") or query_lower.startswith("buscar "):
            try:
                # Extract search query
                search_query = query[7:].strip() if query_lower.startswith("search ") else query[7:].strip()
                # Remove brackets if present
                search_query = search_query.strip("[]")
                
                # Check if user wants to save results
                save_to_memory = "[save]" in query_lower or "[guardar]" in query_lower
                if save_to_memory:
                    search_query = search_query.replace("[save]", "").replace("[guardar]", "").strip()
                
                if len(search_query) > 2:
                    results = self.duckduckgo_search(search_query, max_results=8)
                    
                    if "No search results" in results or "Search error" in results:
                        return {
                            "success": False,
                            "message": f"🔍 **Web Search**: {search_query}\n\n{results}"
                        }
                    
                    # Save to memory if requested
                    save_msg = ""
                    if save_to_memory:
                        try:
                            import datetime
                            self.store_memory(
                                content=f"Search: {search_query}\n\n{results[:1500]}",
                                category="research",
                                importance="medium"
                            )
                            save_msg = "\n\n✅ *Saved to memory*"
                        except Exception as me:
                            save_msg = f"\n\n⚠️ Could not save: {str(me)}"
                    
                    footer = "\n\n---\n💡 Add `[save]` to save results to memory"
                    return {
                        "success": True,
                        "message": f"🔍 **Web Search**: {search_query}\n\n{results}{save_msg}{footer}"
                    }
                else:
                    return {
                        "success": True,
                        "message": "🔍 **Web Search**\n\nUsage: `@ai search [your query]`\n\nExample: `@ai search aloe acemannan suppliers China`\n\nAdd `[save]` to save results to memory"
                    }
                    
            except Exception as e:
                return {"success": False, "error": f"Search Error: {str(e)}"}
        
        # ==================== END DIRECT WEB SEARCH ====================
        
        # ==================== SALES-TO-PURCHASE CYCLE SOP ====================
        
        # Show Opportunities
        if "show opportunit" in query_lower or "list opportunit" in query_lower or "oportunidades" in query_lower:
            try:
                opportunities = frappe.get_list("Opportunity",
                    filters={"status": ["not in", ["Lost", "Closed"]]},
                    fields=["name", "party_name", "opportunity_amount", "status", "expected_closing", "sales_stage"],
                    order_by="modified desc",
                    limit=15
                )
                if opportunities:
                    site_name = frappe.local.site
                    opp_list = []
                    for opp in opportunities:
                        amt = f"${opp.opportunity_amount:,.2f}" if opp.opportunity_amount else "—"
                        opp_link = f"https://{site_name}/app/opportunity/{opp.name}"
                        opp_list.append(f"• **[{opp.name}]({opp_link})**\n   {opp.party_name} · {amt} · {opp.status}")
                    return {
                        "success": True,
                        "message": f"🎯 **SALES OPPORTUNITIES**\n\n" + "\n\n".join(opp_list)
                    }
                return {"success": True, "message": "No active opportunities found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Opportunity
        if "create opportunit" in query_lower or "crear oportunidad" in query_lower:
            customer_match = re.search(r'(?:for|para)\s+["\']?(.+?)["\']?\s*$', query, re.IGNORECASE)
            if customer_match:
                customer_name = customer_match.group(1).strip()
                try:
                    # Find customer
                    customer = frappe.db.get_value("Customer", {"customer_name": ["like", f"%{customer_name}%"]}, "name")
                    if not customer:
                        return {"success": False, "error": f"Customer '{customer_name}' not found. Create customer first."}
                    
                    if not is_confirm:
                        return {
                            "requires_confirmation": True,
                            "preview": f"🎯 CREATE OPPORTUNITY?\n\n  Customer: {customer}\n\nSay 'confirm' to proceed."
                        }
                    
                    opp = frappe.get_doc({
                        "doctype": "Opportunity",
                        "opportunity_from": "Customer",
                        "party_name": customer,
                        "status": "Open",
                        "sales_stage": "Prospecting"
                    })
                    opp.insert()
                    site_name = frappe.local.site
                    return {
                        "success": True,
                        "message": f"✅ Opportunity created: [{opp.name}](https://{site_name}/app/opportunity/{opp.name})"
                    }
                except Exception as e:
                    return {"success": False, "error": str(e)}
        
        # Check Inventory for Sales Order
        so_match = re.search(r'(SAL-ORD-\d+-\d+|SO-[^\s]+)', query, re.IGNORECASE)
        if so_match and ("check inventory" in query_lower or "verificar inventario" in query_lower or "disponibilidad" in query_lower):
            try:
                so_name = so_match.group(1)
                so = frappe.get_doc("Sales Order", so_name)
                items_status = []
                all_available = True
                for item in so.items:
                    available = frappe.db.get_value("Bin", 
                        {"item_code": item.item_code, "warehouse": item.warehouse},
                        "actual_qty") or 0
                    status = "✅" if available >= item.qty else "❌"
                    if available < item.qty:
                        all_available = False
                    items_status.append(f"  {status} {item.item_code}: Need {item.qty}, Available {available}")
                
                summary = "✅ All items available!" if all_available else "⚠️ Some items need to be purchased"
                return {
                    "success": True,
                    "message": f"📦 INVENTORY CHECK FOR {so_name}:\n{summary}\n\n" + "\n".join(items_status)
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Material Request from Sales Order
        if so_match and ("create material request" in query_lower or "crear solicitud de material" in query_lower):
            try:
                so_name = so_match.group(1)
                so = frappe.get_doc("Sales Order", so_name)
                
                # Check which items need purchasing
                items_to_request = []
                for item in so.items:
                    available = frappe.db.get_value("Bin", 
                        {"item_code": item.item_code, "warehouse": item.warehouse},
                        "actual_qty") or 0
                    if available < item.qty:
                        items_to_request.append({
                            "item_code": item.item_code,
                            "qty": item.qty - available,
                            "schedule_date": so.delivery_date or frappe.utils.nowdate(),
                            "warehouse": item.warehouse
                        })
                
                if not items_to_request:
                    return {"success": True, "message": f"✅ All items for {so_name} are in stock. No Material Request needed."}
                
                if not is_confirm:
                    items_preview = [f"  - {i['item_code']}: {i['qty']}" for i in items_to_request[:5]]
                    return {
                        "requires_confirmation": True,
                        "preview": f"📋 CREATE MATERIAL REQUEST FOR {so_name}?\n\nItems to purchase:\n" + "\n".join(items_preview) + "\n\nSay 'confirm' to proceed."
                    }
                
                mr = frappe.get_doc({
                    "doctype": "Material Request",
                    "material_request_type": "Purchase",
                    "schedule_date": so.delivery_date or frappe.utils.nowdate(),
                    "items": items_to_request
                })
                mr.insert()
                site_name = frappe.local.site
                return {
                    "success": True,
                    "message": f"✅ Material Request created: [{mr.name}](https://{site_name}/app/material-request/{mr.name})"
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Show Material Requests
        if "show material request" in query_lower or "list material request" in query_lower or "solicitudes de material" in query_lower:
            try:
                mrs = frappe.get_list("Material Request",
                    filters={"docstatus": ["<", 2], "status": ["not in", ["Stopped", "Cancelled"]]},
                    fields=["name", "material_request_type", "status", "schedule_date", "per_ordered"],
                    order_by="modified desc",
                    limit=15
                )
                if mrs:
                    site_name = frappe.local.site
                    mr_list = []
                    for mr in mrs:
                        ordered = f"{mr.per_ordered or 0:.0f}%"
                        mr_link = f"https://{site_name}/app/material-request/{mr.name}"
                        mr_list.append(f"• **[{mr.name}]({mr_link})**\n   {mr.material_request_type} · {mr.status} · Ordered: {ordered}")
                    return {
                        "success": True,
                        "message": f"📋 **MATERIAL REQUESTS**\n\n" + "\n\n".join(mr_list)
                    }
                return {"success": True, "message": "No pending material requests found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create RFQ from Material Request
        mr_match = re.search(r'(MAT-MR-\d+-\d+|MR-[^\s]+)', query, re.IGNORECASE)
        if mr_match and ("create rfq" in query_lower or "crear solicitud de cotizacion" in query_lower):
            try:
                mr_name = mr_match.group(1)
                mr = frappe.get_doc("Material Request", mr_name)
                
                if not is_confirm:
                    items_preview = [f"  - {i.item_code}: {i.qty}" for i in mr.items[:5]]
                    return {
                        "requires_confirmation": True,
                        "preview": f"📨 CREATE RFQ FROM {mr_name}?\n\nItems:\n" + "\n".join(items_preview) + "\n\n⚠️ You'll need to add suppliers after creation.\nSay 'confirm' to proceed."
                    }
                
                rfq = frappe.get_doc({
                    "doctype": "Request for Quotation",
                    "transaction_date": frappe.utils.nowdate(),
                    "items": [{
                        "item_code": item.item_code,
                        "qty": item.qty,
                        "schedule_date": item.schedule_date,
                        "warehouse": item.warehouse,
                        "material_request": mr_name,
                        "material_request_item": item.name
                    } for item in mr.items]
                })
                rfq.insert()
                site_name = frappe.local.site
                return {
                    "success": True,
                    "message": f"✅ RFQ created: [{rfq.name}](https://{site_name}/app/request-for-quotation/{rfq.name})\n\n⚠️ Add suppliers and send for quotation."
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Show RFQs
        if "show rfq" in query_lower or "list rfq" in query_lower or "solicitudes de cotizacion" in query_lower:
            try:
                rfqs = frappe.get_list("Request for Quotation",
                    filters={"docstatus": ["<", 2]},
                    fields=["name", "status", "transaction_date", "message_for_supplier"],
                    order_by="modified desc",
                    limit=15
                )
                if rfqs:
                    site_name = frappe.local.site
                    rfq_list = [f"• **[{r.name}](https://{site_name}/app/request-for-quotation/{r.name})**\n   {r.status} · {r.transaction_date}" for r in rfqs]
                    return {
                        "success": True,
                        "message": f"📨 **REQUEST FOR QUOTATIONS**\n\n" + "\n\n".join(rfq_list)
                    }
                return {"success": True, "message": "No RFQs found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Show Supplier Quotations
        if "show supplier quotation" in query_lower or "supplier quote" in query_lower or "cotizacion proveedor" in query_lower:
            try:
                sqs = frappe.get_list("Supplier Quotation",
                    filters={"docstatus": ["<", 2]},
                    fields=["name", "supplier", "grand_total", "status", "transaction_date"],
                    order_by="modified desc",
                    limit=15
                )
                if sqs:
                    site_name = frappe.local.site
                    sq_list = []
                    for sq in sqs:
                        amt = f"${sq.grand_total:,.2f}" if sq.grand_total else "—"
                        sq_link = f"https://{site_name}/app/supplier-quotation/{sq.name}"
                        sq_list.append(f"• **[{sq.name}]({sq_link})**\n   {sq.supplier} · {amt} · {sq.status}")
                    return {
                        "success": True,
                        "message": f"📄 **SUPPLIER QUOTATIONS**\n\n" + "\n\n".join(sq_list)
                    }
                return {"success": True, "message": "No supplier quotations found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Purchase Order from Supplier Quotation
        sq_match = re.search(r'(PUR-SQTN-\d+-\d+|SQ-[^\s]+)', query, re.IGNORECASE)
        if sq_match and ("create po" in query_lower or "create purchase order" in query_lower or "crear orden de compra" in query_lower):
            try:
                sq_name = sq_match.group(1)
                sq = frappe.get_doc("Supplier Quotation", sq_name)
                
                if not is_confirm:
                    items_preview = [f"  - {i.item_code}: {i.qty} @ ${i.rate:,.2f}" for i in sq.items[:5]]
                    return {
                        "requires_confirmation": True,
                        "preview": f"🛒 CREATE PURCHASE ORDER FROM {sq_name}?\n\n  Supplier: {sq.supplier}\n  Total: ${sq.grand_total:,.2f}\n\nItems:\n" + "\n".join(items_preview) + "\n\nSay 'confirm' to proceed."
                    }
                
                po = frappe.get_doc({
                    "doctype": "Purchase Order",
                    "supplier": sq.supplier,
                    "items": [{
                        "item_code": item.item_code,
                        "qty": item.qty,
                        "rate": item.rate,
                        "schedule_date": item.schedule_date or frappe.utils.add_days(frappe.utils.nowdate(), 7),
                        "warehouse": item.warehouse,
                        "supplier_quotation": sq_name,
                        "supplier_quotation_item": item.name
                    } for item in sq.items]
                })
                po.insert()
                site_name = frappe.local.site
                return {
                    "success": True,
                    "message": f"✅ Purchase Order created: [{po.name}](https://{site_name}/app/purchase-order/{po.name})"
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Show Purchase Orders
        if "show purchase order" in query_lower or "list purchase order" in query_lower or "ordenes de compra" in query_lower:
            try:
                pos = frappe.get_list("Purchase Order",
                    filters={"docstatus": ["<", 2]},
                    fields=["name", "supplier", "grand_total", "status", "per_received"],
                    order_by="modified desc",
                    limit=15
                )
                if pos:
                    site_name = frappe.local.site
                    po_list = []
                    for po in pos:
                        amt = f"${po.grand_total:,.2f}" if po.grand_total else "—"
                        received = f"{po.per_received or 0:.0f}%"
                        po_link = f"https://{site_name}/app/purchase-order/{po.name}"
                        po_list.append(f"• **[{po.name}]({po_link})**\n   {po.supplier} · {amt} · {po.status} · Rcvd: {received}")
                    return {
                        "success": True,
                        "message": f"🛒 **PURCHASE ORDERS**\n\n" + "\n\n".join(po_list)
                    }
                return {"success": True, "message": "No purchase orders found."}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Receive Goods (Purchase Receipt from PO)
        po_match = re.search(r'(PUR-ORD-\d+-\d+|PO-[^\s]+)', query, re.IGNORECASE)
        if po_match and ("receive goods" in query_lower or "recibir mercancia" in query_lower or "purchase receipt" in query_lower):
            try:
                po_name = po_match.group(1)
                po = frappe.get_doc("Purchase Order", po_name)
                
                # Check pending items
                pending_items = []
                for item in po.items:
                    pending = item.qty - (item.received_qty or 0)
                    if pending > 0:
                        pending_items.append({
                            "item_code": item.item_code,
                            "qty": pending,
                            "rate": item.rate,
                            "warehouse": item.warehouse,
                            "purchase_order": po_name,
                            "purchase_order_item": item.name
                        })
                
                if not pending_items:
                    return {"success": True, "message": f"✅ All items from {po_name} already received."}
                
                if not is_confirm:
                    items_preview = [f"  - {i['item_code']}: {i['qty']}" for i in pending_items[:5]]
                    return {
                        "requires_confirmation": True,
                        "preview": f"📥 RECEIVE GOODS FOR {po_name}?\n\n  Supplier: {po.supplier}\n\nPending Items:\n" + "\n".join(items_preview) + "\n\nSay 'confirm' to create Purchase Receipt."
                    }
                
                pr = frappe.get_doc({
                    "doctype": "Purchase Receipt",
                    "supplier": po.supplier,
                    "items": pending_items
                })
                pr.insert()
                site_name = frappe.local.site
                return {
                    "success": True,
                    "message": f"✅ Purchase Receipt created: [{pr.name}](https://{site_name}/app/purchase-receipt/{pr.name})\n\nVerify quantities and submit to update stock."
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Purchase Invoice from PO
        if po_match and ("create purchase invoice" in query_lower or "bill" in query_lower or "factura de compra" in query_lower):
            try:
                po_name = po_match.group(1)
                po = frappe.get_doc("Purchase Order", po_name)
                
                if not is_confirm:
                    return {
                        "requires_confirmation": True,
                        "preview": f"🧾 CREATE PURCHASE INVOICE FOR {po_name}?\n\n  Supplier: {po.supplier}\n  Total: ${po.grand_total:,.2f}\n\nSay 'confirm' to proceed."
                    }
                
                pi = frappe.get_doc({
                    "doctype": "Purchase Invoice",
                    "supplier": po.supplier,
                    "items": [{
                        "item_code": item.item_code,
                        "qty": item.qty,
                        "rate": item.rate,
                        "warehouse": item.warehouse,
                        "purchase_order": po_name
                    } for item in po.items]
                })
                pi.insert()
                site_name = frappe.local.site
                return {
                    "success": True,
                    "message": f"✅ Purchase Invoice created: [{pi.name}](https://{site_name}/app/purchase-invoice/{pi.name})"
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Delivery Note from Sales Order
        if so_match and ("create delivery" in query_lower or "ship" in query_lower or "deliver" in query_lower or "nota de entrega" in query_lower):
            try:
                so_name = so_match.group(1)
                so = frappe.get_doc("Sales Order", so_name)
                
                # Check pending items
                pending_items = []
                for item in so.items:
                    pending = item.qty - (item.delivered_qty or 0)
                    if pending > 0:
                        pending_items.append({
                            "item_code": item.item_code,
                            "qty": pending,
                            "rate": item.rate,
                            "warehouse": item.warehouse,
                            "against_sales_order": so_name,
                            "so_detail": item.name
                        })
                
                if not pending_items:
                    return {"success": True, "message": f"✅ All items from {so_name} already delivered."}
                
                if not is_confirm:
                    items_preview = [f"  - {i['item_code']}: {i['qty']}" for i in pending_items[:5]]
                    return {
                        "requires_confirmation": True,
                        "preview": f"🚚 CREATE DELIVERY NOTE FOR {so_name}?\n\n  Customer: {so.customer}\n\nItems to ship:\n" + "\n".join(items_preview) + "\n\nSay 'confirm' to proceed."
                    }
                
                dn = frappe.get_doc({
                    "doctype": "Delivery Note",
                    "customer": so.customer,
                    "items": pending_items
                })
                dn.insert()
                site_name = frappe.local.site
                return {
                    "success": True,
                    "message": f"✅ Delivery Note created: [{dn.name}](https://{site_name}/app/delivery-note/{dn.name})"
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Create Sales Invoice from SO or DN
        dn_match = re.search(r'(MAT-DN-\d+-\d+|DN-[^\s]+)', query, re.IGNORECASE)
        if (so_match or dn_match) and ("create sales invoice" in query_lower or "factura de venta" in query_lower or "invoice customer" in query_lower):
            try:
                if dn_match:
                    dn_name = dn_match.group(1)
                    dn = frappe.get_doc("Delivery Note", dn_name)
                    
                    if not is_confirm:
                        return {
                            "requires_confirmation": True,
                            "preview": f"🧾 CREATE SALES INVOICE FROM {dn_name}?\n\n  Customer: {dn.customer}\n  Total: ${dn.grand_total:,.2f}\n\nSay 'confirm' to proceed."
                        }
                    
                    si = frappe.get_doc({
                        "doctype": "Sales Invoice",
                        "customer": dn.customer,
                        "items": [{
                            "item_code": item.item_code,
                            "qty": item.qty,
                            "rate": item.rate,
                            "warehouse": item.warehouse,
                            "delivery_note": dn_name,
                            "dn_detail": item.name
                        } for item in dn.items]
                    })
                    si.insert()
                    site_name = frappe.local.site
                    return {
                        "success": True,
                        "message": f"✅ Sales Invoice created: [{si.name}](https://{site_name}/app/sales-invoice/{si.name})"
                    }
                elif so_match:
                    so_name = so_match.group(1)
                    so = frappe.get_doc("Sales Order", so_name)
                    
                    if not is_confirm:
                        return {
                            "requires_confirmation": True,
                            "preview": f"🧾 CREATE SALES INVOICE FROM {so_name}?\n\n  Customer: {so.customer}\n  Total: ${so.grand_total:,.2f}\n\nSay 'confirm' to proceed."
                        }
                    
                    si = frappe.get_doc({
                        "doctype": "Sales Invoice",
                        "customer": so.customer,
                        "items": [{
                            "item_code": item.item_code,
                            "qty": item.qty,
                            "rate": item.rate,
                            "warehouse": item.warehouse,
                            "sales_order": so_name,
                            "so_detail": item.name
                        } for item in so.items]
                    })
                    si.insert()
                    site_name = frappe.local.site
                    return {
                        "success": True,
                        "message": f"✅ Sales Invoice created: [{si.name}](https://{site_name}/app/sales-invoice/{si.name})"
                    }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # ==================== END SALES-TO-PURCHASE CYCLE SOP ====================
        
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
    
    def process_query(self, query: str, conversation_history: List[Dict] = None) -> Dict:
        """Main processing function"""
        
        query_lower = query.lower()
        
        # Handle help/capabilities command
        if any(h in query_lower for h in ["help", "capabilities", "what can you do", "que puedes hacer", "ayuda"]):
            return {
                "success": True,
                "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 1]\n{CAPABILITIES_LIST}",
                "autonomy_level": 1,
                "context_used": {"help": True}
            }
        
        # Determine autonomy level
        suggested_autonomy = self.determine_autonomy(query)
        
        # Try workflow command first (Level 2/3 operations)
        workflow_result = self.execute_workflow_command(query)
        if workflow_result:
            if workflow_result.get("requires_confirmation"):
                return {
                    "success": True,
                    "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 2]\n\n{workflow_result['preview']}",
                    "autonomy_level": 2,
                    "context_used": {"workflow": True}
                }
            elif workflow_result.get("success"):
                return {
                    "success": True,
                    "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 2]\n\n{workflow_result.get('message', 'Operation completed.')}",
                    "autonomy_level": 2,
                    "context_used": {"workflow": True}
                }
            elif workflow_result.get("error"):
                return {
                    "success": False,
                    "response": f"[CONFIDENCE: HIGH] [AUTONOMY: LEVEL 2]\n\n❌ Error: {workflow_result['error']}",
                    "autonomy_level": 2,
                    "context_used": {"workflow": True}
                }
        
        # Build context
        morning_briefing = self.get_morning_briefing()
        erpnext_context = self.get_erpnext_context(query)
        relevant_memories = self.search_memories(query)
        
        memories_text = "\n".join([f"- {m['content']}" for m in relevant_memories])
        
        # Build messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"## Context\n{morning_briefing}\n\n## ERPNext Data\n{erpnext_context}\n\n## Relevant Memories\n{memories_text}"}
        ]
        
        # Add conversation history
        if conversation_history:
            messages.extend(conversation_history[-10:])  # Last 10 messages
        
        # Add current query with autonomy context
        autonomy_warning = ""
        if suggested_autonomy >= 2:
            autonomy_warning = f"\n\n⚠️ This query suggests LEVEL {suggested_autonomy} autonomy. Please confirm before executing any changes. (Tip: Use `@ai !command` to skip confirmation)"
        
        messages.append({"role": "user", "content": query + autonomy_warning})
        
        # Call LLM
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.settings.get("max_tokens", 2000),
                temperature=0.3  # Lower temperature for accuracy
            )
            
            answer = response.choices[0].message.content
            
            # Extract facts to store (simple heuristic)
            if "[Stored:" in answer:
                # Parse and store facts
                pass
            
            return {
                "success": True,
                "response": answer,
                "autonomy_level": suggested_autonomy,
                "context_used": {
                    "memories": len(relevant_memories),
                    "erpnext_data": bool(erpnext_context)
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "response": f"[CONFIDENCE: UNCERTAIN]\n\nI encountered an error processing your request: {str(e)}"
            }
    
    def end_session(self, conversation: List[Dict]):
        """Lucy Protocol: Generate session summary"""
        if not conversation:
            return
        
        summary_prompt = "Summarize this conversation in 2-3 sentences, focusing on key decisions and information shared."
        
        messages = [
            {"role": "system", "content": summary_prompt},
            {"role": "user", "content": json.dumps(conversation[-20:], default=str)}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=200
            )
            
            summary = response.choices[0].message.content
            
            # Store summary
            doc = frappe.get_doc({
                "doctype": "AI Memory",
                "user": self.user,
                "content": summary,
                "importance": "High",
                "memory_type": "Summary",
                "source": "Session End"
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            
        except Exception:
            pass


@frappe.whitelist()
def process_message(message: str, conversation_history: str = None) -> Dict:
    """API endpoint for processing messages"""
    user = frappe.session.user
    agent = RaymondLucyAgent(user)
    
    history = json.loads(conversation_history) if conversation_history else []
    
    return agent.process_query(message, history)


@frappe.whitelist()
def handle_raven_message(doc, method):
    """Hook for Raven message integration - handles @ai and @bot_name mentions in any channel"""
    from bs4 import BeautifulSoup
    
    try:
        # Skip bot messages to avoid infinite loops
        if doc.is_bot_message:
            return
        
        if not doc.text:
            return
        
        # Strip HTML to get plain text (Raven wraps messages in <p> tags)
        plain_text = BeautifulSoup(doc.text, "html.parser").get_text().strip()
        
        frappe.logger().info(f"[AI Agent] Raw text: {doc.text[:100]}")
        frappe.logger().info(f"[AI Agent] Plain text: {plain_text[:100]}")
        
        query = None
        bot_name = None
        
        # Check for @ai trigger (now on plain text)
        if plain_text.lower().startswith("@ai"):
            query = plain_text[3:].strip()
            bot_name = "sales_order_bot"  # Default bot
        
        # Check for @sales_order_bot mention
        elif "sales_order_bot" in plain_text.lower():
            query = plain_text.replace("@sales_order_bot", "").strip()
            if not query:
                query = "help"  # Default if only mention
            bot_name = "sales_order_bot"
        
        # Check for @sales_order_follow_up bot
        elif "sales_order_follow_up" in plain_text.lower():
            query = plain_text.lower().replace("@sales_order_follow_up", "").strip()
            if not query:
                query = "help"
            bot_name = "sales_order_follow_up"
        
        if not query:
            return
        
        user = doc.owner
        frappe.logger().info(f"[AI Agent] Processing query from {user}: {query}")
        
        # Use ignore_permissions flag instead of switching user (avoids logout issue)
        original_ignore = frappe.flags.ignore_permissions
        try:
            frappe.flags.ignore_permissions = True
            
            # Route to specialized agent based on bot_name
            if bot_name == "sales_order_follow_up":
                from raven_ai_agent.agents import SalesOrderFollowupAgent
                so_agent = SalesOrderFollowupAgent(user)
                response = so_agent.process_command(query)
                result = {"success": True, "response": response}
            else:
                agent = RaymondLucyAgent(user)
                result = agent.process_query(query)
        finally:
            frappe.flags.ignore_permissions = original_ignore
        
        frappe.logger().info(f"[AI Agent] Result: success={result.get('success')}")
        
        # Get bot for proper message sending
        bot = None
        if bot_name:
            try:
                bot = frappe.get_doc("Raven Bot", bot_name)
            except frappe.DoesNotExistError:
                frappe.logger().warning(f"[AI Agent] Bot {bot_name} not found")
        
        response_text = result.get("response") or result.get("error") or "No response generated"
        
        if bot:
            # Use bot's send_message for proper integration
            bot.send_message(
                channel_id=doc.channel_id,
                text=response_text,
                markdown=True
            )
        else:
            # Fallback: create message directly
            reply_doc = frappe.get_doc({
                "doctype": "Raven Message",
                "channel_id": doc.channel_id,
                "text": response_text,
                "message_type": "Text",
                "is_bot_message": 1
            })
            reply_doc.insert(ignore_permissions=True)
            frappe.db.commit()
        
        frappe.logger().info(f"[AI Agent] Reply sent to channel {doc.channel_id}")
        
    except Exception as e:
        frappe.logger().error(f"[AI Agent] Error: {str(e)}")
        frappe.log_error(f"AI Agent Error: {str(e)}", "Raven AI Agent")
        try:
            error_doc = frappe.get_doc({
                "doctype": "Raven Message",
                "channel_id": doc.channel_id,
                "text": f"❌ Error: {str(e)}",
                "message_type": "Text",
                "is_bot_message": 1
            })
            error_doc.insert(ignore_permissions=True)
            frappe.db.commit()
        except:
            pass
