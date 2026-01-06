# Raven AI Agent

Raymond-Lucy AI Agent for ERPNext with Raven Integration.

## Features

- **Raymond Protocol**: Anti-hallucination with verified ERPNext data
- **Memento Protocol**: Persistent memory storage across sessions
- **Lucy Protocol**: Context continuity with morning briefings
- **Karpathy Protocol**: Autonomy slider (Copilot → Command → Agent)

## Installation

```bash
bench get-app https://github.com/your-repo/raven_ai_agent
bench --site your-site install-app raven_ai_agent
```

## Configuration

1. Go to **AI Agent Settings** in ERPNext
2. Enter your OpenAI API Key
3. Configure autonomy levels and memory retention

## Usage

### In Raven
Type `@ai` followed by your question:
```
@ai What are my pending sales invoices?
@ai Show me top customers by revenue
```

### Via API
```python
from raven_ai_agent.api.agent import process_message

result = process_message("What invoices are due this week?")
print(result["response"])
```

## Autonomy Levels

| Level | Name | Description |
|-------|------|-------------|
| 1 | Copilot | Read-only queries, suggestions |
| 2 | Command | Execute specific operations with confirmation |
| 3 | Agent | Multi-step autonomous workflows |

## License

MIT
