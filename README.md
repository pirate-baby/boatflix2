# Boatflix2

A complete self-hosted media server stack for Raspberry Pi 5, combining media streaming, TV channel creation, torrent downloading, and cloud sync in one easy-to-deploy solution.

## Overview

Boatflix2 transforms your Raspberry Pi 5 into a powerful media server with automatic downloading, organization, and optional cloud backup. Perfect for boats, RVs, off-grid setups, or anywhere you want a portable, self-contained media library.

### Architecture

```
                                    ┌─────────────────────────────────────────────────────────┐
                                    │                    Raspberry Pi 5                        │
                                    │                                                          │
   ┌──────────┐                     │   ┌─────────────────────────────────────────────────┐   │
   │  Client  │ ───── HTTP :80 ────────▶│                  Nginx Proxy                    │   │
   │ Browser  │                     │   │                                                 │   │
   └──────────┘                     │   │  jellyfin.* ──▶ Jellyfin :8096                  │   │
                                    │   │  manager.*  ──▶ Manager  :8000                  │   │
                                    │   └─────────────────────────────────────────────────┘   │
                                    │                            │                             │
                                    │         ┌──────────────────┼──────────────────┐         │
                                    │         │                  │                  │         │
                                    │         ▼                  ▼                  ▼         │
                                    │   ┌──────────┐      ┌──────────┐      ┌──────────────┐  │
                                    │   │ Jellyfin │      │  Manager │      │  qBittorrent │  │
                                    │   │  :8096   │      │  :8000   │      │    :8080     │  │
                                    │   └────┬─────┘      └────┬─────┘      └──────┬───────┘  │
                                    │        │                 │                   │          │
                                    │        │           ┌─────┴─────┐             │          │
                                    │        │           │           │             │          │
                                    │        │           ▼           ▼             │          │
                                    │        │      ┌────────┐  ┌────────┐         │          │
                                    │        │      │ yt-dlp │  │ rclone │         │          │
                                    │        │      └────┬───┘  └────┬───┘         │          │
                                    │        │           │           │             │          │
                                    │        ▼           ▼           ▼             ▼          │
                                    │   ┌─────────────────────────────────────────────────┐   │
                                    │   │              External USB HDD                   │   │
                                    │   │        /media/boatflix/Expansion/media           │   │
                                    │   │  ┌───────┐┌───────┐┌───────┐┌───────┐┌─────────┐│   │
                                    │   │  │Movies ││ Shows ││ Music ││ Books ││Downloads││   │
                                    │   │  └───────┘└───────┘└───────┘└───────┘└─────────┘│   │
                                    │   └─────────────────────────────────────────────────┘   │
                                    │                            │                             │
                                    │   ┌──────────────┐         │         ┌──────────────┐   │
                                    │   │  ErsatzTV    │◀────────┘         │  Witty Pi 4  │   │
                                    │   │    :8409     │                   │  (Optional)  │   │
                                    │   └──────────────┘                   └──────────────┘   │
                                    └─────────────────────────────────────────────────────────┘
                                                                 │
                                                                 │ rclone bisync
                                                                 ▼
                                                        ┌──────────────────┐
                                                        │  S3-Compatible   │
                                                        │  Cloud Storage   │
                                                        │   (Optional)     │
                                                        └──────────────────┘
```

### Features

- **Jellyfin** - Stream movies, TV shows, and music to any device
- **ErsatzTV** - Create virtual TV channels from your media library
- **qBittorrent** - Download torrents with web UI
- **Download Manager** - Download videos with yt-dlp via web interface
- **Media Organizer** - Automatically sort and rename downloads
- **Cloud Sync** - Bidirectional sync to S3-compatible storage via rclone
- **Witty Pi 4 Support** - Scheduled power management for low-power operation

## Requirements

### Hardware

- **Raspberry Pi 5** (4GB or 8GB recommended)
- **External USB HDD** - For media storage (formatted ext4)
- **MicroSD Card** - 32GB+ for OS
- **Power Supply** - Official Pi 5 27W power supply recommended

### Optional

- **S3-compatible storage** - For cloud backup (AWS S3, DigitalOcean Spaces, Backblaze B2, MinIO, etc.)
- **Witty Pi 4** - For scheduled power on/off (great for solar/battery setups)

### Software

