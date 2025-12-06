#!/bin/bash
# Boatflix2 Witty Pi 4 - After Startup Script
# This script runs after the Raspberry Pi boots up via Witty Pi 4
#
# Location: /home/boatflix/wittypi/afterStartup.sh
# Reference: https://github.com/uugear/Witty-Pi-4/tree/main/Software/wittypi

# Configuration
BOATFLIX_DIR="/home/boatflix/boatflix2"
MEDIA_MOUNT="/mnt/media"
LOG_FILE="/var/log/boatflix2-wittypi.log"
DOCKER_COMPOSE_FILE="$BOATFLIX_DIR/docker-compose.yml"
RCLONE_CONFIG="$BOATFLIX_DIR/rclone.conf"
ENV_FILE="$BOATFLIX_DIR/.env"

# Network wait configuration
MAX_NETWORK_WAIT=120  # seconds
NETWORK_CHECK_INTERVAL=5

# Logging function
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$timestamp [STARTUP] $*" >> "$LOG_FILE"
}

log "=========================================="
log "Boatflix2 After Startup Script initiated"
log "=========================================="

# ============================================================================
# Step 1: Wait for Network Connectivity
# ============================================================================
log "Waiting for network connectivity..."

wait_count=0
while ! ping -c 1 -W 2 8.8.8.8 &> /dev/null; do
    wait_count=$((wait_count + NETWORK_CHECK_INTERVAL))
    if [ $wait_count -ge $MAX_NETWORK_WAIT ]; then
        log "WARNING: Network not available after ${MAX_NETWORK_WAIT}s, continuing anyway..."
        break
    fi
    log "Network not ready, waiting... (${wait_count}s/${MAX_NETWORK_WAIT}s)"
    sleep $NETWORK_CHECK_INTERVAL
done

if ping -c 1 -W 2 8.8.8.8 &> /dev/null; then
    log "Network connectivity confirmed"
else
    log "WARNING: Proceeding without confirmed network connectivity"
fi

# ============================================================================
# Step 2: Ensure External HDD is Mounted
# ============================================================================
log "Checking external HDD mount..."

if mountpoint -q "$MEDIA_MOUNT"; then
    log "External HDD is mounted at $MEDIA_MOUNT"
else
    log "External HDD not mounted, attempting to mount..."

    # Try to mount via fstab entry
    if mount "$MEDIA_MOUNT" 2>> "$LOG_FILE"; then
        log "Successfully mounted $MEDIA_MOUNT"
    else
        log "ERROR: Failed to mount $MEDIA_MOUNT"
        log "Attempting to reload systemd and retry..."

        systemctl daemon-reload
        sleep 2

        if mount "$MEDIA_MOUNT" 2>> "$LOG_FILE"; then
            log "Successfully mounted $MEDIA_MOUNT after systemd reload"
        else
            log "ERROR: Could not mount external HDD - services may fail"
        fi
    fi
fi

# Verify mount and check disk space
if mountpoint -q "$MEDIA_MOUNT"; then
    disk_info=$(df -h "$MEDIA_MOUNT" | tail -1)
    log "Disk info: $disk_info"
fi

# ============================================================================
# Step 3: Start Docker Services
# ============================================================================
log "Starting Docker services..."

# Ensure Docker daemon is running
if ! systemctl is-active --quiet docker; then
    log "Docker daemon not running, starting..."
    systemctl start docker
    sleep 5
fi

if systemctl is-active --quiet docker; then
    log "Docker daemon is running"

    # Change to boatflix directory
    if [ -d "$BOATFLIX_DIR" ]; then
        cd "$BOATFLIX_DIR"

        # Check if docker-compose.yml exists
        if [ -f "$DOCKER_COMPOSE_FILE" ]; then
            log "Starting docker compose services..."

            # Pull latest images (optional, comment out if not desired)
            # docker compose pull >> "$LOG_FILE" 2>&1

            # Start services
            if docker compose up -d >> "$LOG_FILE" 2>&1; then
                log "Docker services started successfully"

                # Log running containers
                sleep 5
                running=$(docker compose ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null)
                log "Running containers:"
                echo "$running" >> "$LOG_FILE"
            else
                log "ERROR: Failed to start docker compose services"
            fi
        else
            log "ERROR: docker-compose.yml not found at $DOCKER_COMPOSE_FILE"
        fi
    else
        log "ERROR: Boatflix directory not found at $BOATFLIX_DIR"
    fi
else
    log "ERROR: Docker daemon failed to start"
fi

# ============================================================================
# Step 4: Run rclone Sync (if configured)
# ============================================================================
log "Checking rclone configuration..."

# Source environment variables
if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi

if [ -f "$RCLONE_CONFIG" ] && [ -n "$RCLONE_REMOTE" ] && [ -n "$RCLONE_BUCKET" ]; then
    log "rclone is configured, checking for sync on startup..."

    # Check if sync on startup is enabled (optional configuration)
    SYNC_ON_STARTUP=${SYNC_ON_STARTUP:-false}

    if [ "$SYNC_ON_STARTUP" = "true" ]; then
        log "Running rclone sync from remote..."

        # Sync from remote to local (download new content)
        if rclone sync \
            --config "$RCLONE_CONFIG" \
            "${RCLONE_REMOTE}:${RCLONE_BUCKET}" \
            "$MEDIA_MOUNT" \
            --exclude "Downloads/**" \
            --log-file "$LOG_FILE" \
            --log-level INFO \
            --stats 1m \
            2>> "$LOG_FILE"; then
            log "rclone sync from remote completed successfully"
        else
            log "WARNING: rclone sync from remote completed with errors"
        fi
    else
        log "Sync on startup disabled (SYNC_ON_STARTUP=$SYNC_ON_STARTUP)"
    fi

    # Verify remote connection
    if rclone --config "$RCLONE_CONFIG" lsd "${RCLONE_REMOTE}:" &> /dev/null; then
        log "rclone remote connection verified"
    else
        log "WARNING: Could not verify rclone remote connection"
    fi
else
    log "rclone not fully configured, skipping sync"
    [ ! -f "$RCLONE_CONFIG" ] && log "  - rclone.conf not found"
    [ -z "$RCLONE_REMOTE" ] && log "  - RCLONE_REMOTE not set"
    [ -z "$RCLONE_BUCKET" ] && log "  - RCLONE_BUCKET not set"
fi

# ============================================================================
# Step 5: Log Startup Completion
# ============================================================================
uptime_info=$(uptime -p 2>/dev/null || uptime)
log "System uptime: $uptime_info"

# Get service status
if [ -d "$BOATFLIX_DIR" ] && [ -f "$DOCKER_COMPOSE_FILE" ]; then
    cd "$BOATFLIX_DIR"
    service_count=$(docker compose ps -q 2>/dev/null | wc -l)
    log "Docker services running: $service_count"
fi

log "=========================================="
log "Boatflix2 startup sequence completed"
log "=========================================="

exit 0
