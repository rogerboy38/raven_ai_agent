# TECHNICAL SPECIFICATION: app_migrator AI Agent

## 1. OVERVIEW

| Field | Value |
|-------|-------|
| **Project Name** | app_migrator |
| **Type** | Bench CLI Application with AI Agent Integration |
| **Purpose** | Automate complex Frappe/ERPNext site migrations, domain changes, and server transfers with AI-assisted troubleshooting |

---

## 2. CORE FUNCTIONALITIES

### 2.1 Migration Scenarios Covered

- ✅ Domain/Rename Migrations (e.g., old.cloud → new.domain)
- ✅ Server Transfers (Frappe Cloud → Self-hosted/VPS)
- ✅ Database Restoration & Verification
- ✅ Multi-Site Management & Conflict Resolution
- ✅ Redis Configuration & Conflict Resolution
- ✅ Nginx/Traefik Proxy Configuration
- ✅ SSL Certificate Management

### 2.2 AI Agent Capabilities

```
┌─────────────────────────────────────────────────────────────┐
│                     AI AGENT ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────┤
│ 1. DIAGNOSTIC MODULE                                        │
│    • Auto-detect bench version & command syntax             │
│    • Identify running processes & conflicts                 │
│    • Detect configuration mismatches                        │
│    • Redis/Database connectivity checks                     │
│                                                             │
│ 2. PROBLEM-SOLVING MODULE                                   │
│    • Pattern recognition from error messages                │
│    • Historical solution database                           │
│    • Step-by-step guided fixes                              │
│    • Rollback capabilities on failure                       │
│                                                             │
│ 3. AUTOMATION MODULE                                        │
│    • Safe process termination & cleanup                     │
│    • Configuration file management                          │
│    • Dependency resolution                                  │
│    • Validation & verification                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. TECHNICAL ARCHITECTURE

### 3.1 Command Structure

```bash
bench migrator <command> [options]

Commands:
  analyze-site          Analyze current site configuration
  rename-domain        Change domain and update all configs
  transfer-server      Migrate site to new server
  fix-config           Auto-fix configuration issues
  verify-migration     Validate migration success
  cleanup              Remove orphaned files/processes
  rollback             Revert last migration
```

### 3.2 Configuration File Schema

```json
{
  "migration_profile": {
    "source": {
      "domain": "old.cloud",
      "server_ip": "xxx.xxx.xxx.xxx",
      "bench_path": "/home/frappe/frappe-bench",
      "bench_version": "5.29.0"
    },
    "target": {
      "domain": "new.domain",
      "server_ip": "yyy.yyy.yyy.yyy",
      "bench_path": "/home/frappe/frappe-bench"
    },
    "database": {
      "backup_file": "backup.sql.gz",
      "restore_method": "bench_restore|manual"
    },
    "services": {
      "redis": "local|docker|external",
      "proxy": "nginx|traefik|caddy",
      "ssl": "letsencrypt|self-signed|none"
    }
  }
}
```

---

## 4. AI AGENT MODULES

### 4.1 Diagnostic Engine

```python
class DiagnosticEngine:
    def analyze_environment(self):
        """Comprehensive system analysis"""
        checks = [
            self.check_bench_version(),
            self.check_running_processes(),
            self.check_port_conflicts(),
            self.check_directory_structure(),
            self.check_configuration_files(),
            self.check_database_connectivity(),
            self.check_redis_status(),
            self.check_proxy_configuration()
        ]
        return self.generate_diagnostic_report(checks)
    
    def identify_problem_patterns(self, error_logs):
        """Match errors with known solutions"""
        patterns = {
            "Address already in use": "port_conflict",
            "does not exist": "site_misconfiguration", 
            "ModuleNotFoundError": "missing_app",
            "Bad Gateway": "proxy_misconfiguration",
            "Redis connection failed": "redis_issue"
        }
        return self.classify_issues(error_logs, patterns)
