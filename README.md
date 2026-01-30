# Raven AI Agent

Raymond-Lucy AI Agent for ERPNext with Raven Integration - Enhanced with OpenClaw-inspired architecture.

## Features

### Core Protocols
- **Raymond Protocol**: Anti-hallucination with verified ERPNext data
- **Memento Protocol**: Persistent memory storage across sessions
- **Lucy Protocol**: Context continuity with morning briefings
- **Karpathy Protocol**: Autonomy slider (Copilot → Command → Agent)

### Multi-Provider LLM Support
| Provider | Models | Features |
|----------|--------|----------|
| **OpenAI** | gpt-4o, gpt-4o-mini, gpt-4-turbo | Default provider |
| **DeepSeek** | deepseek-chat, deepseek-reasoner | Cost-effective, reasoning mode |
| **Claude** | claude-3-5-sonnet, claude-3-opus | Strong analysis |
| **MiniMax** | abab6.5-chat, abab5.5-chat | Multilingual |

### Multi-Channel Gateway *(NEW)*
- **WhatsApp Business API**: Full messaging + interactive buttons
- **Telegram Bot**: Messages, voice, inline keyboards
- **Slack**: Direct messages, app mentions, button actions
- **Session Management**: Cross-channel context preservation

### Voice Integration *(NEW)*
- **ElevenLabs TTS**: Text-to-speech responses
- **Multiple Voices**: Rachel, Drew, Bella, and more
- **Auto Voice Detection**: Respond with voice when appropriate

### Skills Platform *(NEW)*
- **Browser Control**: Web automation and data extraction
- **Extensible Architecture**: Easy to add new skills
- **Intent Routing**: Automatic skill matching

### Cost Monitoring
- **Usage Tracking**: Per-user token consumption
- **Budget Alerts**: Warnings when approaching limits

## Comparison: raven_ai_agent vs OpenClaw

| Feature | raven_ai_agent | OpenClaw |
|---------|---------------|----------|
| **Integration** | Frappe/Raven + Multi-channel | Multi-channel only |
| **Architecture** | Gateway + Session Management | Gateway/WebSocket |
| **AI Backend** | OpenAI + DeepSeek + Claude + MiniMax | Claude + OpenAI + local |
| **Channels** | WhatsApp, Telegram, Slack, Raven | WhatsApp, Telegram, Slack |
| **Voice** | ElevenLabs TTS | ElevenLabs |
| **Skills** | Browser control, extensible | Browser, canvas, device |
| **Cost Monitor** | ✅ Built-in | ❌ |
| **ERPNext Native** | ✅ | ❌ |

## Installation

```bash
bench get-app https://github.com/your-repo/raven_ai_agent
bench --site your-site install-app raven_ai_agent
```

## Configuration

### AI Agent Settings
1. Go to **AI Agent Settings** in ERPNext
2. Select **Default Provider** and enter API keys
3. Set **Fallback Provider** for automatic failover
4. Configure **Cost Budget** for usage warnings

### Channel Configuration (Optional)
```python
# WhatsApp
whatsapp_config = {
    "phone_number_id": "YOUR_ID",
    "access_token": "YOUR_TOKEN",
    "verify_token": "YOUR_VERIFY_TOKEN"
}

# Telegram
telegram_config = {"bot_token": "YOUR_BOT_TOKEN"}

# Slack  
slack_config = {
    "bot_token": "xoxb-YOUR-TOKEN",
    "signing_secret": "YOUR_SECRET"
}
```

### Voice Configuration (Optional)
```python
voice_config = {
    "elevenlabs_api_key": "YOUR_KEY",
    "default_voice": "rachel"
}
```

## Usage

### In Raven
```
@ai What are my pending sales invoices?
@ai Show me top customers by revenue
```

### Via API
```python
from raven_ai_agent.api.agent_v2 import process_message_v2

result = process_message_v2("What invoices are due?")
result = process_message_v2("Analyze data", provider="claude")
```

### Multi-Channel
```python
from raven_ai_agent.channels import get_channel_adapter
from raven_ai_agent.gateway import session_manager

adapter = get_channel_adapter("whatsapp", config)
incoming = adapter.parse_webhook(payload)
session = session_manager.get_or_create_session(user_id, "whatsapp", incoming.channel_user_id)
```

### Voice
```python
from raven_ai_agent.voice import ElevenLabsVoice

tts = ElevenLabsVoice(api_key="YOUR_KEY")
audio = tts.text_to_speech("Hello!")
```

## Autonomy Levels

| Level | Name | Description |
|-------|------|-------------|
| 1 | Copilot | Read-only queries, suggestions |
| 2 | Command | Execute with confirmation |
| 3 | Agent | Multi-step autonomous workflows |

## Architecture

```
raven_ai_agent/
├── api/
│   ├── agent.py           # V1 API
│   └── agent_v2.py        # V2 API (Multi-provider)
├── providers/             # LLM Providers
│   ├── openai_provider.py
│   ├── deepseek.py
│   ├── claude.py
│   └── minimax.py
├── gateway/               # Multi-channel control
│   ├── session_manager.py
│   └── router.py
├── channels/              # Channel adapters
│   ├── whatsapp.py
│   ├── telegram.py
│   └── slack.py
├── voice/                 # Voice integration
│   └── elevenlabs.py
├── skills/                # Extensible skills
│   └── browser.py
└── utils/
    ├── memory.py
    └── cost_monitor.py
```

## License

MIT