- Raspberry Pi OS (64-bit) - Bookworm or later
- Docker and Docker Compose (installed by setup script)

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/boatflix2.git
   cd boatflix2
   ```

2. **Run the setup script**
   ```bash
   chmod +x setup.sh
   sudo ./setup.sh
   ```

   The script will:
   - Install Docker and required dependencies
   - Set up your external USB HDD
   - Configure rclone for cloud sync (optional)
   - Create the systemd service
   - Start all containers

3. **Access your services**
   - Jellyfin: http://jellyfin.localhost or http://your-pi-ip:8096
   - Manager: http://manager.localhost or http://your-pi-ip:8000
   - qBittorrent: http://your-pi-ip:8080
   - ErsatzTV: http://your-pi-ip:8409

## Manual Installation

For advanced users who prefer manual setup:

### 1. Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Add user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install docker-compose-plugin -y

# Log out and back in for group changes
```

### 2. Install rclone (for cloud sync)

```bash
curl https://rclone.org/install.sh | sudo bash
```

### 3. Prepare External HDD

```bash
# Find your drive (usually /dev/sda)
lsblk

# Format as ext4 (WARNING: This erases all data!)
sudo mkfs.ext4 /dev/sda1

# Create mount point
sudo mkdir -p /media/boatflix/Expansion/media

# Add to fstab for auto-mount
echo "/dev/sda1 /media/boatflix/Expansion/media ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab

# Mount now
sudo mount -a

# Create folder structure
sudo mkdir -p /media/boatflix/Expansion/media/{Movies,Shows,Music,Commercials,Books,Downloads/{complete,incomplete}}
sudo chown -R 1000:1000 /media/boatflix/Expansion/media
```

### 4. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit with your settings
nano .env
```

### 5. Start Services

```bash
# Start all containers
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f
```

### 6. (Optional) Enable Systemd Service

```bash
# Copy service file
sudo cp systemd/boatflix2.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable boatflix2
sudo systemctl start boatflix2
```

## Configuration

### Environment Variables

Create a `.env` file from the example:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `PUID` | `1000` | User ID for file permissions |
| `PGID` | `1000` | Group ID for file permissions |
| `TZ` | `America/New_York` | Timezone for all services |
| `MEDIA_PATH` | `/media/boatflix/Expansion/media` | Path to media storage on host |
| `DOWNLOADS_PATH` | `/media/boatflix/Expansion/media/Downloads` | Torrent download directory |
| `TMDB_API_KEY` | (empty) | TheMovieDB API key for metadata (optional, free at themoviedb.org) |
| `RCLONE_REMOTE` | (empty) | Remote name from rclone.conf |
| `RCLONE_BUCKET` | (empty) | Bucket/path on remote storage |
| `RCLONE_CONFIG` | `./rclone.conf` | Path to rclone config file |
| `SYNC_CRON` | `0 2 * * *` | Cron schedule for sync (default: 2am daily) |
| `SYNC_ENABLED` | `true` | Enable/disable scheduled sync |

### rclone Setup

For cloud sync functionality, you need to configure rclone:

#### Option 1: Interactive Setup (recommended)

```bash
rclone config
```

Follow the prompts to add your S3-compatible storage provider.

#### Option 2: Manual Configuration

Create `rclone.conf` in the project root:

```ini
[s3]
type = s3
provider = Other
endpoint = https://your-endpoint.com
access_key_id = YOUR_ACCESS_KEY
secret_access_key = YOUR_SECRET_KEY
```

Then update `.env`:
```bash
RCLONE_REMOTE=s3
RCLONE_BUCKET=your-bucket-name
```

#### Test Connection

```bash
rclone lsd s3:your-bucket-name
```

### qBittorrent Initial Configuration

1. Access qBittorrent at http://your-pi-ip:8080
2. Default credentials: `admin` / `adminadmin`
3. **Change the password immediately** in Tools > Options > Web UI
4. Configure download paths:
   - Default Save Path: `/media/boatflix/Expansion/media/Downloads/complete`
   - Keep incomplete torrents in: `/media/boatflix/Expansion/media/Downloads/incomplete`

## Usage

### Accessing Jellyfin

1. Open http://jellyfin.localhost or http://your-pi-ip:8096
2. Complete initial setup wizard on first access
3. Add media libraries pointing to:
   - Movies: `/media/boatflix/Expansion/media/Movies`
   - Shows: `/media/boatflix/Expansion/media/Shows`
   - Music: `/media/boatflix/Expansion/media/Music`

### Downloading with yt-dlp

1. Access the Manager at http://manager.localhost
2. Go to the Download page
3. Paste a video URL (YouTube, Vimeo, etc.)
4. Select format options and download
5. Files are saved to `/media/boatflix/Expansion/media/Downloads`

### Organizing Torrents

1. Download torrents via qBittorrent
2. Access Manager > Organize page
3. Files in Downloads folder are listed with detected media type
4. Preview destination path and move to appropriate library folder
5. Jellyfin will automatically pick up new files

### S3 Sync Management

1. Access Manager > Sync page
2. View sync status, history, and logs
3. Trigger manual sync if needed
4. Scheduled syncs run automatically based on `SYNC_CRON`

**Sync behavior:**
- First sync uses `--resync` to establish baseline
- Subsequent syncs are incremental (bidirectional)
- Changes on either local or remote are synchronized
- Logs stored at `/app/data/sync.log` inside container

## Service URLs

| Path | Service | Description |
|------|---------|-------------|
| `http://jellyfin.localhost` | Jellyfin | Media streaming server |
| `http://manager.localhost` | Download Manager | yt-dlp downloads, organization, sync |
| `http://your-ip:8096` | Jellyfin (direct) | Direct access to Jellyfin |
| `http://your-ip:8409` | ErsatzTV | Virtual TV channel creation |
| `http://your-ip:8080` | qBittorrent | Torrent download client |
| `http://your-ip:8000` | Manager API | REST API for manager |

