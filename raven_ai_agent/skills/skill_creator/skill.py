"""Skill Creator - Meta-skill for creating new skills."""
import os
import re
from pathlib import Path
from ..framework import SkillBase

SKILL_TEMPLATE = '''---
name: {name}
description: {description}
version: 1.0.0
author: AMB-Wellness
metadata:
  auto_invoke:
{triggers_yaml}
  scope: general
  category: custom
---

# {title}

{description}

## Commands

| Command | Description |
|---------|-------------|
| `{name} help` | Show help for this skill |

## Usage

```
# Example usage
{name} help
```
'''

SKILL_PY_TEMPLATE = '''"""Skill: {title}"""
from ..framework import SkillBase


class {class_name}(SkillBase):
    """Skill implementation for {name}."""
    
    name = "{name}"
    description = "{description}"
    triggers = {triggers}
    
    def can_handle(self, query: str) -> bool:
        query_lower = query.lower()
        return any(t in query_lower for t in self.triggers)
    
    def execute(self, query: str, context: dict = None) -> dict:
        return {{
            "status": "success",
            "skill": self.name,
            "message": f"Executed {name} skill",
            "query": query
        }}
'''

INIT_TEMPLATE = '''from .skill import {class_name}

__all__ = ["{class_name}"]
'''


class SkillCreatorSkill(SkillBase):
    """Meta-skill for creating new skills."""
    
    name = "skill-creator"
    description = "Create new skills following the established patterns"
    triggers = ["create skill", "new skill", "add skill", "generate skill"]
    
    def __init__(self):
        self.skills_dir = Path(__file__).parent.parent
    
    def can_handle(self, query: str) -> bool:
        query_lower = query.lower()
        return any(t in query_lower for t in self.triggers)
    
    def execute(self, query: str, context: dict = None) -> dict:
        # Parse the skill name from query
        match = re.search(r'(?:create|new|add|generate)\s+skill\s+["\']?(\w+)["\']?', query, re.I)
        if not match:
            return {
                "status": "error",
                "message": "Please specify a skill name. Example: 'create skill my_skill'"
            }
        
        skill_name = match.group(1).lower()
        description = context.get("description", f"Custom skill: {skill_name}") if context else f"Custom skill: {skill_name}"
        triggers = context.get("triggers", [skill_name]) if context else [skill_name]
        
        return self.create_skill(skill_name, description, triggers)
    
    def create_skill(self, name: str, description: str, triggers: list) -> dict:
        """Create a new skill with the given parameters."""
        skill_dir = self.skills_dir / name
        
        if skill_dir.exists():
            return {
                "status": "error",
                "message": f"Skill '{name}' already exists at {skill_dir}"
            }
        
        # Create directory
        skill_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate class name
        class_name = "".join(word.capitalize() for word in name.split("_")) + "Skill"
        title = " ".join(word.capitalize() for word in name.split("_"))
        
        # Generate triggers YAML
        triggers_yaml = "\n".join(f'    - "{t}"' for t in triggers)
        
        # Write SKILL.md
        skill_md = SKILL_TEMPLATE.format(
            name=name,
            description=description,
            title=title,
            triggers_yaml=triggers_yaml
        )
        (skill_dir / "SKILL.md").write_text(skill_md)
        
        # Write skill.py
        skill_py = SKILL_PY_TEMPLATE.format(
            name=name,
            description=description,
            title=title,
            class_name=class_name,
            triggers=triggers
        )
        (skill_dir / "skill.py").write_text(skill_py)
        
        # Write __init__.py
        init_py = INIT_TEMPLATE.format(class_name=class_name)
        (skill_dir / "__init__.py").write_text(init_py)
        
        return {
            "status": "success",
            "message": f"Created skill '{name}' at {skill_dir}",
            "files": [
                str(skill_dir / "SKILL.md"),
                str(skill_dir / "skill.py"),
                str(skill_dir / "__init__.py")
            ]
        }
