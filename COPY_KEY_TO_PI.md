# Copy SSH Key to Raspberry Pi - Manual Instructions

Since password-based SSH isn't working from the MacBook, here are alternative methods to copy the key to your Pi.

## Option 1: Display Key and Copy Manually (Easiest)

### Step 1: Display the Private Key on MacBook

Run this on your **MacBook**:

```bash
cat ~/.ssh/boatflix/id_pi_transcode
```

**Copy the entire output** (including the BEGIN and END lines).

### Step 2: SSH to Pi and Save the Key

On your **MacBook**, SSH to the Pi using whatever method works for you, then:

```bash
# Create directory
mkdir -p ~/boatflix-data/.ssh
chmod 700 ~/boatflix-data/.ssh

# Create and edit the key file
nano ~/boatflix-data/.ssh/id_pi_transcode
```

**Paste the private key** you copied in Step 1, then save (Ctrl+O, Enter, Ctrl+X).

### Step 3: Set Permissions

```bash
chmod 600 ~/boatflix-data/.ssh/id_pi_transcode
```

### Step 4: Test Connection from Pi to MacBook

```bash
ssh -i ~/boatflix-data/.ssh/id_pi_transcode ethan@192.168.50.111 "echo 'Success!'"
```

You should see "Success!" (after enabling Remote Login on MacBook).

---

## Option 2: Copy via File Sharing

### On MacBook:

1. Copy the key file to your Desktop:
   ```bash
   cp ~/.ssh/boatflix/id_pi_transcode ~/Desktop/
   ```

2. Transfer to Pi using:
   - **USB drive** - Copy to drive, plug into Pi
   - **SCP from another computer** that has access to both
   - **File sharing** - If you have Samba/NFS set up

### On Pi:

```bash
# Move key to correct location
mkdir -p ~/boatflix-data/.ssh
mv ~/Desktop/id_pi_transcode ~/boatflix-data/.ssh/
chmod 600 ~/boatflix-data/.ssh/id_pi_transcode
```

---

## Option 3: Using the Web Terminal (if available)

If your Boatflix setup has a web terminal or SSH access through another tool:

1. Display key on MacBook:
   ```bash
   cat ~/.ssh/boatflix/id_pi_transcode
   ```

2. Copy the output

3. In web terminal on Pi:
   ```bash
   mkdir -p ~/boatflix-data/.ssh
   cat > ~/boatflix-data/.ssh/id_pi_transcode << 'EOF'
   [PASTE KEY HERE]
   EOF
   chmod 600 ~/boatflix-data/.ssh/id_pi_transcode
   ```

---

## The Private Key (for reference)

**Location on MacBook:** `~/.ssh/boatflix/id_pi_transcode`

**Key content:**
```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBt2XoIjIPXIgtwyXiw8a8yKEBqkq9Mrsv+TFzE9bL/FwAAAJgcYEU0HGBF
NAAAAAtzc2gtZWQyNTUxOQAAACBt2XoIjIPXIgtwyXiw8a8yKEBqkq9Mrsv+TFzE9bL/Fw
AAAECgslvRW2ir3hRT1bTCcEguN/xckbLTeRhQdELKpW17m23ZegiMg9ciC3DJeLDxrzIo
QGqSr0yuy/5MXMT1sv8XAAAAFWJvYXRmbGl4LXBpLXRyYW5zY29kZQ==
-----END OPENSSH PRIVATE KEY-----
```

**IMPORTANT:** This is a private key - keep it secure! Only store on the Pi.

---

## After Copying the Key

### 1. Test the Connection

```bash
# On Pi
ssh -i ~/boatflix-data/.ssh/id_pi_transcode ethan@192.168.50.111 "echo 'Connected!'"
```

**Note:** Make sure Remote Login is enabled on the MacBook first!

### 2. Add to Docker Volume

Update your `docker-compose.yml` to mount the key:

```yaml
services:
  manager:
    volumes:
      - ./data:/app/data
      - ~/boatflix-data/.ssh/id_pi_transcode:/app/data/.ssh/id_pi_transcode:ro
```

Or copy to the Docker data directory:

```bash
# On Pi
mkdir -p ./data/.ssh
cp ~/boatflix-data/.ssh/id_pi_transcode ./data/.ssh/
chmod 600 ./data/.ssh/id_pi_transcode
```

### 3. Add Environment Variables

Add to your `.env` file on Pi:

```bash
REMOTE_TRANSCODE_ENABLED=true
REMOTE_TRANSCODE_HOST=192.168.50.111
REMOTE_TRANSCODE_USER=ethan
REMOTE_TRANSCODE_SSH_KEY=/app/data/.ssh/id_pi_transcode
```

### 4. Restart Boatflix

```bash
docker-compose restart manager
```

### 5. Verify Setup

```bash
curl http://localhost:8000/api/transcode/remote/check | jq
```

---

## Troubleshooting

**"Permission denied" when testing connection:**
- Make sure Remote Login is enabled on MacBook
- Check key permissions: `ls -l ~/boatflix-data/.ssh/id_pi_transcode` (should be 600)

**"No such file or directory":**
- Make sure you created the directory: `mkdir -p ~/boatflix-data/.ssh`
- Check the key was saved correctly: `cat ~/boatflix-data/.ssh/id_pi_transcode`

**Key doesn't work:**
- Verify the key content matches exactly (including BEGIN/END lines)
- No extra spaces or line breaks
- Permissions must be 600

---

## Alternative: Generate Key on Pi

If copying is difficult, you can generate a new key pair on the Pi and copy the **public** key to the MacBook instead:

```bash
# On Pi
ssh-keygen -t ed25519 -f ~/boatflix-data/.ssh/id_pi_transcode -N ""

# Display public key
cat ~/boatflix-data/.ssh/id_pi_transcode.pub
```

Then on **MacBook**:
```bash
# Add Pi's public key to authorized_keys
echo "PASTE_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

This achieves the same result but in reverse direction.
