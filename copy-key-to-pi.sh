#!/bin/bash
# Script to copy SSH key to Raspberry Pi
# This will prompt for the Pi password (boatflix)

echo "🔑 Copying SSH key to Raspberry Pi..."
echo ""
echo "Pi Details:"
echo "  Host: boatflix.local"
echo "  User: boatflix"
echo "  Password: boatflix"
echo ""

# Create directory on Pi
echo "Step 1: Creating .ssh directory on Pi..."
ssh boatflix@boatflix.local "mkdir -p ~/boatflix-data/.ssh && chmod 700 ~/boatflix-data/.ssh"

if [ $? -eq 0 ]; then
    echo "✓ Directory created"
else
    echo "✗ Failed to create directory"
    echo "You may need to enter the password: boatflix"
    exit 1
fi

# Copy private key to Pi
echo ""
echo "Step 2: Copying private key to Pi..."
scp ~/.ssh/boatflix/id_pi_transcode boatflix@boatflix.local:~/boatflix-data/.ssh/

if [ $? -eq 0 ]; then
    echo "✓ Private key copied"
else
    echo "✗ Failed to copy key"
    exit 1
fi

# Set correct permissions on Pi
echo ""
echo "Step 3: Setting permissions on Pi..."
ssh boatflix@boatflix.local "chmod 600 ~/boatflix-data/.ssh/id_pi_transcode"

if [ $? -eq 0 ]; then
    echo "✓ Permissions set"
else
    echo "✗ Failed to set permissions"
    exit 1
fi

# Test the connection
echo ""
echo "Step 4: Testing connection from Pi to MacBook..."
ssh boatflix@boatflix.local "ssh -i ~/boatflix-data/.ssh/id_pi_transcode -o StrictHostKeyChecking=no -o BatchMode=yes ethan@192.168.50.111 'echo Connection successful'"

if [ $? -eq 0 ]; then
    echo "✓ Connection test successful!"
else
    echo "⚠ Connection test failed - you may need to enable Remote Login on MacBook first"
fi

echo ""
echo "============================================"
echo "✅ SSH key copied to Pi!"
echo ""
echo "Next steps:"
echo "1. Enable Remote Login on this MacBook (System Settings → Sharing)"
echo "2. Add environment variables to Pi's .env file (see .env.macbook-remote)"
echo "3. Restart Boatflix manager on Pi"
echo ""
echo "See QUICKSTART.md for complete setup instructions."
