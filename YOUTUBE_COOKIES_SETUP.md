# Diagnostic Script - Run on Pi to Check Remote Transcode Setup

```bash
#!/bin/bash
echo "=== Remote Transcode Diagnostic ==="
echo ""

echo "1. Environment Variables (from host):"
echo "   REMOTE_TRANSCODE_ENABLED=$REMOTE_TRANSCODE_ENABLED"
echo "   REMOTE_TRANSCODE_HOST=$REMOTE_TRANSCODE_HOST"
echo "   REMOTE_TRANSCODE_USER=$REMOTE_TRANSCODE_USER"
echo "   REMOTE_TRANSCODE_SSH_KEY=$REMOTE_TRANSCODE_SSH_KEY"
echo ""

echo "2. Docker container environment:"
docker exec boatflix2-manager-1 env | grep REMOTE_TRANSCODE || echo "   No REMOTE_TRANSCODE vars found"
echo ""

echo "3. Config API response:"
curl -s http://localhost:8000/api/transcode/config | python3 -m json.tool | grep -A2 remote || echo "   No remote config found"
echo ""

echo "4. Remote check endpoint:"
curl -s http://localhost:8000/api/transcode/remote/check
echo ""

echo "5. SSH key file:"
docker exec boatflix2-manager-1 ls -la /app/data/.ssh/id_pi_transcode 2>&1
echo ""

echo "6. Python import test:"
docker exec boatflix2-manager-1 python3 -c "from services import remote_transcode; print('✓ remote_transcode module imported successfully')" 2>&1
echo ""

echo "=== End Diagnostic ==="
```

Run this on your Pi to see what's happening.
