# Sandbox Tree Structure
Generated: 2026-02-14

## Key Import Paths

The Frappe app has a nested structure:

```
raven_ai_agent/                          # Root app folder
├── raven_ai_agent/                      # Python package (import from here)
│   ├── skills/
│   │   └── formulation_orchestrator/
│   │       └── skill.py                 # <-- ACTUAL import path
│   └── ...
├── skills/                              # Development copy (NOT imported)
│   └── formulation_orchestrator/
│       └── skill.py
└── ...
```

**Import Path:** `from raven_ai_agent.skills.formulation_orchestrator.skill import FormulationOrchestratorSkill`

**Resolves to:** `raven_ai_agent/raven_ai_agent/skills/formulation_orchestrator/skill.py`

## Full Tree
See: user_input_files/pasted-text-2026-02-14T01-52-09.txt
