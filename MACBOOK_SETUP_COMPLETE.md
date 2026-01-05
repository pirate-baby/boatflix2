# MacBook Pro Remote Transcode Setup - READY TO USE

Your MacBook Pro is now configured as a remote transcode server for Boatflix!

## ✅ What's Already Done

1. **ffmpeg installed** with VideoToolbox hardware acceleration
2. **SSH key pair generated** at `~/.ssh/boatflix/id_pi_transcode`
3. **Public key added** to `~/.ssh/authorized_keys`

## 📋 Your MacBook Details

```
Hostname: Pirate-Baby-Pro.local
IP Address: 192.168.50.111
Username: ethan
SSH Port: 22 (default)
```

## 🔧 Next Steps

### Step 1: Enable Remote Login (SSH Server)

You need to enable SSH server on this MacBook:

1. Open **System Settings** (or System Preferences on older macOS)
2. Go to **General** → **Sharing** (or just **Sharing** on older macOS)
3. Enable **Remote Login**
4. Make sure "ethan" is in the allowed users list

**Alternative - Enable via Terminal (requires admin password):**
```bash
sudo systemsetup -setremotelogin on
```

### Step 2: Copy SSH Private Key to Raspberry Pi

The private key needs to be on your Raspberry Pi. Copy this key to your Pi:

**Private key location on MacBook:**
```
/Users/ethan/.ssh/boatflix/id_pi_transcode
```

**On your Raspberry Pi**, create the directory and save the key:

```bash
# On Pi
mkdir -p ~/boatflix-data/.ssh
chmod 700 ~/boatflix-data/.ssh
```

Then copy the private key content below and save it to `~/boatflix-data/.ssh/id_pi_transcode`:

```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBt2XoIjIPXIgtwyXiw8a8yKEBqkq9Mrsv+TFzE9bL/FwAAAJgcYEU0HGBF
NAAAAAtzc2gtZWQyNTUxOQAAACBt2XoIjIPXIgtwyXiw8a8yKEBqkq9Mrsv+TFzE9bL/Fw
AAAECgslvRW2ir3hRT1bTCcEguN/xckbLTeRhQdELKpW17m23ZegiMg9ciC3DJeLDxrzIo
QGqSr0yuy/5MXMT1sv8XAAAAFWJvYXRmbGl4LXBpLXRyYW5zY29kZQ==
-----END OPENSSH PRIVATE KEY-----
```

**Set correct permissions:**
```bash
# On Pi
chmod 600 ~/boatflix-data/.ssh/id_pi_transcode
```

### Step 3: Test SSH Connection from Pi

Once you've copied the key to your Pi, test the connection:

```bash
# On Pi
ssh -i ~/boatflix-data/.ssh/id_pi_transcode ethan@192.168.50.111 "echo 'SSH works!'"
```

You should see "SSH works!" without being prompted for a password.

**If using hostname instead of IP:**
```bash
# On Pi
ssh -i ~/boatflix-data/.ssh/id_pi_transcode ethan@Pirate-Baby-Pro.local "echo 'SSH works!'"
```

### Step 4: Configure Boatflix Manager

Add these environment variables to your Boatflix `.env` file (on the Pi):

```bash
# Enable remote transcoding
REMOTE_TRANSCODE_ENABLED=true

# MacBook connection details
REMOTE_TRANSCODE_HOST=192.168.50.111
REMOTE_TRANSCODE_USER=ethan
REMOTE_TRANSCODE_SSH_KEY=/app/data/.ssh/id_pi_transcode
REMOTE_TRANSCODE_PORT=22
REMOTE_TRANSCODE_WORK_DIR=/tmp/boatflix-transcode
```

**Note:** Use IP address (`192.168.50.111`) if `.local` hostname resolution doesn't work on your network.

### Step 5: Update docker-compose.yml

Mount the SSH key in your docker-compose.yml:

```yaml
services:
  manager:
    volumes:
      - ./data:/app/data
      # Add this line to mount the SSH key:
      - ~/boatflix-data/.ssh/id_pi_transcode:/app/data/.ssh/id_pi_transcode:ro
      # ... other volumes
```

Or simply copy the key to your existing data directory:

```bash
# On Pi
cp ~/boatflix-data/.ssh/id_pi_transcode ./data/.ssh/
chmod 600 ./data/.ssh/id_pi_transcode
```

