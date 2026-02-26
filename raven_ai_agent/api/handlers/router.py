"""
Router - Message handling and bot routing

Contains the @frappe.whitelist() entry points:
- process_message: API endpoint for processing messages
- handle_raven_message: Webhook handler for Raven messages with bot routing
"""
import frappe
import json
from typing import Optional, Dict, List

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
        
        # Check for @rnd_bot
        elif "rnd_bot" in plain_text.lower():
            query = plain_text.lower().replace("@rnd_bot", "").strip()
            if not query:
                query = "help"
            bot_name = "rnd_bot"
        
        # Check for @executive bot
        elif "executive" in plain_text.lower():
            query = plain_text.lower().replace("@executive", "").strip()
            if not query:
                query = "helicopter"  # Default to helicopter view
            bot_name = "executive"

        # Check for @iot bot
        elif "iot" in plain_text.lower():
            query = plain_text.lower().replace("@iot", "").strip()
            if not query:
                query = "help"
            bot_name = "iot"
        
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
            elif bot_name == "rnd_bot":
                from raven_ai_agent.agents import RnDAgent
                rnd_agent = RnDAgent(user)
                response = rnd_agent.process_command(query)
                result = {"success": True, "response": response}
            elif bot_name == "executive":
                from raven_ai_agent.agents.executive_agent import ExecutiveAgent
                exec_agent = ExecutiveAgent(user)
                response = exec_agent.process_command(query)
                result = {"success": True, "response": response}
            elif bot_name == "iot":
                from raven_ai_agent.agents.iot_agent import IoTAgent
                iot_agent = IoTAgent(user)
                result = iot_agent.process_command(query)
            else:
                # Try SkillRouter first for specialized skills (formulation, etc.)
                try:
                    from raven_ai_agent.skills.router import SkillRouter
                    router = SkillRouter()
                    router_result = router.route(query)
                    if router_result and router_result.get("handled"):
                        result = {"success": True, "response": router_result.get("response", "Skill executed.")}
                    else:
                        # Fallback to general agent
                        agent = RaymondLucyAgent(user)
                        result = agent.process_query(query)
                except ImportError:
                    frappe.logger().warning("[AI Agent] SkillRouter not available, using default agent")
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
        
        response_text = result.get("response") or result.get("message") or result.get("error") or "No response generated"
        link_doctype = result.get("link_doctype")
        link_document = result.get("link_document")
        
        if bot:
            bot.send_message(
                channel_id=doc.channel_id,
                text=response_text,
                markdown=True,
                link_doctype=link_doctype,
                link_document=link_document
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
            
            # Publish realtime event to notify frontend clients
            publish_message_created_event(reply_doc, doc.channel_id)
            frappe.logger().info(f"[AI Agent] Published realtime event for channel {doc.channel_id}")
        
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
            
            # Publish realtime event for error message too
            publish_message_created_event(error_doc, doc.channel_id)
        except:
            pass
