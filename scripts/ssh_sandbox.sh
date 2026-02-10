#!/bin/bash
# SSH to sandbox and run commands

SSHPASS='PpeFra27'
SSH_HOST='ftpuser@2.tcp.ngrok.io'
SSH_PORT='12932'
SSH_OPTS='-o PreferredAuthentications=password -o PubkeyAuthentication=no -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'

# Command to run remotely
REMOTE_CMD="$1"

sshpass -p "$SSHPASS" ssh $SSH_OPTS -p $SSH_PORT $SSH_HOST "$REMOTE_CMD"
