# 🚀 Final Setup Steps - 3 Quick Actions

Your MacBook is configured! Just complete these 3 steps to enable **5-10x faster transcoding**.

## Step 1: Enable Remote Login on MacBook (1 minute)

1. Open **System Settings** (click  → System Settings)
2. Go to **General** → **Sharing**
3. Toggle **"Remote Login"** ON
4. Confirm "ethan" is in allowed users

✅ **Done!** SSH server is now running.

---

## Step 2: Copy SSH Key to Raspberry Pi (2 minutes)

### On your Raspberry Pi, run these commands:

```bash
# Create directory
mkdir -p ~/boatflix-data/.ssh
chmod 700 ~/boatflix-data/.ssh

# Create the key file
nano ~/boatflix-data/.ssh/id_pi_transcode
```

### Paste this private key into nano:

```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBt2XoIjIPXIgtwyXiw8a8yKEBqkq9Mrsv+TFzE9bL/FwAAAJgcYEU0HGBF
NAAAAAtzc2gtZWQyNTUxOQAAACBt2XoIjIPXIgtwyXiw8a8yKEBqkq9Mrsv+TFzE9bL/Fw
AAAECgslvRW2ir3hRT1bTCcEguN/xckbLTeRhQdELKpW17m23ZegiMg9ciC3DJeLDxrzIo
QGqSr0yuy/5MXMT1sv8XAAAAFWJvYXRmbGl4LXBpLXRyYW5zY29kZQ==
-----END OPENSSH PRIVATE KEY-----
```

**Save:** Ctrl+O, Enter, Ctrl+X

### Set permissions:

```bash
chmod 600 ~/boatflix-data/.ssh/id_pi_transcode
```

### Test connection:

```bash
ssh -i ~/boatflix-data/.ssh/id_pi_transcode ethan@192.168.50.111 "echo 'Connected!'"
```

You should see "Connected!" ✅

---

## Step 3: Configure Boatflix on Pi (2 minutes)

### Add to your `.env` file:

```bash
REMOTE_TRANSCODE_ENABLED=true
REMOTE_TRANSCODE_HOST=192.168.50.111
REMOTE_TRANSCODE_USER=ethan
REMOTE_TRANSCODE_SSH_KEY=/app/data/.ssh/id_pi_transcode
```

### Update `docker-compose.yml`:

Add this volume mount:

```yaml
services:
  manager:
    volumes:
      - ~/boatflix-data/.ssh/id_pi_transcode:/app/data/.ssh/id_pi_transcode:ro
```

### Restart Boatflix:

```bash
docker-compose restart manager
```

### Verify it works:

```bash
curl http://localhost:8000/api/transcode/remote/check | jq
```

**Expected output:**
```json
{
  "enabled": true,
  "accessible": true,
  "ffmpeg_available": true,
  "hardware_encoders": ["videotoolbox"]
}
```

✅ **Done!** Remote transcoding is active.

---

## 🎉 You're Ready!

Transcoding will now automatically use your MacBook Pro's VideoToolbox:

- **1080p**: ~5-15 min per hour (vs 60-120 min on Pi)
- **4K**: ~10-30 min per hour (vs 180-360+ min on Pi)
- **Your massive library**: Days instead of weeks!

### Test with a single video:

```bash
curl -X POST http://localhost:8000/api/transcode/video \
  -H "Content-Type: application/json" \
  -d '{"video_path": "/mnt/media/Movies/SomeMovie/movie.mkv"}'
```

### Watch the logs:

```bash
curl http://localhost:8000/api/transcode/logs?lines=50
```

Look for:
- "Using remote transcode on 192.168.50.111"
- "Remote: Transferring source file..."
- "Remote transcode complete"

---

## 📚 Need Help?

- **Troubleshooting:** See `COPY_KEY_TO_PI.md`
- **Complete guide:** See `REMOTE_TRANSCODE_SETUP.md`
- **Verification:** Run `./verify-macbook-setup.sh` on MacBook

---

## ⚡ Performance Tips

**Keep MacBook awake during transcoding:**
```bash
# On MacBook
caffeinate -s
```

**Use wired Ethernet** on both devices for fastest transfer speeds.

**Monitor progress:**
```bash
# On Pi
curl http://localhost:8000/api/transcode/status
```

---

## 🎯 Quick Reference

**MacBook Details:**
- Host: `192.168.50.111` (or `Pirate-Baby-Pro.local`)
- User: `ethan`
- SSH Port: `22`

**Pi Details:**
- Host: `boatflix.local`
- User: `boatflix`

**Key Location:**
- MacBook: `~/.ssh/boatflix/id_pi_transcode`
- Pi: `~/boatflix-data/.ssh/id_pi_transcode`

---

That's it! 🚀 Your setup is complete and ready to transcode at 5-10x speed!