### Step 6: Restart Boatflix Manager

```bash
# On Pi
docker-compose restart manager
```

### Step 7: Verify Remote Transcode Setup

Check the configuration:

```bash
# On Pi
curl http://localhost:8000/api/transcode/remote/check | jq
```

Expected output:
```json
{
  "enabled": true,
  "accessible": true,
  "host": "192.168.50.111",
  "user": "ethan",
  "ffmpeg_available": true,
  "ffmpeg_path": "/opt/homebrew/bin/ffmpeg",
  "hardware_encoders": ["videotoolbox"]
}
```

## 🧪 Testing Remote Transcode

Once configured, test with a single video:

```bash
# On Pi
curl -X POST http://localhost:8000/api/transcode/video \
  -H "Content-Type: application/json" \
  -d '{"video_path": "/mnt/media/Movies/TestMovie/test.mkv"}'

# Watch the logs
curl http://localhost:8000/api/transcode/logs?lines=50 | jq -r '.logs[]'
```

Look for:
- "Using remote transcode on 192.168.50.111"
- "Remote: Transferring source file..."
- "Remote: Transcoding on remote host..."
- "Remote transcode complete"

## ⚙️ MacBook Performance Settings (Optional)

To prevent your MacBook from sleeping during long transcodes:

### Prevent Sleep Temporarily
```bash
# On MacBook - keeps awake while command runs
caffeinate -s
```

### Prevent Sleep Permanently (when plugged in)
```bash
# On MacBook - disable sleep when connected to power
sudo pmset -c sleep 0
sudo pmset -c disksleep 0

# To restore default sleep settings:
sudo pmset -c sleep 10
sudo pmset -c disksleep 10
```

## 📊 Expected Performance

Your MacBook Pro with VideoToolbox should transcode:
- **1080p**: ~5-15 minutes per hour of video
- **4K**: ~10-30 minutes per hour of video

This is **5-10x faster** than the Raspberry Pi's CPU transcoding!

## 🔒 Security Notes

- The SSH key grants access to your MacBook - keep it secure
- Remote Login is only needed when you want to transcode
- Consider disabling Remote Login when not actively transcoding (if security is a concern)
- The key is restricted to SSH access only (no other permissions)

## 🐛 Troubleshooting

### Can't enable Remote Login
- Make sure you have admin privileges
- Try the Terminal command with sudo (see Step 1)

### SSH connection fails
1. Verify Remote Login is enabled on MacBook
2. Check both machines are on the same network
3. Try IP address instead of hostname
4. Verify key permissions: `chmod 600 ~/boatflix-data/.ssh/id_pi_transcode`

### MacBook goes to sleep during transcode
- Use `caffeinate -s` on MacBook
- Or change power settings (see Performance Settings above)

### Slow transfer speeds
- Ensure both devices are on wired Ethernet (not WiFi)
- Check network speed: `iperf3 -s` on MacBook, `iperf3 -c 192.168.50.111` on Pi

## 📁 File Locations Reference

**On MacBook:**
- Private key: `/Users/ethan/.ssh/boatflix/id_pi_transcode`
- Public key: `/Users/ethan/.ssh/boatflix/id_pi_transcode.pub`
- Authorized keys: `/Users/ethan/.ssh/authorized_keys`
- Work directory: `/tmp/boatflix-transcode` (created automatically)

**On Raspberry Pi:**
- Private key (to copy here): `~/boatflix-data/.ssh/id_pi_transcode`
- Or in Docker data: `./data/.ssh/id_pi_transcode`

## ✅ Quick Checklist

- [ ] Enable Remote Login on MacBook (System Settings → Sharing)
- [ ] Copy private key to Raspberry Pi
- [ ] Test SSH connection from Pi to MacBook
- [ ] Add environment variables to .env
- [ ] Mount SSH key in docker-compose.yml
- [ ] Restart Boatflix manager
- [ ] Verify with `/api/transcode/remote/check`
- [ ] Test with a single video
- [ ] Run bulk transcode on your massive library!

## 🎉 You're Ready!

Your MacBook Pro is fully configured. Just enable Remote Login and copy the key to your Pi, then you're ready to transcode your massive library at 5-10x speed!
