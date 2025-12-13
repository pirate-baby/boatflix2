#!/bin/bash
# Boatflix2 Setup Script for Raspberry Pi 5
# Target: Raspberry Pi 5 running Raspberry Pi OS (64-bit)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BOATFLIX_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIA_MOUNT="/media/boatflix/Expansion/media"
WITTY_PI_DIR="/home/${USER}/wittypi"
LOG_FILE="/var/log/boatflix2-setup.log"

# Logging function
log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${message}" | sudo tee -a "$LOG_FILE" >/dev/null
    case $level in
        INFO)  echo -e "${GREEN}[INFO]${NC} ${message}" ;;
        WARN)  echo -e "${YELLOW}[WARN]${NC} ${message}" ;;
        ERROR) echo -e "${RED}[ERROR]${NC} ${message}" ;;
        *)     echo -e "${BLUE}[${level}]${NC} ${message}" ;;
    esac
}

# Check if running on Raspberry Pi
check_raspberry_pi() {
    if [[ ! -f /proc/device-tree/model ]]; then
        log WARN "Cannot detect Raspberry Pi model. Continuing anyway..."
        return
    fi
    local model=$(cat /proc/device-tree/model 2>/dev/null || echo "Unknown")
    log INFO "Detected: ${model}"
}

# Check if running as root
check_not_root() {
    if [[ $EUID -eq 0 ]]; then
        log ERROR "This script should NOT be run as root. Run as regular user with sudo privileges."
        exit 1
    fi
}

# ============================================================================
# Section 1: Prerequisites Installation
# ============================================================================
install_prerequisites() {
    log INFO "=== Section 1: Installing Prerequisites ==="

    # Update apt packages
    log INFO "Updating apt packages..."
    sudo apt update && sudo apt upgrade -y

    # Install essential packages
    log INFO "Installing essential packages..."
    sudo apt install -y \
        curl \
        wget \
        git \
        jq \
        unzip \
        htop \
        usbutils \
        udisks2

    # Install Docker via official script
    if command -v docker &> /dev/null; then
        log INFO "Docker is already installed: $(docker --version)"
    else
        log INFO "Installing Docker via official script..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        rm get-docker.sh
        log INFO "Docker installed successfully"
    fi

    # Add current user to docker group
    if groups "$USER" | grep -q docker; then
        log INFO "User $USER is already in docker group"
    else
        log INFO "Adding $USER to docker group..."
        sudo usermod -aG docker "$USER"
        log WARN "You may need to log out and back in for docker group changes to take effect"
    fi

    # Verify Docker Compose plugin
    if docker compose version &> /dev/null; then
        log INFO "Docker Compose plugin is available: $(docker compose version)"
    else
        log INFO "Installing Docker Compose plugin..."
        sudo apt install -y docker-compose-plugin
    fi

    # Install rclone
    if command -v rclone &> /dev/null; then
        log INFO "rclone is already installed: $(rclone version | head -n1)"
    else
        log INFO "Installing rclone..."
        curl https://rclone.org/install.sh | sudo bash
        log INFO "rclone installed successfully"
    fi

    log INFO "Prerequisites installation complete"
}