### Manager API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/download/` | POST | Submit download job |
| `/api/download/analyze` | POST | Analyze URL before download |
| `/api/download/queue` | GET | List pending/active downloads |
| `/api/download/history` | GET | Download history |
| `/api/organize/list` | GET | List items in Downloads |
| `/api/organize/move` | POST | Move file to library |
| `/api/sync/run` | POST | Trigger manual sync |
| `/api/sync/status` | GET | Get sync status |
| `/health` | GET | Health check |

## Troubleshooting

### Common Issues

#### Containers not starting
```bash
# Check container status
docker compose ps

# View logs for specific service
docker compose logs jellyfin
docker compose logs manager

# Restart all services
docker compose restart
```

#### Permission issues with media files
```bash
# Check ownership
ls -la /media/boatflix/Expansion/media

# Fix permissions (match PUID/PGID in .env)
sudo chown -R 1000:1000 /media/boatflix/Expansion/media
```

#### External HDD not mounting
```bash
# Check if drive is detected
lsblk

# Check fstab entry
cat /etc/fstab

# Manual mount attempt
sudo mount /dev/sda1 /media/boatflix/Expansion/media

# Check mount errors
dmesg | tail -20
```

#### rclone sync failing
```bash
# Test rclone configuration
rclone lsd ${RCLONE_REMOTE}:${RCLONE_BUCKET}

# Check sync logs (inside container)
docker exec manager cat /app/data/sync.log

# Manual sync test
docker exec manager rclone sync /media/boatflix/Expansion/media ${RCLONE_REMOTE}:${RCLONE_BUCKET} --dry-run
```

#### Jellyfin not finding media
- Ensure media is in correct folders (`Movies`, `Shows`, `Music`)
- Trigger library scan: Settings > Dashboard > Libraries > Scan All Libraries
- Check file permissions inside container

### Log Locations

| Log | Location | Access |
|-----|----------|--------|
| Setup script | `/var/log/boatflix2-setup.log` | Host system |
| Witty Pi | `/var/log/boatflix2-wittypi.log` | Host system |
| Docker logs | `docker compose logs [service]` | All containers |
| Sync logs | `/app/data/sync.log` | Manager container |
| Sync history | `/app/data/sync_history.json` | Manager container |

### Restart Procedures

```bash
# Restart single service
docker compose restart jellyfin

# Restart all services
docker compose restart

# Full stop and start
docker compose down
docker compose up -d

# Rebuild after code changes
docker compose build manager
docker compose up -d manager
```

## Updating

### Pull Latest Images

```bash
cd /path/to/boatflix2

# Pull latest images
docker compose pull

# Rebuild custom images (manager)
docker compose build --no-cache

# Restart with new images
docker compose down
docker compose up -d

# Clean up old images
docker image prune -f
```

### Update Boatflix2 Code

```bash
cd /path/to/boatflix2

# Pull latest code
git pull

# Rebuild and restart
docker compose build
docker compose down
docker compose up -d
```

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
