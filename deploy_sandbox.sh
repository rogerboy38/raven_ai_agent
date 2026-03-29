#!/bin/bash
# Deploy fix/bug83-clean-v2 to sandbox

set -e

cd /workspace/raven_ai_agent

echo "=== Deploying raven_ai_agent to sandbox ==="

# SSH and deploy
ssh -o StrictHostKeyChecking=no root@sandbox.sysmayal.cloud << 'ENDSSH'
    cd /home/frappe/frappe-bench
    
    # Pull latest from fix/bug83-clean-v2
    cd apps/raven_ai_agent
    git fetch origin
    git checkout fix/bug83-clean-v2
    git pull origin fix/bug83-clean-v2
    
    # Restart services
    echo "Restarting services..."
    bench restart
    supervisorctl restart frappe:frappe-bench-frappe-web
    supervisorctl restart frappe:frappe-bench-frappe-socketio
    
    echo "=== Deployment complete ==="
    echo "Testing connection..."
    bench --site sandbox.sysmayal.cloud execute frappe.ping
ENDSSH

echo "Done!"