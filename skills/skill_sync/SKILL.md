---
name: skill-sync
description: >
  Syncs skill metadata to AGENTS.md Auto-invoke sections.
  Trigger: When updating skill metadata, regenerating Auto-invoke tables.
license: MIT
metadata:
  author: AMB-Wellness
  version: "1.0"
  scope: [root]
  auto_invoke:
    - "After creating/modifying a skill"
    - "Regenerate AGENTS.md Auto-invoke tables"
    - "Troubleshoot why a skill is missing from AGENTS.md auto-invoke"
allowed-tools: Read, Edit, Write, Bash
---

# Skill Sync

Keeps AGENTS.md Auto-invoke sections in sync with skill metadata. Adapted from [Prowler](https://github.com/prowler-cloud/prowler).

## Required Skill Metadata

Each skill needs these fields in `metadata`:

```yaml
metadata:
  author: AMB-Wellness
  version: "1.0"
  scope: [root, skills]           # Which AGENTS.md files to update
  auto_invoke:
    - "Creating migration fixes"   # Actions that trigger this skill
    - "Validating FoxPro data"
```

### Scope Values

| Scope | Updates |
|-------|---------|
| `root` | `raven_ai_agent/AGENTS.md` (repo root) |
| `skills` | `raven_ai_agent/raven_ai_agent/skills/AGENTS.md` |
| `api` | `raven_ai_agent/raven_ai_agent/api/AGENTS.md` |
| `providers` | `raven_ai_agent/raven_ai_agent/providers/AGENTS.md` |

Skills can have multiple scopes: `scope: [root, skills]`

## Usage

```bash
./raven_ai_agent/raven_ai_agent/skills/skill_sync/assets/sync.sh
```

## What It Does

1. Reads all `skills/*/SKILL.md` files
2. Extracts `metadata.scope` and `metadata.auto_invoke`
3. Generates Auto-invoke tables for each AGENTS.md
4. Updates the `### Auto-invoke Skills` section

## Commands

```bash
# Sync all AGENTS.md files
./raven_ai_agent/raven_ai_agent/skills/skill_sync/assets/sync.sh

# Dry run (show what would change)
./raven_ai_agent/raven_ai_agent/skills/skill_sync/assets/sync.sh --dry-run
```
