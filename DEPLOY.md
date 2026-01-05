# Auto-Deploy Setup

This setup enables automatic deployment on your Raspberry Pi. Every 2 minutes, the system checks for changes on the main branch and automatically redeploys affected services.

## How It Works

1. **deploy.sh** - Smart deployment script that:
   - Fetches and pulls from git main branch
   - Detects which files changed
   - Rebuilds only impacted containers
   - Restarts services intelligently (full restart for compose changes, selective for service changes)
   - Logs all activity to `deploy.log`

2. **systemd timer** - Runs the deploy script every 2 minutes

3. **Smart rebuild logic**:
   - `docker-compose.yml` or `.env` changes → full rebuild
   - `fastapi-manager/` changes → rebuild manager service only
   - `qbittorrentvpn/` changes → rebuild qbittorrentvpn service only
   - `nginx/` changes → restart nginx only
   - `configs/` changes → full restart

## Installation on Raspberry Pi

1. **Make the deploy script executable:**
   ```bash
   chmod +x /home/pi/boatflix2/deploy.sh
   ```

2. **Update paths in systemd files if needed:**

   If your boatflix2 directory is NOT at `/home/pi/boatflix2`, edit the service file:
   ```bash
   nano /home/pi/boatflix2/boatflix-deploy.service
   ```

   Update `WorkingDirectory` and `ExecStart` to match your actual path.

3. **Copy systemd files to system directory:**
   ```bash
   sudo cp /home/pi/boatflix2/boatflix-deploy.service /etc/systemd/system/
   sudo cp /home/pi/boatflix2/boatflix-deploy.timer /etc/systemd/system/
   ```

4. **Reload systemd and enable the timer:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable boatflix-deploy.timer
   sudo systemctl start boatflix-deploy.timer
   ```

5. **Verify it's running:**
   ```bash
   # Check timer status
   sudo systemctl status boatflix-deploy.timer

   # List all timers to see when next run is
   systemctl list-timers boatflix-deploy.timer
   ```

## Usage

Once installed, the system runs automatically. Your workflow becomes:

1. Make changes on MacBook
2. Commit and push to main on GitHub
3. Wait up to 2 minutes
4. Changes are automatically deployed on the Pi

## Monitoring

- **View deploy logs:**
  ```bash
  tail -f /home/pi/boatflix2/deploy.log
  ```

- **Check timer status:**
  ```bash
  sudo systemctl status boatflix-deploy.timer
  ```

- **Check last service run:**
  ```bash
  sudo systemctl status boatflix-deploy.service
  ```

- **See upcoming runs:**
  ```bash
  systemctl list-timers boatflix-deploy.timer
  ```

## Manual Deployment

You can still trigger a deploy manually:

```bash
cd /home/pi/boatflix2
./deploy.sh
```

## Adjusting the Interval

To change how often it checks (default is every 2 minutes):

1. Edit the timer:
   ```bash
   sudo nano /etc/systemd/system/boatflix-deploy.timer
   ```

2. Change `OnUnitActiveSec=2min` to your preferred interval (e.g., `5min`, `10min`, `1h`)

3. Reload systemd:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart boatflix-deploy.timer
   ```

## Troubleshooting

- **Deploy not running:**
  Check timer status: `sudo systemctl status boatflix-deploy.timer`

- **Permission errors:**
  Ensure the pi user can run docker commands: `sudo usermod -aG docker pi`
  Then log out and back in.

- **Git pull fails:**
  Make sure the Pi has git credentials configured or uses SSH keys for GitHub

- **Lock file stuck:**
  If deploy.sh crashes, remove: `rm /tmp/boatflix-deploy.lock`

## Disabling Auto-Deploy

To stop auto-deployment:

```bash
sudo systemctl stop boatflix-deploy.timer
sudo systemctl disable boatflix-deploy.timer
```

To re-enable:

```bash
sudo systemctl enable boatflix-deploy.timer
sudo systemctl start boatflix-deploy.timer
```
