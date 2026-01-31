# Raven AI Agent V10.0.0 - Diagnostic Script
# Run: bench --site sysmayal2.v.frappe.cloud console
# Then paste this script or run: exec(open('/home/frappe/frappe-bench/apps/raven_ai_agent/raven_ai_agent/scripts/verify_components.py').read())

import frappe

print("\n" + "="*60)
print("  RAVEN AI AGENT V10.0.0 - COMPONENT VERIFICATION")
print("="*60)

# 1. Core Modules
print("\n[1] CORE MODULES")
modules = [
    ("raven_ai_agent.api.agent", "V1 Agent API"),
    ("raven_ai_agent.api.agent_v2", "V2 Agent API"),
    ("raven_ai_agent.utils.memory", "Memory Manager"),
    ("raven_ai_agent.utils.cost_monitor", "Cost Monitor"),
]
for path, name in modules:
    try:
        __import__(path)
        print(f"  ✅ {name}")
    except ImportError as e:
        print(f"  ❌ {name}: {e}")

# 2. LLM Providers
print("\n[2] LLM PROVIDERS")
providers = [
    ("raven_ai_agent.providers.openai_provider", "OpenAI"),
    ("raven_ai_agent.providers.deepseek", "DeepSeek"),
    ("raven_ai_agent.providers.claude", "Claude"),
    ("raven_ai_agent.providers.minimax", "MiniMax"),
]
for path, name in providers:
    try:
        __import__(path)
        print(f"  ✅ {name}")
    except ImportError as e:
        print(f"  ❌ {name}: {e}")

# 3. Gateway & Channels
print("\n[3] GATEWAY & CHANNELS")
gateway = [
    ("raven_ai_agent.gateway.session_manager", "Session Manager"),
    ("raven_ai_agent.gateway.router", "Message Router"),
    ("raven_ai_agent.channels.whatsapp", "WhatsApp"),
    ("raven_ai_agent.channels.telegram", "Telegram"),
    ("raven_ai_agent.channels.slack", "Slack"),
]
for path, name in gateway:
    try:
        __import__(path)
        print(f"  ✅ {name}")
    except ImportError as e:
        print(f"  ❌ {name}: {e}")

# 4. Voice & Skills
print("\n[4] VOICE & SKILLS")
extras = [
    ("raven_ai_agent.voice.elevenlabs", "ElevenLabs Voice"),
    ("raven_ai_agent.skills.browser", "Browser Skill"),
]
for path, name in extras:
    try:
        __import__(path)
        print(f"  ✅ {name}")
    except ImportError as e:
        print(f"  ❌ {name}: {e}")

# 5. Settings DocType
print("\n[5] FRAPPE SETTINGS")
try:
    s = frappe.get_single("AI Agent Settings")
    print(f"  ✅ AI Agent Settings DocType found")
    print(f"     Default Provider: {getattr(s, 'default_provider', 'Not Set')}")
    print(f"     Model: {getattr(s, 'model', 'Not Set')}")
except Exception as e:
    print(f"  ❌ AI Agent Settings: {e}")

# 6. Router Test
print("\n[6] FUNCTIONAL TEST")
try:
    from raven_ai_agent.gateway import message_router
    route = message_router.route("show pending invoices")
    print(f"  ✅ Router: 'show pending invoices' -> {route.handler}")
except Exception as e:
    print(f"  ❌ Router: {e}")

print("\n" + "="*60)
print("  DONE - Configure API keys in AI Agent Settings to enable LLMs")
print("="*60 + "\n")