```

### 4.2 Solution Database

```python
SOLUTION_DATABASE = {
    "port_conflict": {
        "detection": "Port 8000 is in use",
        "solution_steps": [
            "Identify process using port: `sudo lsof -i :8000`",
            "Terminate conflicting process",
            "Verify port is free",
            "Restart service"
        ],
        "validation": "Port 8000 accepts connections",
        "risk_level": "low"
    },
    "site_misconfiguration": {
        "detection": "Site domain not recognized",
        "solution_steps": [
            "Check sites.txt file",
            "Verify hosts file in site directory",
            "Update site_config.json host_name",
            "Update common_site_config.json",
            "Restart bench serve"
        ],
        "validation": "Site loads with new domain",
        "risk_level": "medium"
    },
    "redis_docker_conflict": {
        "detection": "Multiple Redis instances running",
        "solution_steps": [
            "Identify all Redis processes",
            "Stop Docker Redis containers if conflicting",
            "Configure local Redis ports",
            "Update common_site_config.json",
            "Test Redis connections"
        ],
        "validation": "Redis responds on correct ports",
        "risk_level": "high"
    }
}
```

### 4.3 Automated Migration Workflow

```python
class MigrationWorkflow:
    def execute_migration(self, profile):
        """Orchestrate complete migration"""
        steps = [
            self.pre_migration_checks(profile),
            self.backup_current_state(profile),
            self.stop_services_safely(profile),
            self.update_configurations(profile),
            self.handle_domain_changes(profile),
            self.resolve_dependencies(profile),
            self.start_services(profile),
            self.verify_migration(profile),
            self.cleanup_old_files(profile)
        ]
        
        for step in steps:
            result = self.execute_with_rollback(step)
            if not result.success:
                return self.rollback_migration(step)
        
        return MigrationResult(success=True)
```

---

## 5. INTEGRATION POINTS

### 5.1 Bench CLI Integration

```python
# Integration with existing bench commands
@click.command()
@click.option('--source-domain', required=True)
@click.option('--target-domain', required=True)
@click.option('--interactive/--no-interactive', default=True)
def migrate_domain(source_domain, target_domain, interactive):
    """AI-assisted domain migration"""
    
    # Initialize AI agent
    agent = MigrationAgent()
    
    # Analyze current state
    analysis = agent.analyze_site(source_domain)
    
    if interactive:
        agent.present_findings(analysis)
        if not click.confirm('Proceed with migration?'):
            return
    
    # Execute migration
    result = agent.execute_domain_migration(
        source_domain, 
        target_domain
    )
    
    # Present results
    agent.present_results(result)
```

### 5.2 Error Recovery System

```python
class ErrorRecovery:
    def handle_failure(self, error, context):
        """Intelligent error recovery"""
        
        # Classify error
        error_type = self.classify_error(error)
        
        # Get recovery strategy
        strategy = self.get_recovery_strategy(error_type, context)
        
        # Execute recovery
        if strategy['type'] == 'automatic':
            return self.execute_automatic_recovery(strategy)
        elif strategy['type'] == 'guided':
            return self.prompt_guided_recovery(strategy)
        elif strategy['type'] == 'rollback':
            return self.execute_rollback(strategy)
        
    def classify_error(self, error_message):
        """Categorize errors for appropriate handling"""
        classifications = {
            'configuration': [
                'does not exist',
                'invalid configuration',
                'host not found'
            ],
            'service': [
                'failed to start',
                'connection refused',
                'address already in use'
            ],
            'dependency': [
                'module not found',
                'import error',
                'missing dependency'
            ],
            'permission': [
                'permission denied',
                'access denied',
                'not authorized'
            ]
        }
        
        for category, patterns in classifications.items():
            if any(pattern in error_message for pattern in patterns):
                return category
        
        return 'unknown'