# ============================================================================
# Section 2: External HDD Setup
# ============================================================================
setup_external_hdd() {
    log INFO "=== Section 2: External HDD Setup ==="

    # Check if already mounted - if so, skip drive setup
    if mountpoint -q "$MEDIA_MOUNT" 2>/dev/null; then
        log INFO "External HDD already mounted at ${MEDIA_MOUNT}"
        log INFO "Skipping drive configuration"

        # Still create folder structure if needed
        log INFO "Ensuring Jellyfin folder structure exists..."
        mkdir -p "$MEDIA_MOUNT/Movies"
        mkdir -p "$MEDIA_MOUNT/Shows"
        mkdir -p "$MEDIA_MOUNT/Music"
        mkdir -p "$MEDIA_MOUNT/Commercials"
        mkdir -p "$MEDIA_MOUNT/Books"
        mkdir -p "$MEDIA_MOUNT/Downloads"
        mkdir -p "$MEDIA_MOUNT/Downloads/complete"
        mkdir -p "$MEDIA_MOUNT/Downloads/incomplete"
        return
    fi

    # Create mount point
    if [[ ! -d "$MEDIA_MOUNT" ]]; then
        log INFO "Creating mount point ${MEDIA_MOUNT}..."
        sudo mkdir -p "$MEDIA_MOUNT"
        sudo chown "$USER:$USER" "$MEDIA_MOUNT"
    else
        log INFO "Mount point ${MEDIA_MOUNT} already exists"
    fi

    # List available USB drives
    echo ""
    log INFO "Detecting USB drives..."
    echo ""

    # Find USB block devices (excluding boot device)
    local usb_drives=()
    while IFS= read -r line; do
        usb_drives+=("$line")
    done < <(lsblk -dpno NAME,SIZE,MODEL,TRAN 2>/dev/null | grep usb || true)

    if [[ ${#usb_drives[@]} -eq 0 ]]; then
        log WARN "No USB drives detected automatically."
        echo ""
        echo "Available block devices:"
        lsblk -dpo NAME,SIZE,MODEL,TRAN
        echo ""
        read -p "Enter device path (e.g., /dev/sda) or 'skip' to configure later: " DEVICE
        if [[ "$DEVICE" == "skip" ]]; then
            log WARN "Skipping external HDD setup. Configure manually later."
            return
        fi
    else
        echo "Detected USB drives:"
        echo ""
        local i=1
        for drive in "${usb_drives[@]}"; do
            echo "  $i) $drive"
            ((i++))
        done
        echo ""
        read -p "Select drive number (or enter device path, or 'skip'): " selection

        if [[ "$selection" == "skip" ]]; then
            log WARN "Skipping external HDD setup. Configure manually later."
            return
        elif [[ "$selection" =~ ^[0-9]+$ ]] && [[ $selection -ge 1 ]] && [[ $selection -le ${#usb_drives[@]} ]]; then
            DEVICE=$(echo "${usb_drives[$((selection-1))]}" | awk '{print $1}')
        else
            DEVICE="$selection"
        fi
    fi

    # Validate device exists
    if [[ ! -b "$DEVICE" ]]; then
        log ERROR "Device $DEVICE does not exist"
        return 1
    fi

    log INFO "Selected device: $DEVICE"

    # Check for partitions
    local partition=""
    if [[ -b "${DEVICE}1" ]]; then
        partition="${DEVICE}1"
    elif [[ -b "${DEVICE}p1" ]]; then
        partition="${DEVICE}p1"
    else
        partition="$DEVICE"
    fi

    log INFO "Using partition: $partition"

    # Get filesystem type
    local fstype=$(lsblk -no FSTYPE "$partition" 2>/dev/null | head -n1)
    if [[ -z "$fstype" ]]; then
        log WARN "No filesystem detected on $partition"
        read -p "Would you like to format as ext4? (y/N): " format_confirm
        if [[ "$format_confirm" =~ ^[Yy]$ ]]; then
            log INFO "Formatting $partition as ext4..."
            sudo mkfs.ext4 -L "boatflix-media" "$partition"
            fstype="ext4"
        else
            log ERROR "Cannot proceed without filesystem"
            return 1
        fi
    fi
    log INFO "Filesystem type: $fstype"

    # Get UUID
    local uuid=$(sudo blkid -s UUID -o value "$partition")
    if [[ -z "$uuid" ]]; then
        log ERROR "Could not get UUID for $partition"
        return 1
    fi
    log INFO "Drive UUID: $uuid"

    # Determine mount options based on filesystem type
    local mount_opts="defaults,nofail,x-systemd.device-timeout=30"
    local uid=$(id -u)
    local gid=$(id -g)

    # FAT/exFAT filesystems don't support Unix permissions, so set ownership at mount time
    if [[ "$fstype" == "vfat" || "$fstype" == "exfat" ]]; then
        mount_opts="$mount_opts,uid=$uid,gid=$gid,umask=0022"
        log INFO "Using mount options for $fstype filesystem (uid=$uid, gid=$gid)"
    fi

    # Check if already in fstab
    local fstab_updated=false
    if grep -q "$uuid" /etc/fstab; then
        # Check if fstab entry needs updating for vfat/exfat (missing uid/gid options)
        if [[ "$fstype" == "vfat" || "$fstype" == "exfat" ]]; then
            if ! grep "$uuid" /etc/fstab | grep -q "uid="; then
                log INFO "Updating fstab entry with uid/gid options for $fstype..."
                sudo cp /etc/fstab /etc/fstab.backup.$(date +%Y%m%d%H%M%S)
                sudo sed -i "\|$uuid|d" /etc/fstab
                echo "UUID=$uuid  $MEDIA_MOUNT  $fstype  $mount_opts  0  2" | sudo tee -a /etc/fstab
                fstab_updated=true
            else
                log INFO "Drive already configured in /etc/fstab with correct options"
            fi
        else
            log INFO "Drive already configured in /etc/fstab"
        fi
    else
        log INFO "Adding fstab entry..."
        # Backup fstab
        sudo cp /etc/fstab /etc/fstab.backup.$(date +%Y%m%d%H%M%S)

        # Add fstab entry
        echo "UUID=$uuid  $MEDIA_MOUNT  $fstype  $mount_opts  0  2" | sudo tee -a /etc/fstab
        log INFO "Added fstab entry for auto-mount"
        fstab_updated=true
    fi

    # Reload systemd if fstab was updated
    if [[ "$fstab_updated" == true ]]; then
        sudo systemctl daemon-reload
    fi

    # Mount the drive (remount if already mounted and fstab was updated)
    if mountpoint -q "$MEDIA_MOUNT"; then
        if [[ "$fstab_updated" == true ]]; then
            log INFO "Remounting drive with updated options..."
            sudo umount "$MEDIA_MOUNT"
            sudo mount "$MEDIA_MOUNT"
        else
            log INFO "$MEDIA_MOUNT is already mounted"
        fi
    else
        log INFO "Mounting drive..."
        sudo mount "$MEDIA_MOUNT"
    fi

    # Set ownership (only works on filesystems that support Unix permissions)
    if [[ "$fstype" != "vfat" && "$fstype" != "exfat" ]]; then
        sudo chown -R "$USER:$USER" "$MEDIA_MOUNT"
    fi

    # Create Jellyfin folder structure
    log INFO "Creating Jellyfin folder structure..."
    mkdir -p "$MEDIA_MOUNT/Movies"
    mkdir -p "$MEDIA_MOUNT/Shows"
    mkdir -p "$MEDIA_MOUNT/Music"
    mkdir -p "$MEDIA_MOUNT/Commercials"
    mkdir -p "$MEDIA_MOUNT/Books"
    mkdir -p "$MEDIA_MOUNT/Downloads"
    mkdir -p "$MEDIA_MOUNT/Downloads/complete"
    mkdir -p "$MEDIA_MOUNT/Downloads/incomplete"

    log INFO "Folder structure created:"
    ls -la "$MEDIA_MOUNT"

    log INFO "External HDD setup complete"
}

# ============================================================================
# Section 3: rclone Configuration
# ============================================================================
configure_rclone() {
    log INFO "=== Section 3: rclone Configuration ==="

    local rclone_config="$BOATFLIX_DIR/rclone.conf"

    echo ""
    read -p "Would you like to configure rclone for S3 backup now? (y/N): " configure_rclone

    if [[ ! "$configure_rclone" =~ ^[Yy]$ ]]; then
        log INFO "Skipping rclone configuration. You can configure it later by editing rclone.conf"

        # Create empty rclone.conf if it doesn't exist
        if [[ ! -f "$rclone_config" ]]; then
            cat > "$rclone_config" << 'EOF'
# rclone configuration for Boatflix2
# Configure your S3-compatible storage here
# See: https://rclone.org/s3/

# Example S3 configuration:
# [s3]
# type = s3
# provider = Other
# access_key_id = YOUR_ACCESS_KEY
# secret_access_key = YOUR_SECRET_KEY
# endpoint = YOUR_S3_ENDPOINT
# acl = private
EOF
            log INFO "Created template rclone.conf"
        fi
        return
    fi

    echo ""
    log INFO "S3-Compatible Storage Configuration"
    echo ""

    read -p "S3 Endpoint URL (e.g., s3.amazonaws.com or nyc3.digitaloceanspaces.com): " s3_endpoint
    read -p "Access Key ID: " s3_access_key
    read -sp "Secret Access Key: " s3_secret_key
    echo ""
    read -p "Bucket name: " s3_bucket
    read -p "Remote name [s3]: " remote_name
    remote_name=${remote_name:-s3}

    # Create rclone.conf
    cat > "$rclone_config" << EOF
# rclone configuration for Boatflix2
# Generated by setup.sh on $(date)

[$remote_name]
type = s3
provider = Other
access_key_id = $s3_access_key
secret_access_key = $s3_secret_key
endpoint = $s3_endpoint
acl = private
EOF

    chmod 600 "$rclone_config"
    log INFO "Created rclone.conf"

    # Test connection
    log INFO "Testing rclone connection..."
    if RCLONE_CONFIG="$rclone_config" rclone lsd "${remote_name}:" 2>/dev/null; then
        log INFO "Successfully connected to S3 storage"

        # Check if bucket exists
        if RCLONE_CONFIG="$rclone_config" rclone lsd "${remote_name}:${s3_bucket}" 2>/dev/null; then
            log INFO "Bucket '$s3_bucket' is accessible"
        else
            log WARN "Bucket '$s3_bucket' may not exist or is not accessible"
        fi

        # Update .env with rclone settings
        if [[ -f "$BOATFLIX_DIR/.env" ]]; then
            sed -i "s|^RCLONE_REMOTE=.*|RCLONE_REMOTE=${remote_name}|" "$BOATFLIX_DIR/.env"
            sed -i "s|^RCLONE_BUCKET=.*|RCLONE_BUCKET=${s3_bucket}|" "$BOATFLIX_DIR/.env"
            log INFO "Updated .env with rclone settings"
        fi
    else
        log WARN "Could not connect to S3 storage. Please verify credentials."
        log WARN "You can test manually with: rclone --config=$rclone_config lsd ${remote_name}:"
    fi

    log INFO "rclone configuration complete"
}

# ============================================================================
# Section 4: Witty Pi 4 Integration
# ============================================================================
setup_witty_pi() {
    log INFO "=== Section 4: Witty Pi 4 Integration ==="

    if [[ ! -d "$WITTY_PI_DIR" ]]; then
        log WARN "Witty Pi directory not found at $WITTY_PI_DIR"
        log INFO "If Witty Pi 4 is installed, please ensure it's at the correct location"
        log INFO "You can install Witty Pi 4 from: https://github.com/uugear/Witty-Pi-4"

        read -p "Would you like to create Witty Pi script templates anyway? (y/N): " create_templates
        if [[ ! "$create_templates" =~ ^[Yy]$ ]]; then
            log INFO "Skipping Witty Pi setup"
            return
        fi

        # Create wittypi directory for templates
        mkdir -p "$WITTY_PI_DIR"
    fi

    # Backup existing scripts
    for script in afterStartup.sh beforeShutdown.sh; do
        if [[ -f "$WITTY_PI_DIR/$script" ]]; then
            cp "$WITTY_PI_DIR/$script" "$WITTY_PI_DIR/${script}.backup.$(date +%Y%m%d%H%M%S)"
            log INFO "Backed up existing $script"
        fi
    done

    # Copy Witty Pi scripts from templates
    if [[ -f "$BOATFLIX_DIR/wittypi/afterStartup.sh" ]]; then
        cp "$BOATFLIX_DIR/wittypi/afterStartup.sh" "$WITTY_PI_DIR/afterStartup.sh"
        chmod +x "$WITTY_PI_DIR/afterStartup.sh"
        log INFO "Installed afterStartup.sh"
    fi

    if [[ -f "$BOATFLIX_DIR/wittypi/beforeShutdown.sh" ]]; then
        cp "$BOATFLIX_DIR/wittypi/beforeShutdown.sh" "$WITTY_PI_DIR/beforeShutdown.sh"
        chmod +x "$WITTY_PI_DIR/beforeShutdown.sh"
        log INFO "Installed beforeShutdown.sh"
    fi

    log INFO "Witty Pi integration complete"
}

# ============================================================================
# Section 5: Systemd Service
# ============================================================================
setup_systemd_service() {
    log INFO "=== Section 5: Systemd Service Setup ==="

    local service_file="/etc/systemd/system/boatflix2.service"

    # Create systemd service
    log INFO "Creating systemd service..."

    sudo tee "$service_file" > /dev/null << EOF
[Unit]
Description=Boatflix2 Media Server Stack
Documentation=https://github.com/your-repo/boatflix2
After=docker.service media-boatflix-Expansion-media.mount network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=$USER
Group=docker
WorkingDirectory=$BOATFLIX_DIR

# Start containers
ExecStart=/usr/bin/docker compose -f $BOATFLIX_DIR/docker-compose.yml up -d

# Stop containers gracefully
ExecStop=/usr/bin/docker compose -f $BOATFLIX_DIR/docker-compose.yml down

# Restart policy handled by Docker's restart: unless-stopped
Restart=on-failure
RestartSec=30

# Environment
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

[Install]
WantedBy=multi-user.target
EOF

    log INFO "Created $service_file"

    # Reload systemd
    sudo systemctl daemon-reload

    # Enable service
    sudo systemctl enable boatflix2.service
    log INFO "Enabled boatflix2.service"

    log INFO "Systemd service setup complete"
    log INFO "Note: Service will start on next boot, or run: sudo systemctl start boatflix2"
}

# ============================================================================
# Section 6: Environment Setup
# ============================================================================
setup_environment() {
    log INFO "=== Section 6: Environment Setup ==="

    local env_file="$BOATFLIX_DIR/.env"
    local env_example="$BOATFLIX_DIR/.env.example"

    # Create .env if it doesn't exist
    if [[ ! -f "$env_file" ]]; then
        if [[ -f "$env_example" ]]; then
            cp "$env_example" "$env_file"
            log INFO "Created .env from .env.example"
        else
            # Create .env from scratch
            cat > "$env_file" << 'EOF'
# User/Group IDs for file permissions
PUID=1000
PGID=1000

# Timezone
TZ=America/New_York

# Media storage path on host
MEDIA_PATH=/media/boatflix/Expansion/media

# Downloads path (where torrents are downloaded)
DOWNLOADS_PATH=/media/boatflix/Expansion/media/Downloads

# TMDB API Key for metadata enrichment (optional, free tier available at themoviedb.org)
TMDB_API_KEY=

# rclone sync configuration
RCLONE_REMOTE=
RCLONE_BUCKET=
RCLONE_CONFIG=./rclone.conf
SYNC_CRON=0 2 * * *
SYNC_ENABLED=true

# VPN Configuration (for qBittorrent)
VPN_USER=
VPN_PASSWORD=
LAN_NETWORK=192.168.1.0/24
EOF
            log INFO "Created new .env file"
        fi
    else
        log INFO ".env file already exists, will preserve existing values"
        # Ensure VPN fields exist (add them if missing)
        if ! grep -q "^VPN_USER=" "$env_file"; then
            echo "" >> "$env_file"
            echo "# VPN Configuration (for qBittorrent)" >> "$env_file"
            echo "VPN_USER=" >> "$env_file"
            log INFO "Added VPN_USER field to .env"
        fi
        if ! grep -q "^VPN_PASSWORD=" "$env_file"; then
            echo "VPN_PASSWORD=" >> "$env_file"
            log INFO "Added VPN_PASSWORD field to .env"
        fi
        if ! grep -q "^LAN_NETWORK=" "$env_file"; then
            echo "LAN_NETWORK=192.168.1.0/24" >> "$env_file"
            log INFO "Added LAN_NETWORK field to .env"
        fi
    fi

    # Helper function to get current value from .env
    get_env_value() {
        grep "^$1=" "$env_file" 2>/dev/null | cut -d'=' -f2-
    }

    echo ""
    log INFO "Configuring environment variables (press Enter to keep existing values)..."
    echo ""

    # Get PUID (prefer existing, fallback to current user's ID)
    local existing_puid=$(get_env_value "PUID")
    local default_puid=${existing_puid:-$(id -u)}
    read -p "PUID (user ID) [$default_puid]: " puid
    puid=${puid:-$default_puid}

    # Get PGID (prefer existing, fallback to current user's group ID)
    local existing_pgid=$(get_env_value "PGID")
    local default_pgid=${existing_pgid:-$(id -g)}
    read -p "PGID (group ID) [$default_pgid]: " pgid
    pgid=${pgid:-$default_pgid}

    # Get timezone (prefer existing, fallback to system timezone)
    local existing_tz=$(get_env_value "TZ")
    local default_tz=${existing_tz:-$(cat /etc/timezone 2>/dev/null || echo "UTC")}
    read -p "Timezone [$default_tz]: " tz
    tz=${tz:-$default_tz}

    # Update .env file
    sed -i "s|^PUID=.*|PUID=$puid|" "$env_file"
    sed -i "s|^PGID=.*|PGID=$pgid|" "$env_file"
    sed -i "s|^TZ=.*|TZ=$tz|" "$env_file"
    sed -i "s|^MEDIA_PATH=.*|MEDIA_PATH=$MEDIA_MOUNT|" "$env_file"
    sed -i "s|^DOWNLOADS_PATH=.*|DOWNLOADS_PATH=$MEDIA_MOUNT/Downloads|" "$env_file"

    # TMDB API Key (optional)
    echo ""
    local existing_tmdb=$(get_env_value "TMDB_API_KEY")
    if [[ -n "$existing_tmdb" ]]; then
        read -p "TMDB API Key [keep existing]: " tmdb_key
    else
        read -p "TMDB API Key (optional, press Enter to skip): " tmdb_key
    fi
    if [[ -n "$tmdb_key" ]]; then
        sed -i "s|^TMDB_API_KEY=.*|TMDB_API_KEY=$tmdb_key|" "$env_file"
    fi

    # VPN Configuration
    echo ""
    log INFO "VPN Configuration (for qBittorrent with PIA)"
    echo ""
    local existing_vpn_user=$(get_env_value "VPN_USER")
    local existing_vpn_pass=$(get_env_value "VPN_PASSWORD")

    if [[ -n "$existing_vpn_user" ]]; then
        read -p "PIA VPN Username [$existing_vpn_user]: " vpn_user
        vpn_user=${vpn_user:-$existing_vpn_user}
    else
        read -p "PIA VPN Username: " vpn_user
    fi

    if [[ -n "$existing_vpn_pass" ]]; then
        read -sp "PIA VPN Password [keep existing, or enter new]: " vpn_pass
        echo ""
        vpn_pass=${vpn_pass:-$existing_vpn_pass}
    else
        read -sp "PIA VPN Password: " vpn_pass
        echo ""
    fi

    if [[ -n "$vpn_user" ]]; then
        sed -i "s|^VPN_USER=.*|VPN_USER=$vpn_user|" "$env_file"
    fi
    if [[ -n "$vpn_pass" ]]; then
        sed -i "s|^VPN_PASSWORD=.*|VPN_PASSWORD=$vpn_pass|" "$env_file"
    fi

    # Auto-detect LAN network
    local lan_network=""
    local existing_lan=$(get_env_value "LAN_NETWORK")

    # Try to detect the primary network interface's subnet
    local detected_lan=$(ip -o -f inet addr show 2>/dev/null | grep -v '127.0.0.1' | head -n1 | awk '{print $4}' | sed 's/\.[0-9]*\//.0\//')

    if [[ -z "$detected_lan" ]]; then
        # Fallback: try hostname -I approach
        local ip_addr=$(hostname -I 2>/dev/null | awk '{print $1}')
        if [[ -n "$ip_addr" ]]; then
            # Convert IP to /24 subnet (e.g., 192.168.1.50 -> 192.168.1.0/24)
            detected_lan=$(echo "$ip_addr" | sed 's/\.[0-9]*$/.0\/24/')
        fi
    fi

    # Prefer existing value, fallback to detected, then default
    lan_network=${existing_lan:-${detected_lan:-"192.168.1.0/24"}}

    if [[ -n "$detected_lan" && "$detected_lan" != "$lan_network" ]]; then
        log INFO "Detected LAN: $detected_lan (current: $lan_network)"
    fi
    read -p "LAN Network (for VPN split tunnel) [$lan_network]: " user_lan
    lan_network=${user_lan:-$lan_network}

    sed -i "s|^LAN_NETWORK=.*|LAN_NETWORK=$lan_network|" "$env_file"

    chmod 600 "$env_file"

    log INFO "Environment configuration:"
    echo "  PUID=$puid"
    echo "  PGID=$pgid"
    echo "  TZ=$tz"
    echo "  MEDIA_PATH=$MEDIA_MOUNT"
    echo "  LAN_NETWORK=$lan_network"

    log INFO "Environment setup complete"
}

# ============================================================================
# Main Installation Flow
# ============================================================================
print_banner() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                                                               ║${NC}"
    echo -e "${BLUE}║${NC}     ${GREEN}Boatflix2 Setup Script for Raspberry Pi 5${NC}               ${BLUE}║${NC}"
    echo -e "${BLUE}║${NC}     Media Server Stack: Jellyfin + ErsatzTV + qBittorrent   ${BLUE}║${NC}"
    echo -e "${BLUE}║                                                               ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_summary() {
    echo ""
    log INFO "=== Setup Complete ==="
    echo ""
    echo "Installation Summary:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  Boatflix Directory: $BOATFLIX_DIR"
    echo "  Media Mount Point:  $MEDIA_MOUNT"
    echo "  Witty Pi Scripts:   $WITTY_PI_DIR"
    echo ""
    echo "  Services configured:"
    echo "    - Jellyfin     (http://localhost:8096)"
    echo "    - ErsatzTV     (http://localhost:8409)"
    echo "    - qBittorrent  (http://localhost:8080)"
    echo "    - Manager API  (http://localhost:8000)"
    echo ""
    echo "  Next Steps:"
    echo "    1. Log out and back in (for docker group changes)"
    echo "    2. Start services: sudo systemctl start boatflix2"
    echo "    3. Or manually: docker compose up -d"
    echo ""
    echo "  Useful Commands:"
    echo "    - Check status:  sudo systemctl status boatflix2"
    echo "    - View logs:     docker compose logs -f"
    echo "    - Stop services: sudo systemctl stop boatflix2"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

main() {
    print_banner

    check_not_root
    check_raspberry_pi

    # Create log file
    sudo touch "$LOG_FILE"
    sudo chown "$USER:$USER" "$LOG_FILE"

    log INFO "Starting Boatflix2 setup..."
    log INFO "Boatflix directory: $BOATFLIX_DIR"
    log INFO "Log file: $LOG_FILE"
    echo ""

    # Run setup sections
    install_prerequisites
    echo ""

    setup_external_hdd
    echo ""

    configure_rclone
    echo ""

    setup_witty_pi
    echo ""

    setup_systemd_service
    echo ""

    setup_environment
    echo ""

    print_summary
}

# Run main function
main "$@"
