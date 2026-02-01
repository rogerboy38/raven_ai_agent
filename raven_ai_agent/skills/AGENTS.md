# Skills Directory Guidelines

> For skill patterns, read the relevant [SKILL.md](skills/{skill-name}/SKILL.md)

## Available Skills

| Skill | Description | URL |
|-------|-------------|-----|
| `migration-fixer` | FoxPro → ERPNext migration validation and repair | [SKILL.md](migration_fixer/SKILL.md) |
| `skill-creator` | Create new AI agent skills | [SKILL.md](skill_creator/SKILL.md) |
| `skill-sync` | Sync skill metadata to AGENTS.md | [SKILL.md](skill_sync/SKILL.md) |

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

---

## Creating New Skills

1. Use `skill-creator` skill for guidance
2. Add `metadata.scope` and `metadata.auto_invoke` fields
3. Run `skill-sync` to update Auto-invoke tables
