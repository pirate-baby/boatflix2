#!/bin/bash

# Boatflix Auto-Deploy Script
# This script pulls from git and redeploys changed services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

LOG_FILE="${LOG_FILE:-$SCRIPT_DIR/deploy.log}"
LOCK_FILE="/tmp/boatflix-deploy.lock"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Check if another deploy is running
if [ -f "$LOCK_FILE" ]; then
    log "Deploy already in progress (lock file exists)"
    exit 0
fi

# Create lock file
touch "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

log "Starting deploy check..."

# Fetch latest changes
git fetch origin main 2>&1 | tee -a "$LOG_FILE"

# Check if there are new commits
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    log "No changes detected, skipping deploy"
    exit 0
fi

log "New changes detected! Local: $LOCAL, Remote: $REMOTE"

# Get list of changed files
CHANGED_FILES=$(git diff --name-only HEAD origin/main)
log "Changed files:"
echo "$CHANGED_FILES" | tee -a "$LOG_FILE"

# Pull the changes
log "Pulling changes..."
git pull origin main 2>&1 | tee -a "$LOG_FILE"

# Determine which services need rebuilding
REBUILD_SERVICES=()
RESTART_ALL=false

# Check if docker-compose.yml changed - requires full restart
if echo "$CHANGED_FILES" | grep -q "^docker-compose.yml$"; then
    log "docker-compose.yml changed - full restart required"
    RESTART_ALL=true
fi

# Check if .env changed - requires full restart
if echo "$CHANGED_FILES" | grep -q "^.env$"; then
    log ".env changed - full restart required"
    RESTART_ALL=true
fi

# Check for service-specific changes
if echo "$CHANGED_FILES" | grep -q "^fastapi-manager/"; then
    log "fastapi-manager changed - will rebuild"
    REBUILD_SERVICES+=("manager")
fi

if echo "$CHANGED_FILES" | grep -q "^qbittorrentvpn/"; then
    log "qbittorrentvpn changed - will rebuild"
    REBUILD_SERVICES+=("qbittorrentvpn")
fi

if echo "$CHANGED_FILES" | grep -q "^nginx/"; then
    log "nginx config changed - will restart nginx"
    REBUILD_SERVICES+=("nginx")
fi

# If config directories changed, restart affected services
if echo "$CHANGED_FILES" | grep -q "^configs/"; then
    log "Config files changed - full restart required"
    RESTART_ALL=true
fi

# Perform deployment
if [ "$RESTART_ALL" = true ]; then
    log "Performing full restart..."
    docker compose down 2>&1 | tee -a "$LOG_FILE"
    docker compose build 2>&1 | tee -a "$LOG_FILE"
    docker compose up -d 2>&1 | tee -a "$LOG_FILE"
    log "Full restart complete"
elif [ ${#REBUILD_SERVICES[@]} -gt 0 ]; then
    log "Rebuilding services: ${REBUILD_SERVICES[*]}"

    # Build changed services
    for service in "${REBUILD_SERVICES[@]}"; do
        log "Building $service..."
        docker compose build "$service" 2>&1 | tee -a "$LOG_FILE"
    done

    # Restart changed services
    log "Restarting services: ${REBUILD_SERVICES[*]}"
    docker compose up -d "${REBUILD_SERVICES[@]}" 2>&1 | tee -a "$LOG_FILE"
    log "Service restart complete"
else
    log "No service-specific changes detected, performing safe restart..."
    docker compose up -d 2>&1 | tee -a "$LOG_FILE"
    log "Restart complete"
fi

# Show running containers
log "Current running containers:"
docker compose ps 2>&1 | tee -a "$LOG_FILE"

log "Deploy complete!"
