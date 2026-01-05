# Remote Transcoding Setup Guide

This guide explains how to configure Boatflix to use a more powerful machine (like your MacBook Pro) for video transcoding over SSH, while the Raspberry Pi continues to serve files.

## Overview

Remote transcoding allows you to:
- Use a powerful Mac/PC with hardware acceleration (VideoToolbox, NVENC, etc.)
- Significantly speed up bulk transcoding of your media library
- Keep files on the Pi's network storage
- Automatically fall back to local transcoding if the remote host is unavailable

## Architecture

```
┌─────────────────┐
│  Raspberry Pi   │
│  (Manager API)  │
│                 │
│  1. Detects     │
│     incompatible│
│     video       │
└────────┬────────┘
         │
         │ 2. SSH to MacBook
         ▼
┌─────────────────┐
│   MacBook Pro   │
│                 │
│  3. rsync video │◄───┐
│  4. Transcode   │    │
│     (VideoTool) │    │ Fast Local Network
│  5. rsync back  │────┘
└─────────────────┘
         │
         ▼
┌─────────────────┐
│  Raspberry Pi   │
│  (Storage)      │
│                 │
│  6. Archive     │
│     original    │
│  7. Serve new   │
│     file        │
└─────────────────┘
```

## Requirements

### On the Raspberry Pi:
- SSH client (`ssh`, `rsync`) - usually pre-installed
- Network access to the MacBook
- SSH key authentication configured (passwordless)

### On the MacBook Pro:
- SSH server enabled (System Preferences → Sharing → Remote Login)
- `ffmpeg` with VideoToolbox support installed
- Sufficient disk space for temporary transcoding (at least 2x largest video file)
- Network access from the Pi

## Setup Instructions

### Step 1: Enable SSH on MacBook

1. Open **System Preferences** → **Sharing**
2. Enable **Remote Login**
3. Note your MacBook's hostname or IP address (e.g., `macbook-pro.local` or `192.168.1.100`)
4. Note your username (e.g., `yourname`)

### Step 2: Install ffmpeg on MacBook

```bash
# Using Homebrew
brew install ffmpeg

# Verify VideoToolbox support
ffmpeg -encoders | grep h264_videotoolbox
```

You should see output like: `V..... h264_videotoolbox  H.264 (VideoToolbox acceleration)`

### Step 3: Set up SSH Key Authentication

On your **Raspberry Pi**, generate an SSH key if you don't have one:

```bash
# On Pi
ssh-keygen -t ed25519 -f ~/.ssh/id_boatflix_transcode -N ""
```

Copy the public key to your MacBook:

```bash
# On Pi
ssh-copy-id -i ~/.ssh/id_boatflix_transcode.pub yourname@macbook-pro.local
```

Test the connection:

```bash
# On Pi
ssh -i ~/.ssh/id_boatflix_transcode yourname@macbook-pro.local "echo 'SSH works!'"
```

You should see "SSH works!" without being prompted for a password.

### Step 4: Configure Boatflix Manager

Add the following to your `.env` file (or docker-compose environment variables):

```bash
# Enable remote transcoding
REMOTE_TRANSCODE_ENABLED=true

# MacBook connection details
REMOTE_TRANSCODE_HOST=macbook-pro.local  # or IP address like 192.168.1.100
REMOTE_TRANSCODE_USER=yourname
REMOTE_TRANSCODE_SSH_KEY=/app/data/.ssh/id_boatflix_transcode
REMOTE_TRANSCODE_PORT=22

# Working directory on MacBook (will be created automatically)
REMOTE_TRANSCODE_WORK_DIR=/tmp/boatflix-transcode
```

### Step 5: Mount SSH Key in Docker

Update your `docker-compose.yml` to mount the SSH key:

```yaml
services:
  manager:
    volumes:
      - ./data:/app/data
      - ~/.ssh/id_boatflix_transcode:/app/data/.ssh/id_boatflix_transcode:ro
      # ... other volumes
```

Or if you store the key in the data directory:

```bash
# On Pi, copy the key to the data directory
mkdir -p ./data/.ssh
cp ~/.ssh/id_boatflix_transcode ./data/.ssh/
chmod 600 ./data/.ssh/id_boatflix_transcode
```

### Step 6: Restart Manager Service

```bash
docker-compose restart manager
```

### Step 7: Verify Configuration

Check the transcode configuration via API:

```bash
curl http://localhost:8000/api/transcode/config | jq
```

You should see:
```json
{
  "remote_transcode_enabled": true,
  "remote_transcode_host": "macbook-pro.local",
  ...
}
```

Test the remote connection:

```bash
curl http://localhost:8000/api/transcode/remote/check | jq
```

Expected response:
```json
{
  "enabled": true,
  "accessible": true,
  "host": "macbook-pro.local",
  "ffmpeg_available": true,
  "ffmpeg_path": "/usr/local/bin/ffmpeg",
  "hardware_encoders": ["videotoolbox"]
}
```

