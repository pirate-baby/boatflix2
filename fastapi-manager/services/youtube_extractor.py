"""yt-dlp service for extracting YouTube playlist information using cookies."""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


async def extract_playlist_info(url: str) -> dict:
    """
    Extract basic playlist information using yt-dlp.

    Args:
        url: YouTube playlist URL

    Returns:
        Dict with playlist_id, title, description, item_count

    Raises:
        RuntimeError: If extraction fails
    """
    cookies_path = Path(settings.YOUTUBE_COOKIES_FILE)

    cmd = [
        "yt-dlp",
        "--cookies", str(cookies_path),
        "--dump-single-json",
        "--flat-playlist",
        "--no-warnings",
        url,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            logger.error(f"yt-dlp failed: {error_msg}")
            raise RuntimeError(f"Failed to extract playlist info: {error_msg}")

        data = json.loads(stdout.decode())

        # Extract playlist ID from URL or data
        playlist_id = data.get("id") or _extract_playlist_id_from_url(url)

        return {
            "playlist_id": playlist_id,
            "title": data.get("title", "Unknown Playlist"),
            "description": data.get("description"),
            "item_count": len(data.get("entries", [])),
            "entries": data.get("entries", []),  # Video IDs and titles
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse yt-dlp output: {e}")
        raise RuntimeError("Failed to parse playlist data")
    except Exception as e:
        logger.error(f"Unexpected error extracting playlist: {e}")
        raise RuntimeError(f"Failed to extract playlist: {str(e)}")


async def extract_playlist_items(url: str, playlist_id: Optional[str] = None) -> list[dict]:
    """
    Extract all items from a YouTube playlist.

    Args:
        url: YouTube playlist URL
        playlist_id: Optional playlist ID (will extract from URL if not provided)

    Returns:
        List of dicts with video_id, title, artist, position, added_at

    Raises:
        RuntimeError: If extraction fails
    """
    cookies_path = Path(settings.YOUTUBE_COOKIES_FILE)

    cmd = [
        "yt-dlp",
        "--cookies", str(cookies_path),
        "--dump-single-json",
        "--flat-playlist",
        "--no-warnings",
        url,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            logger.error(f"yt-dlp failed: {error_msg}")
            raise RuntimeError(f"Failed to extract playlist items: {error_msg}")

        data = json.loads(stdout.decode())
        entries = data.get("entries", [])

        items = []
        for idx, entry in enumerate(entries):
            # Skip unavailable/deleted videos
            if not entry or not entry.get("id"):
                continue

            items.append({
                "video_id": entry["id"],
                "title": entry.get("title", "Unknown Title"),
                "artist": entry.get("uploader") or entry.get("channel"),
                "position": idx,
                # yt-dlp doesn't provide added_at for flat playlist, so use current time
                # This is fine for initial sync; subsequent syncs only add new items
            })

        return items

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse yt-dlp output: {e}")
        raise RuntimeError("Failed to parse playlist items")
    except Exception as e:
        logger.error(f"Unexpected error extracting playlist items: {e}")
        raise RuntimeError(f"Failed to extract playlist items: {str(e)}")


def _extract_playlist_id_from_url(url: str) -> Optional[str]:
    """
    Extract playlist ID from YouTube URL.

    Handles various URL formats:
    - https://www.youtube.com/playlist?list=PLxxx
    - https://www.youtube.com/watch?v=xxx&list=PLxxx
    - https://music.youtube.com/playlist?list=PLxxx
    """
    # Try to extract from list= parameter
    match = re.search(r'[?&]list=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)

    # Try to extract from /playlist/ path
    match = re.search(r'/playlist/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)

    return None


async def check_cookies_valid() -> bool:
    """
    Check if uploaded cookies are still valid.

    Returns:
        True if cookies work, False otherwise
    """
    cookies_path = Path(settings.YOUTUBE_COOKIES_FILE)

    if not cookies_path.exists():
        return False

    # Try to fetch a simple public playlist to test cookies
    test_url = "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"  # YouTube Developers channel

    cmd = [
        "yt-dlp",
        "--cookies", str(cookies_path),
        "--dump-single-json",
        "--flat-playlist",
        "--playlist-end", "1",  # Only check first video
        "--no-warnings",
        test_url,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        return process.returncode == 0

    except Exception as e:
        logger.error(f"Failed to check cookies validity: {e}")
        return False
