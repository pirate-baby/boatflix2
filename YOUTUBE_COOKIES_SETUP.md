# YouTube Sync - Simple Cookie-Based Setup (No OAuth!)

This method uses browser cookies instead of OAuth - **much simpler** and works great!

## Why This is Better

- ✅ **No Google Cloud account needed**
- ✅ **No OAuth configuration**
- ✅ **No redirect URI issues**
- ✅ **Works offline** (once cookies are exported)
- ✅ **5 minute setup** vs 30 minutes for OAuth

## How It Works

yt-dlp (which you already have installed) can use your browser's YouTube cookies to access your private playlists and liked videos - just like you're logged into YouTube in your browser!

## Setup Steps

### Step 1: Export Cookies from Your Browser

**Option A: Using Browser Extension (Easiest)**

1. Install a cookie export extension:
   - Chrome/Edge: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - Firefox: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

2. Go to [YouTube.com](https://youtube.com) and make sure you're logged in

3. Click the extension icon and export cookies for `youtube.com`

4. Save the file as `youtube_cookies.txt`

**Option B: Using yt-dlp (Manual)**

If you have yt-dlp installed locally:

```bash
# Chrome
yt-dlp --cookies-from-browser chrome --cookies cookies.txt https://www.youtube.com

# Firefox
yt-dlp --cookies-from-browser firefox --cookies cookies.txt https://www.youtube.com

# Safari
yt-dlp --cookies-from-browser safari --cookies cookies.txt https://www.youtube.com
```

### Step 2: Place Cookies File

Copy `youtube_cookies.txt` to your boatflix2 data directory:

```bash
# On your server
cp youtube_cookies.txt ~/boatflix2/manager_data/youtube_cookies.txt
```

Or if using Docker volume:
```bash
docker cp youtube_cookies.txt $(docker-compose ps -q manager):/app/data/youtube_cookies.txt
```

### Step 3: Configure Environment Variable

Add to your `.env` file:

```env
YOUTUBE_COOKIES_FILE=/app/data/youtube_cookies.txt
```

### Step 4: Restart Manager

```bash
docker-compose restart manager
```

### Step 5: Use the YouTube Sync Page

Now when you access `http://boatflix.local:8080/manager/youtube`, you can:

1. **Fetch your playlists** using yt-dlp (no OAuth needed!)
2. **Configure which ones to sync** (audio or video)
3. **Let it automatically download** new items

## How to Get Your Playlist URLs

yt-dlp can extract playlists directly from URLs:

1. **Your Playlists:** `https://www.youtube.com/feed/playlists`
2. **Liked Videos:** `https://www.youtube.com/playlist?list=LL`
3. **Watch Later:** `https://www.youtube.com/playlist?list=WL`
4. **Specific Playlist:** Copy URL from browser

The app will use yt-dlp to:
- Extract all videos from the playlist
- Download them as audio (MP3) or video (MP4)
- Track what's been downloaded
- Sync new items automatically

## Updating Cookies

Cookies expire after a while (usually 6-12 months). When they do:

1. Re-export cookies using the same method
2. Replace the old `youtube_cookies.txt` file
3. Restart the manager container

You'll know cookies expired when downloads start failing with authentication errors.

## Security Note

⚠️ **Keep your cookies file secure!** It contains session tokens that let anyone access YouTube as you. Don't share it or commit it to git.

The cookies file is stored in your Docker volume which is private to your server.

## Troubleshooting

### "Unable to extract playlist"

Your cookies may have expired. Re-export them from your browser.

### "Sign in to confirm you're not a bot"

YouTube is blocking automated access. Try:
1. Log out and back into YouTube in your browser
2. Watch a few videos manually
3. Re-export cookies

### "This video is age-restricted"

Age-restricted videos require you to be logged in (which you are via cookies), but may still fail. This is a YouTube limitation.

## Multiple YouTube Accounts

To sync from multiple accounts:

1. Export cookies while logged into Account 1 → save as `youtube_cookies_account1.txt`
2. Export cookies while logged into Account 2 → save as `youtube_cookies_account2.txt`
3. Configure each in the UI separately

---

**This is SO much easier than OAuth!** No Google Cloud Console, no redirect URIs, no API quotas to worry about.