## Usage

Once configured, remote transcoding is **automatic**. When you trigger a transcode operation:

1. The manager checks if remote transcoding is enabled
2. If yes, it uses the MacBook; if no (or if it fails), it falls back to local Pi transcoding
3. You can monitor progress in the transcode logs

### Triggering Transcodes

**Transcode a single video:**
```bash
curl -X POST http://localhost:8000/api/transcode/video \
  -H "Content-Type: application/json" \
  -d '{"video_path": "/mnt/media/Movies/Example/example.mkv"}'
```

**Transcode entire directory:**
```bash
curl -X POST http://localhost:8000/api/transcode/directory \
  -H "Content-Type: application/json" \
  -d '{"directory": "/mnt/media/Movies", "recursive": true}'
```

**Check transcode logs:**
```bash
curl http://localhost:8000/api/transcode/logs?lines=50
```

## Performance Expectations

Typical MacBook Pro (M1/M2/M3 with VideoToolbox):
- **1080p video**: 5-15 minutes per hour of content
- **4K video**: 10-30 minutes per hour of content
- **Network transfer**: ~5-10 minutes per GB on gigabit network

Typical Raspberry Pi 4 (software encoding):
- **1080p video**: 60-120 minutes per hour of content
- **4K video**: 180-360+ minutes per hour of content

**Expected speedup: 5-10x faster with MacBook Pro**

## Troubleshooting

### "Remote host not accessible" error

1. Verify SSH connection manually:
   ```bash
   ssh -i ~/.ssh/id_boatflix_transcode yourname@macbook-pro.local
   ```

2. Check if MacBook is on the network:
   ```bash
   ping macbook-pro.local
   ```

3. Verify SSH key permissions:
   ```bash
   ls -l ~/.ssh/id_boatflix_transcode  # Should be 600
   ```

### "ffmpeg not available on remote host" error

1. SSH to MacBook and check:
   ```bash
   which ffmpeg
   ffmpeg -version
   ```

2. Install if missing:
   ```bash
   brew install ffmpeg
   ```

### Slow transfer speeds

1. Check your network speed:
   ```bash
   iperf3 -c macbook-pro.local
   ```

2. Consider using wired Ethernet instead of WiFi
3. Ensure no other heavy network activity during transcoding

### MacBook goes to sleep during transcoding

Prevent sleep while SSH sessions are active:

```bash
# On MacBook
sudo pmset -c sleep 0
sudo pmset -c disksleep 0
```

Or use `caffeinate`:

```bash
# On MacBook, run this before starting transcoding
caffeinate -s &
```

## Disabling Remote Transcoding

To temporarily disable remote transcoding without removing the configuration:

```bash
# In .env
REMOTE_TRANSCODE_ENABLED=false
```

Then restart the manager service.

## Security Considerations

- The SSH key grants access to your MacBook - keep it secure
- Consider restricting the SSH key to only run specific commands (advanced)
- Use a firewall to limit SSH access to your local network only
- Regularly update ffmpeg on both Pi and MacBook for security patches

## Advanced Configuration

### Custom Work Directory

If `/tmp` fills up, use a different directory:

```bash
REMOTE_TRANSCODE_WORK_DIR=/Users/yourname/boatflix-transcode
```

Make sure the user has write permissions:
```bash
# On MacBook
mkdir -p /Users/yourname/boatflix-transcode
```

### Custom SSH Port

If your MacBook uses a non-standard SSH port:

```bash
REMOTE_TRANSCODE_PORT=2222
```

### Force Remote or Local

To always use remote (never fall back to local):
- Modify the code in `services/transcode.py` to not catch remote exceptions
- Not recommended for production use

To always use local (disable remote):
```bash
REMOTE_TRANSCODE_ENABLED=false
```

## FAQ

**Q: Can I use a Windows PC instead of a Mac?**
A: Yes! Just install ffmpeg with NVENC support (requires NVIDIA GPU) and enable SSH server (via OpenSSH or WSL2).

**Q: Will this work over the internet?**
A: Technically yes, but not recommended due to bandwidth requirements. Best for local networks.

**Q: Can multiple Pis share one transcode machine?**
A: Yes, but they'll queue up since the transcode service prevents concurrent jobs.

**Q: What happens if the MacBook disconnects mid-transcode?**
A: The manager will detect the failure and automatically fall back to local transcoding.

**Q: Can I manually trigger remote vs local?**
A: Not currently via API, but you can toggle `REMOTE_TRANSCODE_ENABLED` in the config.

## Support

For issues or questions:
1. Check the transcode logs: `curl http://localhost:8000/api/transcode/logs?lines=100`
2. Test the remote connection: `curl http://localhost:8000/api/transcode/remote/check`
3. Review this guide's troubleshooting section
4. Open an issue on GitHub with logs and configuration details
