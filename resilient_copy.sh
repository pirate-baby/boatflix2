#!/bin/bash

# Resilient Copy Script
# Copies files one-by-one from source to destination, deleting source after successful copy
# Designed to handle drives that may disconnect unexpectedly

set -euo pipefail

# Configuration
SOURCE_DIR="${1:-}"
DEST_DIR="${2:-}"
LOG_FILE="${3:-./resilient_copy.log}"
PROGRESS_FILE="${4:-./resilient_copy_progress.txt}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 <source_directory> <destination_directory> [log_file] [progress_file]"
    echo ""
    echo "Arguments:"
    echo "  source_directory      Path to the legacy drive (e.g., /mnt/legacy)"
    echo "  destination_directory Path to the new drive (e.g., /mnt/new)"
    echo "  log_file              Optional: Path to log file (default: ./resilient_copy.log)"
    echo "  progress_file         Optional: Path to progress file (default: ./resilient_copy_progress.txt)"
    echo ""
    echo "The script will:"
    echo "  1. Find all files in source_directory"
    echo "  2. Copy each file to destination_directory (preserving structure)"
    echo "  3. Verify the copy with checksum"
    echo "  4. Delete the source file only after successful verification"
    echo "  5. Track progress so you can resume after a drive failure"
    exit 1
}

log() {
    local message="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo -e "$message" | tee -a "$LOG_FILE"
}

check_mount() {
    local dir="$1"
    if ! mountpoint -q "$dir" 2>/dev/null; then
        # Not a mountpoint, check if directory is accessible
        if [[ ! -d "$dir" ]] || ! ls "$dir" &>/dev/null; then
            return 1
        fi
    fi
    return 0
}

# Validate arguments
if [[ -z "$SOURCE_DIR" ]] || [[ -z "$DEST_DIR" ]]; then
    usage
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo -e "${RED}Error: Source directory does not exist: $SOURCE_DIR${NC}"
    exit 1
fi

if [[ ! -d "$DEST_DIR" ]]; then
    echo -e "${YELLOW}Creating destination directory: $DEST_DIR${NC}"
    mkdir -p "$DEST_DIR"
fi

# Initialize log
log "=========================================="
log "Starting resilient copy"
log "Source: $SOURCE_DIR"
log "Destination: $DEST_DIR"
log "Progress file: $PROGRESS_FILE"
log "=========================================="

# Load already-copied files from progress file
declare -A COPIED_FILES
if [[ -f "$PROGRESS_FILE" ]]; then
    while IFS= read -r line; do
        COPIED_FILES["$line"]=1
    done < "$PROGRESS_FILE"
    log "Loaded ${#COPIED_FILES[@]} already-copied files from progress file"
fi

# Counters
total_files=0
copied_files=0
skipped_files=0
failed_files=0

# Find all files and process them one by one
log "Scanning source directory for files..."

while IFS= read -r -d '' source_file; do
    ((total_files++))

    # Get relative path
    relative_path="${source_file#$SOURCE_DIR/}"
    dest_file="$DEST_DIR/$relative_path"

    # Skip if already copied
    if [[ -v "COPIED_FILES[$relative_path]" ]]; then
        echo -e "${YELLOW}[SKIP]${NC} Already copied: $relative_path"
        ((skipped_files++))
        continue
    fi

    # Check if source is still accessible
    if ! check_mount "$SOURCE_DIR"; then
        log "${RED}ERROR: Source drive appears to be unmounted!${NC}"
        log "Processed $copied_files files before failure"
        log "Run the script again after remounting the drive"
        exit 2
    fi

    echo -e "${YELLOW}[COPY]${NC} $relative_path"

    # Create destination directory structure
    dest_dir=$(dirname "$dest_file")
    if [[ ! -d "$dest_dir" ]]; then
        if ! mkdir -p "$dest_dir" 2>/dev/null; then
            log "ERROR: Failed to create directory: $dest_dir"
            ((failed_files++))
            continue
        fi
    fi

    # Get source file size for progress
    source_size=$(stat -c%s "$source_file" 2>/dev/null || stat -f%z "$source_file" 2>/dev/null || echo "unknown")

    # Copy the file with rsync for better handling
    if rsync -a --progress --inplace "$source_file" "$dest_file" 2>&1; then
        # Verify with checksum
        echo -n "  Verifying checksum... "

        source_md5=$(md5sum "$source_file" 2>/dev/null | cut -d' ' -f1 || md5 -q "$source_file" 2>/dev/null)
        dest_md5=$(md5sum "$dest_file" 2>/dev/null | cut -d' ' -f1 || md5 -q "$dest_file" 2>/dev/null)

        if [[ "$source_md5" == "$dest_md5" ]] && [[ -n "$source_md5" ]]; then
            echo -e "${GREEN}OK${NC}"

            # Delete source file
            echo -n "  Deleting source... "
            if rm "$source_file" 2>/dev/null; then
                echo -e "${GREEN}OK${NC}"

                # Record success
                echo "$relative_path" >> "$PROGRESS_FILE"
                ((copied_files++))
                log "SUCCESS: $relative_path (${source_size} bytes)"
            else
                echo -e "${RED}FAILED${NC}"
                log "WARNING: Copy succeeded but could not delete source: $relative_path"
                # Still record as copied since the file is safely on destination
                echo "$relative_path" >> "$PROGRESS_FILE"
                ((copied_files++))
            fi
        else
            echo -e "${RED}MISMATCH${NC}"
            log "ERROR: Checksum mismatch for $relative_path"
            log "  Source MD5: $source_md5"
            log "  Dest MD5:   $dest_md5"
            # Remove failed copy
            rm -f "$dest_file" 2>/dev/null
            ((failed_files++))
        fi
    else
        echo -e "${RED}[FAILED]${NC} Copy failed for: $relative_path"
        log "ERROR: Copy failed for $relative_path"

        # Check if this was an I/O error (drive disconnected)
        if ! check_mount "$SOURCE_DIR"; then
            log "Source drive disconnected during copy!"
            log "Processed $copied_files files before failure"
            log "Run the script again after remounting the drive"
            exit 2
        fi

        ((failed_files++))
    fi

done < <(find "$SOURCE_DIR" -type f -print0 2>/dev/null)

# Summary
log "=========================================="
log "Copy complete!"
log "Total files found: $total_files"
log "Successfully copied: $copied_files"
log "Previously copied (skipped): $skipped_files"
log "Failed: $failed_files"
log "=========================================="

echo ""
echo -e "${GREEN}=========================================="
echo "Copy complete!"
echo "Total files found: $total_files"
echo "Successfully copied: $copied_files"
echo "Previously copied (skipped): $skipped_files"
echo "Failed: $failed_files"
echo -e "==========================================${NC}"

if [[ $failed_files -gt 0 ]]; then
    echo -e "${YELLOW}Some files failed to copy. Check the log for details: $LOG_FILE${NC}"
    exit 1
fi

exit 0
