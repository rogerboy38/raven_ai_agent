---
name: skill-creator
description: >
  Creates new skills for RaymondLucyAgent following the agentskills.io standard.
  Trigger: When creating a new skill, adding agent capabilities, or setting up skill structure.
license: MIT
metadata:
  author: AMB-Wellness
  version: "1.0"
  scope: [root, skills]
  auto_invoke:
    - "Creating new skills"
    - "Adding agent capabilities"
    - "Setting up skill structure"
allowed-tools: Read, Edit, Write, Bash
---

# Skill Creator

## CRITICAL RULES
- **ALWAYS** create SKILL.md with proper frontmatter
- **ALWAYS** export SKILL_CLASS in __init__.py
- **ALWAYS** inherit from SkillBase
- **NEVER** modify framework.py for individual skills

---

## Directory Structure

```
raven_ai_agent/skills/{skill_name}/
├── __init__.py           # Exports SKILL_CLASS
├── skill.py              # SkillBase implementation
├── SKILL.md              # Documentation (agentskills.io format)
└── [optional files]      # Additional modules
```

---

## Step-by-Step Creation

### 1. Create Directory
```bash
mkdir -p raven_ai_agent/skills/{skill_name}
```

### 2. Create SKILL.md
```yaml
---
name: {skill-name}
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

# Skill Name

## CRITICAL RULES
- ALWAYS do X
- NEVER do Y

## Commands
...
```

### 3. Create skill.py
```python
from raven_ai_agent.skills.framework import SkillBase
from typing import Dict, Optional


class {SkillName}Skill(SkillBase):
    """
    Skill description.
    """
    
    name = "{skill-name}"
    description = "What this skill does"
    emoji = "🔧"
    version = "1.0.0"
    priority = 50  # 0-100, higher = checked first
    
    # Simple keyword triggers
    triggers = [
        "keyword1",
        "keyword2",
        "phrase to match"
    ]
    
    # Regex patterns (optional, for complex matching)
    patterns = [
        r"pattern\s+\d+",
        r"another.*pattern"
    ]
    
    def __init__(self, agent=None):
        super().__init__(agent)
        # Initialize any resources
    
    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """
        Handle a query if this skill can process it.
        
        Returns:
            None if skill doesn't handle this query
            Dict with response if handled
        """
        query_lower = query.lower()
        
        # Check if we should handle this
        if "keyword1" in query_lower:
            result = self._do_something(query)
            return {
                "handled": True,
                "response": result,
                "confidence": 0.9,
                "data": {}  # Optional extra data
            }
        
        return None
    
    def _do_something(self, query: str) -> str:
        """Internal method to process query"""
        return f"Processed: {query}"


# REQUIRED: Export for auto-discovery
SKILL_CLASS = {SkillName}Skill
```

### 4. Create __init__.py
```python
from raven_ai_agent.skills.{skill_name}.skill import {SkillName}Skill

SKILL_CLASS = {SkillName}Skill

__all__ = ["{SkillName}Skill", "SKILL_CLASS"]
```

### 5. Update AGENTS.md (Optional)
Add to Auto-invoke table if needed.

---

## Skill Response Format

```python
{
    "handled": True,           # Required: Did skill handle the query?
    "response": str,           # Required: Response to show user
    "confidence": float,       # Optional: 0.0-1.0 confidence score
    "data": Any               # Optional: Extra data for further processing
}
```

---

## Best Practices

1. **Concise**: Only include what AI doesn't already know
2. **Progressive**: Point to docs, don't duplicate
3. **Critical first**: Lead with ALWAYS/NEVER rules
4. **Minimal examples**: Show patterns, not tutorials
5. **High priority**: Set priority > 50 for important skills

---

## Testing Your Skill

```python
# Direct skill test
from raven_ai_agent.skills.{skill_name} import SKILL_CLASS

skill = SKILL_CLASS()
result = skill.handle("test query")
print(result)

# Via agent
from raven_ai_agent.api.agent_v2 import RaymondLucyAgentV2

agent = RaymondLucyAgentV2(user="Administrator")
result = agent.process_query("test query")
print(result)

# Check skill was used
print(result.get("skill_used"))
```

---

## Template Files

See `assets/` folder for complete templates:
- `skill_template.py` - Full skill class template
- `init_template.py` - __init__.py template
- `skill_md_template.md` - SKILL.md template
