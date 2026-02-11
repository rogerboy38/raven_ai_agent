"""
Webhook API for Raven AI Agent
Provides remote management capabilities including git operations
"""
import frappe
import subprocess
import os
from pathlib import Path
from typing import Dict


@frappe.whitelist()
def git_pull(app_name: str = "raven_ai_agent", branch: str = "main") -> Dict:
    """
    Pull latest changes from git for the specified app.
    
    Args:
        app_name: Name of the app to update (default: raven_ai_agent)
        branch: Git branch to pull from (default: main)
    
    Returns:
        Dict with status and details
    """
    # Security: Only allow pulling raven_ai_agent
    allowed_apps = ["raven_ai_agent"]
    if app_name not in allowed_apps:
        return {
            "success": False,
            "error": f"App '{app_name}' not allowed. Allowed: {allowed_apps}"
        }
    
    bench_path = Path(os.getenv('BENCH_PATH', '/home/frappe/frappe-bench'))
    app_path = bench_path / 'apps' / app_name
    
    if not app_path.exists():
        return {
            "success": False,
            "error": f"App path not found: {app_path}"
        }
    
    try:
        # Fetch first
        fetch_result = subprocess.run(
            ['git', 'fetch', 'origin', branch],
            cwd=app_path,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Get current commit before pull
        before_commit = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=app_path,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        # Pull changes
        pull_result = subprocess.run(
            ['git', 'pull', 'origin', branch],
            cwd=app_path,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        # Get new commit after pull
        after_commit = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=app_path,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        if pull_result.returncode == 0:
            # Get list of changes
            changes = []
            if before_commit != after_commit:
                log_result = subprocess.run(
                    ['git', 'log', '--oneline', f'{before_commit}..{after_commit}'],
                    cwd=app_path,
                    capture_output=True,
                    text=True
                )
                changes = log_result.stdout.strip().split('\n') if log_result.stdout.strip() else []
            
            return {
                "success": True,
                "app": app_name,
                "branch": branch,
                "before_commit": before_commit,
                "after_commit": after_commit,
                "updated": before_commit != after_commit,
                "changes": changes,
                "message": pull_result.stdout.strip() or "Already up to date"
            }
        else:
            return {
                "success": False,
                "error": pull_result.stderr.strip() or pull_result.stdout.strip(),
                "app": app_name
            }
            
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Git operation timed out"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def git_status(app_name: str = "raven_ai_agent") -> Dict:
    """
    Get git status for the specified app.
    
    Returns current branch, commit, and any uncommitted changes.
    """
    allowed_apps = ["raven_ai_agent"]
    if app_name not in allowed_apps:
        return {
            "success": False,
            "error": f"App '{app_name}' not allowed"
        }
    
    bench_path = Path(os.getenv('BENCH_PATH', '/home/frappe/frappe-bench'))
    app_path = bench_path / 'apps' / app_name
    
    if not app_path.exists():
        return {
            "success": False,
            "error": f"App path not found: {app_path}"
        }
    
    try:
        # Get current branch
        branch_result = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=app_path,
            capture_output=True,
            text=True
        )
        
        # Get current commit
        commit_result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=app_path,
            capture_output=True,
            text=True
        )
        
        # Get commit message
        msg_result = subprocess.run(
            ['git', 'log', '-1', '--pretty=%s'],
            cwd=app_path,
            capture_output=True,
            text=True
        )
        
        # Check for uncommitted changes
        status_result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=app_path,
            capture_output=True,
            text=True
        )
        
        # Get remote URL
        remote_result = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            cwd=app_path,
            capture_output=True,
            text=True
        )
        
        return {
            "success": True,
            "app": app_name,
            "branch": branch_result.stdout.strip(),
            "commit": commit_result.stdout.strip(),
            "commit_message": msg_result.stdout.strip(),
            "has_uncommitted_changes": bool(status_result.stdout.strip()),
            "uncommitted_changes": status_result.stdout.strip().split('\n') if status_result.stdout.strip() else [],
            "remote_url": remote_result.stdout.strip()
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def ping() -> Dict:
    """Simple ping endpoint to test connectivity."""
    return {
        "success": True,
        "message": "pong",
        "app": "raven_ai_agent"
    }
