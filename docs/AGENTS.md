# Repository Guidelines - raven_ai_agent

## How to Use This Guide
- Start here for project norms and skill discovery
- Each skill has a `SKILL.md` with detailed patterns
- Skills auto-invoke based on query patterns

## Available Skills

### ERPNext/Migration Skills
| Skill | Description | Trigger Patterns |
|-------|-------------|------------------|
| `migration-fixer` | FoxPro → ERPNext migration validation and repair | scan migration, fix folio, compare folio |
| `browser` | Web browsing and automation | browse, search web, open url |

### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Suggesting formulations from inventory | `formulation-advisor` |
| Finding batches that match TDS | `formulation-advisor` |
| Blending cuñetes for target specs | `formulation-advisor` |
| Optimizing raw material selection | `formulation-advisor` |
| Scanning migration status | `migration-fixer` |
| Fixing quotation data | `migration-fixer` |
| Comparing FoxPro vs ERPNext | `migration-fixer` |
| Generating migration reports | `migration-fixer` |
| Creating new skills | `skill-creator` |
| Adding agent capabilities | `skill-creator` |
| Setting up skill structure | `skill-creator` |
| After creating/modifying a skill | `skill-sync` |
| Regenerate AGENTS.md Auto-invoke tables | `skill-sync` |
| Troubleshoot why a skill is missing from AGENTS.md auto-invoke | `skill-sync` |

---

## Project Structure

```
raven_ai_agent/
├── api/                    # Frappe API endpoints
│   ├── agent.py           # V1 Agent (original)
│   └── agent_v2.py        # V2 Agent with multi-provider + skills
├── providers/             # LLM Providers
│   ├── openai.py
│   ├── deepseek.py
│   ├── claude.py
│   ├── minimax.py
│   └── ollama.py
├── skills/                # Dynamic Skill System
│   ├── framework.py       # SkillBase, Registry, Router, Learner
│   ├── browser/           # Web browsing skill
│   └── migration_fixer/   # FoxPro migration skill
├── config/                # DocType configurations
├── gateway/               # Raven integration
├── utils/                 # Utilities
│   └── cost_monitor.py
└── channels/              # Communication channels
```

---

## Skill System Architecture

```
┌─────────────────────────────────────────────┐
│              RaymondLucyAgentV2             │
│  ┌────────────────────────────────────┐     │
│  │         process_query()            │     │
│  │  1. Try Skills (SkillRouter)       │     │
│  │  2. Fallback to LLM if no match    │     │
│  └────────────────────────────────────┘     │
│                    │                        │
│         ┌─────────▼──────────┐              │
│         │    SkillRouter     │              │
│         │  (auto-learning)   │              │
│         └─────────┬──────────┘              │
│                   │                         │
│    ┌──────────────▼──────────────┐          │
│    │      SkillRegistry          │          │
│    │   (auto-discovers skills)   │          │
│    └──────────────┬──────────────┘          │
│                   │                         │
│    ┌──────────────▼──────────────┐          │
│    │         skills/             │          │
│    │  ├── migration_fixer/       │          │
│    │  ├── browser/               │          │
│    │  └── [future skills...]     │          │
│    └─────────────────────────────┘          │
└─────────────────────────────────────────────┘
```

---

## Creating New Skills

### Quick Start
```bash
# 1. Create skill directory
mkdir -p raven_ai_agent/skills/my_skill

# 2. Create required files
touch raven_ai_agent/skills/my_skill/__init__.py
touch raven_ai_agent/skills/my_skill/skill.py
touch raven_ai_agent/skills/my_skill/SKILL.md
```

### SKILL.md Format (agentskills.io standard)
```yaml
---
name: my-skill
description: >
  What this skill does.
  Trigger: When user asks about X, Y, or Z.
license: MIT
metadata:
  author: your-name
  version: "1.0"
  scope: [root]
  auto_invoke:
    - "Doing X"
    - "Processing Y"
allowed-tools: Read, Edit, Write, Bash
---

## Detailed Instructions
...
```

### Skill Class Template
```python
from raven_ai_agent.skills.framework import SkillBase

class MySkill(SkillBase):
    name = "my-skill"
    description = "What this skill does"
    emoji = "🔧"
    priority = 50
    
    triggers = ["keyword1", "keyword2"]
    patterns = [r"regex\s+pattern"]
    
    def handle(self, query: str, context=None):
        if self._matches_query(query):
            return {
                "handled": True,
                "response": "Result...",
                "confidence": 0.9
            }
        return None

SKILL_CLASS = MySkill
```

---

## Development Commands

```bash
# Test skill routing
from raven_ai_agent.api.agent_v2 import route_to_skill
route_to_skill("scan migration 2024")

# List available skills
from raven_ai_agent.skills import list_available_skills
list_available_skills()

# Test full agent
from raven_ai_agent.api.agent_v2 import RaymondLucyAgentV2
agent = RaymondLucyAgentV2(user="Administrator")
agent.process_query("scan migration 2024")
```

---

## Provider Configuration

| Provider | Config Key | Model Options |
|----------|------------|---------------|
| OpenAI | `openai_api_key` | gpt-4o, gpt-4o-mini |
| DeepSeek | `deepseek_api_key` | deepseek-chat, deepseek-reasoner |
| Claude | `claude_api_key` | claude-3-5-sonnet |
| MiniMax | `minimax_cp_key` | MiniMax-M2.1 |
| Ollama | `ollama_base_url` | llama3.1:8b |

---

## Design Principles

1. **Skills First**: Try specialized skills before falling back to LLM
2. **Auto-Discovery**: Skills in `skills/` are automatically found
3. **Learning**: SkillLearner improves routing over time
4. **Extensible**: Add new skills without modifying core code
5. **Concise**: Skills contain only what AI doesn't already know
