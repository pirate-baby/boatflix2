# Remote Transcode Quick Start Guide

## 🚀 One-Time MacBook Setup (5 minutes)

### 1. Enable SSH Server on MacBook
```bash
# On MacBook - Open System Settings → General → Sharing → Enable "Remote Login"
# Or via terminal:
sudo systemsetup -setremotelogin on
```

### 2. Copy SSH Private Key to Pi

**The private key is in:** `MACBOOK_SETUP_COMPLETE.md`

On your **Raspberry Pi**, save it to:
```bash
mkdir -p ~/boatflix-data/.ssh
nano ~/boatflix-data/.ssh/id_pi_transcode
# Paste the private key from MACBOOK_SETUP_COMPLETE.md
chmod 600 ~/boatflix-data/.ssh/id_pi_transcode
```

### 3. Test Connection from Pi
```bash
# On Pi
ssh -i ~/boatflix-data/.ssh/id_pi_transcode ethan@192.168.50.111 "echo 'SSH works!'"
```

### 4. Configure Boatflix on Pi

Add to your `.env` file:
```bash
REMOTE_TRANSCODE_ENABLED=true
REMOTE_TRANSCODE_HOST=192.168.50.111
REMOTE_TRANSCODE_USER=ethan
REMOTE_TRANSCODE_SSH_KEY=/app/data/.ssh/id_pi_transcode
```

Add to `docker-compose.yml`:
```yaml
volumes:
  - ~/boatflix-data/.ssh/id_pi_transcode:/app/data/.ssh/id_pi_transcode:ro
```

### 5. Restart & Verify
```bash
# On Pi
docker-compose restart manager
curl http://localhost:8000/api/transcode/remote/check | jq
```

## ✅ That's It!

Your transcodes will now automatically use the MacBook Pro's VideoToolbox hardware acceleration - **5-10x faster** than the Pi!

---

## 📚 Full Details

- **MacBook Setup Instructions**: `MACBOOK_SETUP_COMPLETE.md`
- **Complete Guide**: `REMOTE_TRANSCODE_SETUP.md`
- **Technical Details**: `REMOTE_TRANSCODE_SUMMARY.md`

## 🆘 Troubleshooting

**SSH fails?**
1. Check Remote Login is enabled on MacBook
2. Try IP instead of hostname: `192.168.50.111`

**MacBook sleeps?**
```bash
# On MacBook
caffeinate -s
```

**Slow transfers?**
Use wired Ethernet instead of WiFi on both devices
