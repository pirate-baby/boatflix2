"""YouTube playlist sync service - Cookie-based approach."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from config import settings
from database import SessionLocal
from models.db import YouTubePlaylist, YouTubePlaylistItem, MediaType
from models.youtube_simple import YouTubeItemStatus, DownloadType
from models.download import MusicMetadata, MovieMetadata
from services.youtube_extractor import extract_playlist_items
from services.download_queue import download_queue

logger = logging.getLogger(__name__)


class YouTubeSyncSimple:
    """Manages YouTube playlist synchronization using cookies."""

    def __init__(self):
        self.is_running = False
        self.current_playlist_id = None
        self.current_playlist_title = None
        self.progress_message = ""

    def _get_session(self):
        """Get database session."""
        return SessionLocal()

    async def sync_all_playlists(self):
        """Sync all playlists in the database."""
        if self.is_running:
            logger.warning("Sync already running, skipping")
            return

        # Check if cookies exist
        cookies_path = Path(settings.YOUTUBE_COOKIES_FILE)
        if not cookies_path.exists():
            logger.error("YouTube cookies not found, skipping sync")
            return

        self.is_running = True
        self.progress_message = "Starting sync for all playlists"

        try:
            with self._get_session() as session:
                playlists = session.scalars(select(YouTubePlaylist)).all()

                for playlist in playlists:
                    await self._sync_single_playlist(playlist.id)

            self.progress_message = "Sync completed for all playlists"

        except Exception as e:
            logger.error(f"Error syncing playlists: {e}")
            self.progress_message = f"Sync failed: {str(e)}"

        finally:
            self.is_running = False
            self.current_playlist_id = None
            self.current_playlist_title = None

    async def _sync_single_playlist(self, playlist_id: str):
        """Sync a single playlist by ID."""
        with self._get_session() as session:
            playlist = session.get(YouTubePlaylist, playlist_id)

            if not playlist:
                logger.error(f"Playlist {playlist_id} not found")
                return

            self.current_playlist_id = playlist_id
            self.current_playlist_title = playlist.title
            self.progress_message = f"Syncing playlist: {playlist.title}"

            logger.info(f"Syncing playlist: {playlist.title} ({playlist.url})")

            try:
                # Extract current playlist items from YouTube
                logger.info(f"Extracting items for playlist: {playlist.url}")
                youtube_items = await extract_playlist_items(playlist.url, playlist.youtube_playlist_id)
                logger.info(f"Extracted {len(youtube_items)} items from YouTube for playlist: {playlist.title}")

                # Get existing items from database
                existing_items = session.scalars(
                    select(YouTubePlaylistItem).where(
                        YouTubePlaylistItem.playlist_id == playlist_id
                    )
                ).all()
                logger.info(f"Found {len(existing_items)} existing items in database")

                existing_video_ids = {item.youtube_video_id for item in existing_items}

                # Find new items (one-way sync - add only, never remove)
                new_items = [
                    item for item in youtube_items
                    if item["video_id"] not in existing_video_ids
                ]

                if not new_items:
                    logger.info(f"No new items found for playlist: {playlist.title} (YouTube has {len(youtube_items)} items, DB has {len(existing_items)} items)")
                    playlist.last_synced_at = datetime.now(timezone.utc)
                    session.commit()
                    return

                logger.info(f"Found {len(new_items)} new items for playlist: {playlist.title}")

                # Create database records and queue downloads
                for item in new_items:
                    # Create playlist item record
                    playlist_item = YouTubePlaylistItem(
                        id=str(uuid4()),
                        playlist_id=playlist_id,
                        youtube_video_id=item["video_id"],
                        title=item["title"],
                        artist=item.get("artist"),
                        position=item["position"],
                        download_status=YouTubeItemStatus.PENDING.value,
                        added_to_playlist_at=datetime.now(timezone.utc),
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )

                    session.add(playlist_item)
                    session.flush()  # Ensure the record is written

                    # Queue download
                    video_url = f"https://www.youtube.com/watch?v={item['video_id']}"

                    # Determine media type and metadata based on playlist download_type
                    if playlist.download_type == DownloadType.AUDIO.value:
                        media_type = MediaType.MUSIC
                        metadata = MusicMetadata(
                            artist=item.get("artist", "Unknown Artist"),
                            album=playlist.title,  # Use playlist title as album
                            track=item["title"],
                        )
                    else:
                        media_type = MediaType.MOVIE
                        metadata = MovieMetadata(
                            title=item["title"],
                        )

                    # Add to download queue
                    job = download_queue.add_job(
                        url=video_url,
                        media_type=media_type,
                        metadata=metadata,
                    )

                    # Update playlist item with download_id
                    playlist_item.download_id = job.id
                    playlist_item.download_status = YouTubeItemStatus.PENDING.value

                # Update playlist sync timestamp
                playlist.last_synced_at = datetime.now(timezone.utc)
                playlist.updated_at = datetime.now(timezone.utc)

                session.commit()

                logger.info(f"Queued {len(new_items)} downloads for playlist: {playlist.title}")

            except Exception as e:
                logger.error(f"Error syncing playlist {playlist.title}: {e}")
                session.rollback()
                raise


async def sync_playlist_items(playlist_id: str):
    """Sync items for a specific playlist (called from background tasks)."""
    sync = YouTubeSyncSimple()
    sync.is_running = True

    try:
        logger.info(f"Background task: Starting sync for playlist {playlist_id}")
        await sync._sync_single_playlist(playlist_id)
        logger.info(f"Background task: Completed sync for playlist {playlist_id}")
    except Exception as e:
        logger.error(f"Background task: Failed to sync playlist {playlist_id}: {e}", exc_info=True)
        raise
    finally:
        sync.is_running = False
        sync.current_playlist_id = None
        sync.current_playlist_title = None


# Global instance for status tracking
youtube_sync_simple = YouTubeSyncSimple()