```

---

## 6. SAFETY FEATURES

### 6.1 Pre-Migration Validation

```python
VALIDATION_CHECKS = [
    {
        "name": "database_backup",
        "check": "verify_backup_exists",
        "critical": True,
        "failure_message": "No backup found. Create backup before migration."
    },
    {
        "name": "disk_space",
        "check": "verify_disk_space",
        "critical": True,
        "failure_message": "Insufficient disk space for migration."
    },
    {
        "name": "service_dependencies",
        "check": "verify_services_running",
        "critical": False,
        "failure_message": "Some services not running (may be intentional)."
    }
]
```

### 6.2 Rollback System

```python
class RollbackManager:
    def __init__(self):
        self.checkpoints = []
    
    def create_checkpoint(self, description, data):
        """Save state before risky operation"""
        checkpoint = {
            'timestamp': datetime.now(),
            'description': description,
            'data': data,
            'backup_files': self.backup_critical_files()
        }
        self.checkpoints.append(checkpoint)
    
    def execute_rollback(self, checkpoint_index):
        """Revert to previous state"""
        checkpoint = self.checkpoints[checkpoint_index]
        
        steps = [
            self.restore_files(checkpoint['backup_files']),
            self.restore_database(checkpoint['data'].get('db_state')),
            self.restore_configurations(checkpoint['data'].get('configs')),
            self.cleanup_temp_files()
        ]
        
        return all(steps)
```

---

## 7. OUTPUT & REPORTING

### 7.1 Migration Report

```json
{
  "migration_report": {
    "summary": {
      "status": "success|partial|failed",
      "duration": "HH:MM:SS",
      "domain_changed": "old.cloud → new.domain"
    },
    "steps_completed": [
      {
        "step": "pre_migration_checks",
        "status": "completed",
        "duration": "00:02:15",
        "issues_found": 2,
        "issues_resolved": 2
      }
    ],
    "configuration_changes": {
      "files_modified": ["site_config.json", "common_site_config.json"],
      "services_restarted": ["redis", "bench-serve"],
      "dns_updates_required": true
    },
    "verification_results": {
      "site_accessible": true,
      "https_working": true,
      "database_connected": true,
      "redis_functional": true
    },
    "next_steps": [
      "Update DNS records if changed",
      "Monitor error logs for 24 hours",
      "Test critical business workflows"
    ]
  }
}
```

---

## 8. INSTALLATION & USAGE

### 8.1 Installation

```bash
# Install as bench app
bench get-app app_migrator
bench --site all install-app app_migrator

# Or as standalone CLI
pip install frappe-migrator
```

### 8.2 Basic Usage Examples

```bash
# Analyze current site
bench migrator analyze-site --site mysite.cloud

# Rename domain
bench migrator rename-domain \
  --source old.cloud \
  --target new.domain \
  --interactive

# Full server migration
bench migrator transfer-server \
  --source-server 192.168.1.100 \
  --target-server 192.168.1.200 \
  --backup-file /path/to/backup.sql.gz

# Fix common issues
bench migrator fix-config --auto-fix
```

---

## 9. TECHNICAL REQUIREMENTS

### 9.1 Dependencies

- Python 3.8+
- Frappe Framework 14+
- Redis client libraries
- MySQL/MariaDB client
- Docker SDK (optional, for Docker detection)

### 9.2 Supported Bench Versions

- Bench v5.x (new command structure)
- Bench v4.x (legacy support)
- Frappe Cloud compatible

### 9.3 Security Considerations

- No storage of passwords/credentials
- Local processing only (optional cloud sync)
- Audit logging for all changes
- Permission verification before modifications

---

## 10. ROADMAP & ENHANCEMENTS

### Phase 1 (Core)
- Basic domain migration
- Configuration file management
- Error detection & basic recovery

### Phase 2 (Advanced)
- Multi-site migration
- Docker container management
- Cloud provider integrations (AWS, GCP, Azure)

### Phase 3 (AI Enhancement)
- Predictive issue detection
- Machine learning for solution optimization
- Natural language troubleshooting
- Community knowledge base integration

---

## Summary

This specification provides a comprehensive framework for building an AI-powered migration assistant that encapsulates all the complex troubleshooting we just performed manually. The system would learn from each migration, building a knowledge base to handle increasingly complex scenarios autonomously.

---

*Document generated based on successful migration: old.cloud → v2.sysmayal.cloud*
*Reference: https://v2.sysmayal.cloud (IP: 187.77.2.74)*
