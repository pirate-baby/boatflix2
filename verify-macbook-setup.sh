#!/bin/bash
# Verification script for MacBook Pro remote transcode setup

echo "🔍 MacBook Pro Remote Transcode Setup Verification"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SUCCESS="${GREEN}✓${NC}"
FAILURE="${RED}✗${NC}"
WARNING="${YELLOW}⚠${NC}"

# Track overall status
ALL_GOOD=true

echo "1. Checking SSH Server Status..."
if sudo launchctl list | grep -q "com.openssh.sshd"; then
    echo -e "   ${SUCCESS} SSH server is running"
else
    echo -e "   ${FAILURE} SSH server is NOT running"
    echo -e "   ${WARNING} Please enable Remote Login in System Settings → General → Sharing"
    ALL_GOOD=false
fi
echo ""

echo "2. Checking ffmpeg installation..."
if command -v ffmpeg &> /dev/null; then
    FFMPEG_PATH=$(which ffmpeg)
    echo -e "   ${SUCCESS} ffmpeg found at: $FFMPEG_PATH"

    # Check for VideoToolbox
    if ffmpeg -hide_banner -encoders 2>&1 | grep -q "h264_videotoolbox"; then
        echo -e "   ${SUCCESS} VideoToolbox encoder available"
    else
        echo -e "   ${WARNING} VideoToolbox encoder not found (will use software encoding)"
    fi
else
    echo -e "   ${FAILURE} ffmpeg not found"
    echo -e "   ${WARNING} Install with: brew install ffmpeg"
    ALL_GOOD=false
fi
echo ""

echo "3. Checking SSH key pair..."
if [ -f ~/.ssh/boatflix/id_pi_transcode ]; then
    echo -e "   ${SUCCESS} Private key exists: ~/.ssh/boatflix/id_pi_transcode"
else
    echo -e "   ${FAILURE} Private key not found"
    ALL_GOOD=false
fi

if [ -f ~/.ssh/boatflix/id_pi_transcode.pub ]; then
    echo -e "   ${SUCCESS} Public key exists: ~/.ssh/boatflix/id_pi_transcode.pub"
else
    echo -e "   ${FAILURE} Public key not found"
    ALL_GOOD=false
fi

if grep -q "boatflix-pi-transcode" ~/.ssh/authorized_keys 2>/dev/null; then
    echo -e "   ${SUCCESS} Public key added to authorized_keys"
else
    echo -e "   ${WARNING} Public key might not be in authorized_keys"
fi
echo ""

echo "4. Checking network configuration..."
HOSTNAME=$(hostname)
IP_ADDRESS=$(ipconfig getifaddr en0 2>/dev/null || echo "Not connected")
echo -e "   Hostname: ${YELLOW}$HOSTNAME${NC}"
echo -e "   IP Address: ${YELLOW}$IP_ADDRESS${NC}"
if [ "$IP_ADDRESS" != "Not connected" ]; then
    echo -e "   ${SUCCESS} Network interface active"
else
    echo -e "   ${WARNING} No IP address on en0 (might be using WiFi or different interface)"
fi
echo ""

echo "5. Testing local SSH connection..."
if ssh -o BatchMode=yes -o ConnectTimeout=5 ethan@localhost "echo 'test'" &> /dev/null; then
    echo -e "   ${SUCCESS} Can SSH to localhost"
else
    echo -e "   ${WARNING} Cannot SSH to localhost (might need to accept fingerprint first)"
    echo -e "   ${WARNING} Try manually: ssh ethan@localhost"
fi
echo ""

echo "6. Checking work directory permissions..."
WORK_DIR="/tmp/boatflix-transcode"
if [ -w "/tmp" ]; then
    echo -e "   ${SUCCESS} Can write to /tmp (work directory will be: $WORK_DIR)"
else
    echo -e "   ${FAILURE} Cannot write to /tmp"
    ALL_GOOD=false
fi
echo ""

echo "=================================================="
echo ""

if $ALL_GOOD; then
    echo -e "${GREEN}🎉 MacBook setup looks good!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. If SSH server is not running, enable Remote Login in System Settings"
    echo "2. Copy the private key to your Raspberry Pi"
    echo "3. Test connection from Pi: ssh -i <key> ethan@$IP_ADDRESS"
    echo "4. Configure Boatflix with the settings in .env.macbook-remote"
    echo ""
    echo "See QUICKSTART.md for detailed instructions."
else
    echo -e "${RED}⚠️  Some issues found - please review above${NC}"
    echo ""
    echo "Most common fixes:"
    echo "• Enable Remote Login: System Settings → General → Sharing → Remote Login"
    echo "• Install ffmpeg: brew install ffmpeg"
    echo ""
fi

echo ""
echo "Your MacBook details for Boatflix configuration:"
echo "------------------------------------------------"
echo "REMOTE_TRANSCODE_HOST=$IP_ADDRESS"
echo "REMOTE_TRANSCODE_USER=ethan"
echo "REMOTE_TRANSCODE_SSH_KEY=/app/data/.ssh/id_pi_transcode"
echo ""
