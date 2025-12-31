# YouTube / YouTube Music Sync Setup Guide

This guide will help you set up automatic syncing of your YouTube and YouTube Music playlists to your Jellyfin media server.

## Features

- **One-way sync**: Songs/videos are added automatically but never removed from Jellyfin
- **Multiple accounts**: Support for multiple YouTube users with separate playlists
- **Audio or Video**: Choose to download playlists as audio-only (MP3) or video files
- **Liked Songs**: Automatically includes your "Liked Videos" playlist
- **Automatic scheduling**: Syncs every 6 hours by default (configurable)
- **API Quota tracking**: Monitors YouTube API usage and pauses when limits are reached

## Prerequisites

- A Google Cloud account (free)
- YouTube or YouTube Music account(s) you want to sync from
- Boatflix2 running with the manager service

## Step 1: Create Google Cloud Project and OAuth Credentials

1. **Go to Google Cloud Console**
   - Visit [https://console.cloud.google.com](https://console.cloud.google.com)
   - Sign in with your Google account

2. **Create a new project** (or select existing)
   - Click the project dropdown at the top
   - Click "New Project"
   - Name it something like "Boatflix YouTube Sync"
   - Click "Create"

3. **Enable YouTube Data API v3**
   - In your project, go to "APIs & Services" > "Library"
   - Search for "YouTube Data API v3"
   - Click on it and press "Enable"

4. **Configure OAuth Consent Screen**
   - Go to "APIs & Services" > "OAuth consent screen"
   - Select "External" as the user type
   - Click "Create"
   - Fill in required fields:
     - App name: "Boatflix YouTube Sync"
     - User support email: your email
     - Developer contact: your email
   - Click "Save and Continue"
   - Skip "Scopes" page (click "Save and Continue")
   - Add yourself as a test user (click "Add Users" and enter your email)
   - Click "Save and Continue"

5. **Create OAuth 2.0 Credentials**
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Application type: "Web application"
   - Name: "Boatflix Manager"
   - Under "Authorized redirect URIs", add:
     ```
     http://manager.localhost/api/youtube/auth/callback
     ```
     (or your custom domain if you've configured one)
   - Click "Create"
   - **IMPORTANT**: Copy your Client ID and Client Secret - you'll need these next!

## Step 2: Generate Encryption Key

The encryption key is used to securely store OAuth tokens in the database.

Run this command to generate a key:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Or use this Docker command if you don't have Python locally:

```bash
docker run --rm python:3.11-slim python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Save the output - you'll need it in the next step.

## Step 3: Configure Environment Variables

Add the following to your `.env` file (or update your docker-compose environment):

```env
# YouTube sync configuration
YOUTUBE_SYNC_ENABLED=true
YOUTUBE_SYNC_CRON=0 */6 * * *
YOUTUBE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=your-client-secret-here
YOUTUBE_REDIRECT_URI=http://manager.localhost/api/youtube/auth/callback
YOUTUBE_ENCRYPTION_KEY=your-generated-encryption-key-here
```

**Replace**:
- `your-client-id-here` with your OAuth Client ID from Step 1
- `your-client-secret-here` with your OAuth Client Secret from Step 1
- `your-generated-encryption-key-here` with the key from Step 2

**Optional**: Adjust `YOUTUBE_REDIRECT_URI` if using a custom domain.

## Step 4: Restart Services

Restart the manager container to load the new configuration:

```bash
docker-compose restart manager
```

Or if running with Docker stack:

```bash
docker service update --force boatflix_manager
```

## Step 5: Connect Your YouTube Account

1. **Access the YouTube Sync page**
   - Navigate to your Boatflix Manager: `http://manager.localhost`
   - Click "YouTube" in the top navigation

2. **Add your YouTube account**
   - Click "Add YouTube Account"
   - You'll be redirected to Google's OAuth consent page
   - Sign in with the YouTube/Google account you want to sync
   - Grant permissions:
     - View your YouTube account
     - View your YouTube playlists
   - Click "Allow"

3. **You'll be redirected back** to the YouTube sync page
   - Your account should now appear in the "Connected YouTube Accounts" section
   - Your playlists will automatically start syncing

## Step 6: Configure Playlists

For each playlist, you can:

1. **Choose download type**:
   - **Audio** (default): Downloads as MP3 files for music
   - **Video**: Downloads as MP4 video files
   - Click "Switch" to toggle between types

2. **Manually trigger sync**:
   - Click "Sync" on any playlist to fetch new items immediately
   - Or click "Sync All Playlists" to sync everything

3. **View playlist details**:
   - Click on a playlist title to see all items
   - Track download status for each song/video
   - Filter by status (pending, downloading, completed, failed)

## How It Works

### Sync Process

1. **Every 6 hours** (or your configured schedule):
   - Fetches your playlists from YouTube API
   - Compares with local database
   - Adds any new songs/videos to download queue
   - **Never removes** items (one-way sync only)

2. **Downloads**:
   - Queued items are downloaded using yt-dlp
   - Audio playlists: Extracted to MP3 format
   - Video playlists: Downloaded as MP4
   - Files are saved to `/mnt/media/Downloads`

3. **Manual Organization**:
   - You manually move files from Downloads to correct folders
   - Use the existing "Organize" page in Manager
   - This gives you control over artist/album structure

### API Quota Management

- YouTube API has a daily quota of **10,000 units**
- Typical usage:
  - List playlists: ~1 unit per user
  - Fetch playlist items: ~1 unit per 50 songs
  - Example: 5 users with 10 playlists each (200 items avg) = ~150 units
- The system tracks usage and automatically pauses if quota is exceeded
- Quota resets at midnight Pacific Time

You can view current quota usage on the YouTube sync page.

## Troubleshooting

### "YouTube OAuth credentials not configured"

Make sure you've set `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` in your `.env` file and restarted the manager service.

### "Failed to connect YouTube account"

1. Check that your redirect URI matches exactly:
   - In Google Cloud Console OAuth settings
   - In your `YOUTUBE_REDIRECT_URI` environment variable
2. Make sure you added yourself as a test user in OAuth consent screen
3. Check Docker logs: `docker-compose logs manager`

### "Quota exceeded"

The YouTube API has daily limits. If exceeded:
- Sync will automatically pause until midnight PT
- You can still browse playlists and view status
- Consider reducing sync frequency if this happens often

### Downloads failing

1. Check yt-dlp is working: `docker exec -it manager yt-dlp --version`
2. Verify the video is available and not region-locked
3. Check manager logs for errors: `docker-compose logs manager`
4. Try manually downloading the failing video URL to debug

### Missing playlists

- Only playlists you created appear automatically
- "Liked Videos" is included as a special playlist
- Subscribed/shared playlists may not appear

## Advanced Configuration

### Change Sync Schedule

Edit `YOUTUBE_SYNC_CRON` in `.env`:

```env
# Sync every 12 hours
YOUTUBE_SYNC_CRON=0 */12 * * *

# Sync daily at 3 AM
YOUTUBE_SYNC_CRON=0 3 * * *

# Sync every 2 hours
YOUTUBE_SYNC_CRON=0 */2 * * *
```

Format: `minute hour day month day_of_week`

### Disable Automatic Sync

```env
YOUTUBE_SYNC_ENABLED=false
```

You can still trigger manual syncs from the web UI.

### Using Custom Domain

If you're using a custom domain instead of `manager.localhost`:

1. Update redirect URI in Google Cloud Console OAuth settings
2. Update `YOUTUBE_REDIRECT_URI` in `.env`:
   ```env
   YOUTUBE_REDIRECT_URI=https://your-domain.com/api/youtube/auth/callback
   ```

### Multiple Users

You can connect multiple YouTube/Google accounts:

1. Click "Add YouTube Account" again
2. Sign in with a different account
3. Each account's playlists are tracked separately
4. All playlists from all accounts sync together

## Data Storage

- **Database**: `/app/data/media_manager.db` (SQLite)
- **OAuth tokens**: Encrypted in database using `YOUTUBE_ENCRYPTION_KEY`
- **Downloaded files**: `/mnt/media/Downloads/` (then manually organized)

## Privacy & Security

- OAuth tokens are encrypted at rest
- Only you can access your YouTube data
- API calls are made server-side (your IP)
- Tokens can be revoked at: https://myaccount.google.com/permissions

## Support

For issues or questions:
- Check Docker logs: `docker-compose logs manager`
- Review API quota usage on YouTube sync page
- File an issue on GitHub with logs and error messages

---

**Tip**: Start with one small playlist to test the setup before syncing your entire library!
