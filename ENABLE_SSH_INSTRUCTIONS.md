# Enable SSH Server on Your MacBook Pro

## Quick Steps (2 minutes)

### Method 1: Using System Settings (Recommended)

1. **Open System Settings**
   - Click the Apple menu () → System Settings

2. **Navigate to Sharing**
   - Click "General" in the sidebar
   - Click "Sharing"

3. **Enable Remote Login**
   - Toggle "Remote Login" to ON (blue)
   - You should see: "Remote Login: On"
   - Allow access for: "Only these users" → Make sure "ethan" is in the list

4. **Note the connection info**
   - You should see something like: "To log in to this computer remotely, type 'ssh ethan@192.168.50.111'"

That's it! SSH is now enabled.

---

### Method 2: Using Terminal (Alternative)

If you prefer terminal and have Full Disk Access configured:

```bash
sudo systemsetup -setremotelogin on
```

**Note:** This requires entering your admin password and Full Disk Access permissions for Terminal.

---

## Verify SSH is Running

Run this command to check if SSH is enabled:

```bash
sudo launchctl list | grep com.openssh.sshd
```

You should see output like:
```
-    0    com.openssh.sshd-keygen-wrapper
-    0    com.openssh.sshd
```

Or simply try connecting to yourself:

```bash
ssh ethan@localhost "echo 'SSH is working!'"
```

---

## What's Next?

After enabling Remote Login, you're ready to:

1. ✅ Copy the SSH private key to your Raspberry Pi
2. ✅ Test the connection from Pi to MacBook
3. ✅ Configure Boatflix to use remote transcoding

See **QUICKSTART.md** for the complete setup steps.

---

## Security Note

Remote Login allows SSH access to your MacBook. For security:
- Only enable when you need to transcode
- Your network firewall should block external SSH access
- Only your Pi needs the SSH key - keep it secure
- You can disable Remote Login when not transcoding (optional)

---

## Troubleshooting

**"Remote Login" option is grayed out:**
- Make sure you have admin privileges
- Try restarting System Settings

**Can't find "Sharing" in System Settings:**
- On older macOS: System Preferences → Sharing (at the same level as other icons)
- On newer macOS: System Settings → General → Sharing

**Want to disable later:**
- Just toggle "Remote Login" back to OFF in the same location
