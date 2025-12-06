#!/bin/bash
# Boatflix2 Witty Pi 4 - Before Shutdown Script
# This script runs before the Raspberry Pi shuts down via Witty Pi 4
#
# Location: /home/boatflix/wittypi/beforeShutdown.sh
# Reference: https://github.com/uugear/Witty-Pi-4/tree/main/Software/wittypi

# Configuration
BOATFLIX_DIR="/home/boatflix/boatflix2"
MEDIA_MOUNT="/mnt/media"
LOG_FILE="/var/log/boatflix2-wittypi.log"
DOCKER_COMPOSE_FILE="$BOATFLIX_DIR/docker-compose.yml"
RCLONE_CONFIG="$BOATFLIX_DIR/rclone.conf"
ENV_FILE="$BOATFLIX_DIR/.env"

# Shutdown timeout configuration
DOCKER_STOP_TIMEOUT=60  # seconds
RCLONE_SYNC_TIMEOUT=300 # seconds (5 minutes)

# Logging function
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$timestamp [SHUTDOWN] $*" >> "$LOG_FILE"
}

log "=========================================="
log "Boatflix2 Before Shutdown Script initiated"
log "=========================================="

# ============================================================================
# Step 1: Gracefully Stop Docker Containers
# ============================================================================
log "Stopping Docker containers gracefully..."

if [ -d "$BOATFLIX_DIR" ] && [ -f "$DOCKER_COMPOSE_FILE" ]; then
    cd "$BOATFLIX_DIR"

    # Check if any containers are running
    running_containers=$(docker compose ps -q 2>/dev/null | wc -l)

    if [ "$running_containers" -gt 0 ]; then
        log "Found $running_containers running containers"

        # Stop containers with timeout
        log "Executing docker compose down (timeout: ${DOCKER_STOP_TIMEOUT}s)..."

        if timeout $DOCKER_STOP_TIMEOUT docker compose down >> "$LOG_FILE" 2>&1; then
            log "Docker containers stopped successfully"
        else
            log "WARNING: docker compose down timed out or failed"
            log "Attempting to force stop remaining containers..."

            # Force stop any remaining containers
            docker compose kill >> "$LOG_FILE" 2>&1
            docker compose rm -f >> "$LOG_FILE" 2>&1
        fi

        # Verify containers are stopped
        remaining=$(docker compose ps -q 2>/dev/null | wc -l)
        if [ "$remaining" -gt 0 ]; then
            log "WARNING: $remaining containers still running after shutdown"
        else
            log "All containers stopped"
        fi
    else
        log "No running containers found"
    fi
else
    log "WARNING: Boatflix directory or docker-compose.yml not found"
fi

# ============================================================================
# Step 2: Sync Any Pending rclone Changes
# ============================================================================
log "Checking for pending rclone sync..."

# Source environment variables
if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi

if [ -f "$RCLONE_CONFIG" ] && [ -n "$RCLONE_REMOTE" ] && [ -n "$RCLONE_BUCKET" ]; then
    log "rclone configured, syncing local changes to remote..."

    # Check if media mount is accessible
    if mountpoint -q "$MEDIA_MOUNT"; then
        log "Syncing to ${RCLONE_REMOTE}:${RCLONE_BUCKET}..."

        # Sync local to remote (upload changes) with timeout
        if timeout $RCLONE_SYNC_TIMEOUT rclone sync \
            --config "$RCLONE_CONFIG" \
            "$MEDIA_MOUNT" \
            "${RCLONE_REMOTE}:${RCLONE_BUCKET}" \
            --exclude "Downloads/**" \
            --exclude ".Trash-*/**" \
            --exclude "*.tmp" \
            --exclude "*.partial" \
            --log-file "$LOG_FILE" \
            --log-level INFO \
            --stats 30s \
            2>> "$LOG_FILE"; then
            log "rclone sync to remote completed successfully"
        else
            exit_code=$?
            if [ $exit_code -eq 124 ]; then
                log "WARNING: rclone sync timed out after ${RCLONE_SYNC_TIMEOUT}s"
            else
                log "WARNING: rclone sync completed with errors (exit code: $exit_code)"
            fi
        fi
    else
        log "WARNING: Media mount not available, skipping rclone sync"
    fi
else
    log "rclone not configured, skipping sync"
fi

# ============================================================================
# Step 3: Sync Filesystem Buffers
# ============================================================================
log "Syncing filesystem buffers..."
sync
log "Filesystem sync complete"

# ============================================================================
# Step 4: Unmount External Drives Safely
# ============================================================================
log "Preparing to unmount external drives..."

if mountpoint -q "$MEDIA_MOUNT"; then
    # Check for any processes using the mount
    if fuser -m "$MEDIA_MOUNT" > /dev/null 2>&1; then
        log "WARNING: Processes still using $MEDIA_MOUNT"
        log "Active processes:"
        fuser -vm "$MEDIA_MOUNT" >> "$LOG_FILE" 2>&1

        # Try to terminate processes gracefully
        log "Attempting to terminate processes..."
        fuser -km "$MEDIA_MOUNT" >> "$LOG_FILE" 2>&1
        sleep 2
    fi

    # Sync again before unmount
    sync

    # Attempt to unmount
    log "Unmounting $MEDIA_MOUNT..."

    if umount "$MEDIA_MOUNT" 2>> "$LOG_FILE"; then
        log "Successfully unmounted $MEDIA_MOUNT"
    else
        log "WARNING: Normal unmount failed, trying lazy unmount..."

        if umount -l "$MEDIA_MOUNT" 2>> "$LOG_FILE"; then
            log "Lazy unmount successful for $MEDIA_MOUNT"
        else
            log "ERROR: Could not unmount $MEDIA_MOUNT"
            log "Drive may be unmounted forcefully during shutdown"
        fi
    fi
else
    log "Media mount $MEDIA_MOUNT is not mounted"
fi

# ============================================================================
# Step 5: Log Shutdown Completion
# ============================================================================
uptime_info=$(uptime -p 2>/dev/null || uptime)
log "System uptime at shutdown: $uptime_info"

log "=========================================="
log "Boatflix2 shutdown preparation completed"
log "System will now shut down via Witty Pi"
log "=========================================="

# Final sync of log file
sync

exit 0
