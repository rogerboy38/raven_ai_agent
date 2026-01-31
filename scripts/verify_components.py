"""
Raven AI Agent V10.0.0 - Diagnostic & Verification Script
Run in bench console: bench --site your-site console < scripts/verify_components.py

Or copy-paste sections into: bench --site your-site console
"""

import frappe

def print_header(title):
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def print_status(name, status, details=""):
    icon = "✅" if status else "❌"
    print(f"  {icon} {name}: {'OK' if status else 'MISSING'} {details}")

def verify_all():
    """Run all verification checks"""
    
    print_header("RAVEN AI AGENT V10.0.0 - COMPONENT VERIFICATION")
    
    # 1. Core Modules
    print_header("1. CORE MODULES")
    
    modules = [
        ("raven_ai_agent.api.agent", "V1 Agent API"),
        ("raven_ai_agent.api.agent_v2", "V2 Agent API (Multi-provider)"),
        ("raven_ai_agent.utils.memory", "Memory Manager"),
        ("raven_ai_agent.utils.cost_monitor", "Cost Monitor"),
    ]
    
    for module_path, name in modules:
        try:
            __import__(module_path)
            print_status(name, True)
        except ImportError as e:
            print_status(name, False, f"- {e}")
    
    # 2. LLM Providers
    print_header("2. LLM PROVIDERS")
    
    providers = [
        ("raven_ai_agent.providers.openai_provider", "OpenAI Provider"),
        ("raven_ai_agent.providers.deepseek", "DeepSeek Provider"),
        ("raven_ai_agent.providers.claude", "Claude Provider"),
        ("raven_ai_agent.providers.minimax", "MiniMax Provider"),
    ]
    
    for module_path, name in providers:
        try:
            __import__(module_path)
            print_status(name, True)
        except ImportError as e:
            print_status(name, False, f"- {e}")
    
    # 3. Gateway & Channels
    print_header("3. GATEWAY & CHANNELS")
    
    gateway_modules = [
        ("raven_ai_agent.gateway.session_manager", "Session Manager"),
        ("raven_ai_agent.gateway.router", "Message Router"),
        ("raven_ai_agent.channels.whatsapp", "WhatsApp Adapter"),
        ("raven_ai_agent.channels.telegram", "Telegram Adapter"),
        ("raven_ai_agent.channels.slack", "Slack Adapter"),
    ]
    
    for module_path, name in gateway_modules:
        try:
            __import__(module_path)
            print_status(name, True)
        except ImportError as e:
            print_status(name, False, f"- {e}")
    
    # 4. Voice & Skills
    print_header("4. VOICE & SKILLS")
    
    extra_modules = [
        ("raven_ai_agent.voice.elevenlabs", "ElevenLabs Voice"),
        ("raven_ai_agent.skills.browser", "Browser Skill"),
    ]
    
    for module_path, name in extra_modules:
        try:
            __import__(module_path)
            print_status(name, True)
        except ImportError as e:
            print_status(name, False, f"- {e}")
    
    # 5. DocType Settings
    print_header("5. FRAPPE DOCTYPES")
    
    try:
        settings = frappe.get_single("AI Agent Settings")
        print_status("AI Agent Settings DocType", True)
        
        # Check configured providers
        print("\n  Configured Settings:")
        print(f"    - Default Provider: {getattr(settings, 'default_provider', 'Not Set')}")
        print(f"    - Model: {getattr(settings, 'model', 'Not Set')}")
        print(f"    - Max Tokens: {getattr(settings, 'max_tokens', 'Not Set')}")
        
        # Check API Keys (without revealing them)
        api_keys = {
            "OpenAI": hasattr(settings, 'openai_api_key') and bool(settings.get_password('openai_api_key', raise_exception=False)),
            "DeepSeek": hasattr(settings, 'deepseek_api_key') and bool(settings.get_password('deepseek_api_key', raise_exception=False)),
            "Claude": hasattr(settings, 'claude_api_key') and bool(settings.get_password('claude_api_key', raise_exception=False)),
            "MiniMax": hasattr(settings, 'minimax_api_key') and bool(settings.get_password('minimax_api_key', raise_exception=False)),
            "ElevenLabs": hasattr(settings, 'elevenlabs_api_key') and bool(settings.get_password('elevenlabs_api_key', raise_exception=False)),
        }
        
        print("\n  API Keys Status:")
        for provider, configured in api_keys.items():
            icon = "🔑" if configured else "⚪"
            status = "Configured" if configured else "Not Set"
            print(f"    {icon} {provider}: {status}")
            
    except Exception as e:
        print_status("AI Agent Settings DocType", False, f"- {e}")
        print("\n  ⚠️  You may need to create the DocType or run migrations")
    
    # 6. Memory Table
    print_header("6. MEMORY STORAGE")
    
    try:
        count = frappe.db.count("AI Agent Memory") if frappe.db.table_exists("AI Agent Memory") else 0
        print_status("AI Agent Memory Table", True, f"({count} memories stored)")
    except Exception as e:
        print_status("AI Agent Memory Table", False, f"- {e}")
    
    # 7. Test Basic Functionality
    print_header("7. FUNCTIONAL TESTS")
    
    # Test Provider Factory
    try:
        from raven_ai_agent.providers import get_provider
        print_status("Provider Factory", True)
    except Exception as e:
        print_status("Provider Factory", False, f"- {e}")
    
    # Test Session Manager
    try:
        from raven_ai_agent.gateway import session_manager
        print_status("Session Manager Instance", True)
    except Exception as e:
        print_status("Session Manager Instance", False, f"- {e}")
    
    # Test Message Router
    try:
        from raven_ai_agent.gateway import message_router
        route = message_router.route("show my pending invoices")
        print_status("Message Router", True, f"(routes to: {route.handler})")
    except Exception as e:
        print_status("Message Router", False, f"- {e}")
    
    # Test Channel Factory
    try:
        from raven_ai_agent.channels import get_channel_adapter
        print_status("Channel Adapter Factory", True)
    except Exception as e:
        print_status("Channel Adapter Factory", False, f"- {e}")
    
    # Summary
    print_header("SUMMARY")
    print("""
  To complete setup:
  
  1. Configure API Keys in AI Agent Settings:
     - Go to: /app/ai-agent-settings
     - Add at least one LLM API key (OpenAI/DeepSeek/Claude/MiniMax)
  
  2. Test with @ai in Raven:
     - @ai help
     - @ai What are my pending invoices?
  
  3. (Optional) Configure channels:
     - WhatsApp: Add phone_number_id, access_token, verify_token
     - Telegram: Add bot_token
     - Slack: Add bot_token, signing_secret
  
  4. (Optional) Configure voice:
     - Add ElevenLabs API key for TTS responses
""")

# Run verification
if __name__ == "__main__":
    verify_all()
else:
    # When pasted in console
    verify_all()
