#!/bin/bash

# Auto Push Monitor
# Monitors git repositories and automatically pushes changes to main branch

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to log with timestamp
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

# Function to check if directory is a git repository
is_git_repo() {
    local dir="$1"
    [ -d "$dir/.git" ]
}

# Function to check and push a single repository
check_and_push_repo() {
    local repo_path="$1"

    log "Checking repository: $repo_path"

    cd "$repo_path" || return 1

    # Check if main branch exists
    if ! git show-ref --verify --quiet refs/heads/main; then
        log_warning "  No 'main' branch found, skipping"
        return 0
    fi

    # Get current branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)

    # Check if we're on main branch
    if [ "$current_branch" != "main" ]; then
        log_warning "  Not on main branch (currently on $current_branch), skipping"
        return 0
    fi

    # Fetch to update remote tracking
    log "  Fetching from origin..."
    git fetch origin main

    # Check if local main is ahead of origin/main
    local_commit=$(git rev-parse main)
    remote_commit=$(git rev-parse origin/main 2>/dev/null || echo "")

    if [ -z "$remote_commit" ]; then
        log_warning "  No remote tracking branch found for main"
        return 0
    fi

    if [ "$local_commit" = "$remote_commit" ]; then
        log "  No changes to push"
        return 0
    fi

    # Check if local is ahead
    ahead=$(git rev-list --count origin/main..main)
    behind=$(git rev-list --count main..origin/main)

    if [ "$behind" -gt 0 ]; then
        log_error "  Local is behind remote by $behind commits"
        return 1
    fi

    if [ "$ahead" -gt 0 ]; then
        log_success "  Local is ahead by $ahead commits, pushing..."
        git push origin main
        log_success "  ✓ Pushed successfully"
    fi
}

# Function to process all subdirectories in a root path
process_root_directory() {
    local root_path="$1"

    if [ ! -d "$root_path" ]; then
        log_error "Directory does not exist: $root_path"
        return 1
    fi

    log "Processing root directory: $root_path"

    # Find all git repositories in subdirectories
    for subdir in "$root_path"/*; do
        if [ -d "$subdir" ]; then
            if is_git_repo "$subdir"; then
                check_and_push_repo "$subdir"
            fi
        fi
    done
}

# Main monitoring loop
main() {
    if [ $# -eq 0 ]; then
        echo "Usage: $0 <root_directory_1> [root_directory_2] ..."
        echo ""
        echo "Example: $0 /path/to/repos /another/path/to/repos"
        echo ""
        echo "This script will monitor all git repositories in the subdirectories"
        echo "of the provided root paths and automatically push changes to the main branch."
        exit 1
    fi

    local root_directories=("$@")

    log_success "Starting Auto Push Monitor"
    log "Monitoring ${#root_directories[@]} root director(y/ies)"
    for dir in "${root_directories[@]}"; do
        log "  - $dir"
    done
    log "Press Ctrl+C to stop"
    echo ""

    while true; do
        for root_dir in "${root_directories[@]}"; do
            process_root_directory "$root_dir"
        done

        log "Sleeping for 10 seconds..."
        echo ""
        sleep 10
    done
}

# Run main function with all arguments
main "$@"
