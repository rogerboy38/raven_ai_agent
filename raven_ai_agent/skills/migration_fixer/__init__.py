# Migration Fixer Skill for raven_ai_agent
# Handles FoxPro -> ERPNext migration validation and fixes

from raven_ai_agent.skills.migration_fixer.fixer import (
    MigrationFixer,
    scan_migration,
    fix_folio
)

from raven_ai_agent.skills.migration_fixer.api import (
    scan_folios,
    validate_folio,
    preview_fix,
    apply_fix,
    bulk_preview,
    bulk_apply,
    compare_folio,
    get_migration_report,
    get_foxpro_data,
    handle_migration_command
)

__all__ = [
    "MigrationFixer",
    "scan_migration",
    "fix_folio",
    "scan_folios",
    "validate_folio",
    "preview_fix", 
    "apply_fix",
    "bulk_preview",
    "bulk_apply",
    "compare_folio",
    "get_migration_report",
    "get_foxpro_data",
    "handle_migration_command"
]
