"""YouTube sync service with one-way add-only logic."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from config import settings
from database import SessionLocal
from models.db import YouTubeUser, YouTubePlaylist, YouTubePlaylistItem, YouTubeQuota
from models.download import MediaType, MusicMetadata
from models.youtube import DownloadType, YouTubeItemStatus
from services.youtube_api import (
    youtube_api,
    YouTubeAPIError,
    YouTubeQuotaExceeded,
)
from services.download_queue import DownloadQueueManager

logger = logging.getLogger(__name__)


class YouTubeSyncService:
    """Service for syncing YouTube playlists to local downloads."""

    def __init__(self):
        """Initialize sync service."""
        self.download_queue = DownloadQueueManager()
        self.is_running = False
        self.current_user_id: Optional[str] = None
        self.current_playlist_id: Optional[str] = None
        self.current_playlist_title: Optional[str] = None
        self.progress_message: Optional[str] = None

    def _get_session(self) -> Session:
        """Get a new database session."""
        return SessionLocal()

    async def check_quota(self, session: Session) -> bool:
        """
        Check if we can make API calls (quota not exceeded).

        Returns:
            True if we can make API calls, False if quota exceeded
        """
        # Get today's quota record
        today = datetime.now(timezone.utc).date()
        quota_stmt = select(YouTubeQuota).where(
            YouTubeQuota.reset_date >= datetime.now(timezone.utc)
        ).order_by(YouTubeQuota.created_at.desc()).limit(1)

        quota = session.scalar(quota_stmt)

        if not quota:
            # Create new quota record for today
            quota = YouTubeQuota(
                units_used=0,
                reset_date=datetime.combine(
                    today + timedelta(days=1), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            session.add(quota)
            session.commit()
            return True

        # Check if quota exceeded until timestamp has passed
        if quota.quota_exceeded_until:
            if datetime.now(timezone.utc) < quota.quota_exceeded_until:
                logger.warning(
                    f"Quota exceeded until {quota.quota_exceeded_until}, skipping sync"
                )
                return False
            else:
                # Reset exceeded flag
                quota.quota_exceeded_until = None
                session.commit()

        return True

    async def increment_quota(self, session: Session, units: int):
        """
        Increment quota usage and check if we've exceeded the limit.

        Args:
            session: Database session
            units: Number of quota units to add
        """
        today = datetime.now(timezone.utc).date()
        quota_stmt = select(YouTubeQuota).where(
            YouTubeQuota.reset_date >= datetime.now(timezone.utc)
        ).order_by(YouTubeQuota.created_at.desc()).limit(1)

        quota = session.scalar(quota_stmt)

        if not quota:
            quota = YouTubeQuota(
                units_used=units,
                reset_date=datetime.combine(
                    today + timedelta(days=1), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            session.add(quota)
        else:
            quota.units_used += units

        # Check if we've exceeded the limit
        if quota.units_used >= 10000:  # Daily limit
            quota.quota_exceeded_until = datetime.combine(
                today + timedelta(days=1), datetime.min.time()
            ).replace(tzinfo=timezone.utc)
            logger.warning(
                f"YouTube API quota exceeded: {quota.units_used} units used"
            )

        session.commit()

    async def sync_user_playlists(
        self, session: Session, user: YouTubeUser
    ) -> list[YouTubePlaylist]:
        """
        Fetch and sync all playlists for a user from YouTube.

        Args:
            session: Database session
            user: YouTubeUser to sync

        Returns:
            List of synced YouTubePlaylist objects
        """
        logger.info(f"Syncing playlists for user {user.email}")

        # Get credentials
        credentials = youtube_api.get_credentials(
            user.access_token, user.refresh_token, user.token_expiry
        )

        # Refresh token if expired
        if credentials.expired:
            logger.info(f"Refreshing access token for {user.email}")
            (
                user.access_token,
                user.refresh_token,
                user.token_expiry,
            ) = await youtube_api.refresh_access_token(credentials)
            session.commit()

            # Re-get credentials with new token
            credentials = youtube_api.get_credentials(
                user.access_token, user.refresh_token, user.token_expiry
            )

        synced_playlists = []

        # Fetch user's playlists with pagination
        page_token = None
        while True:
            try:
                result = await youtube_api.get_user_playlists(credentials, page_token)
                await self.increment_quota(session, 1)  # playlists.list = 1 unit

                for yt_playlist in result["playlists"]:
                    playlist = await self._upsert_playlist(
                        session, user, yt_playlist, is_liked=False
                    )
                    synced_playlists.append(playlist)

                page_token = result.get("next_page_token")
                if not page_token:
                    break

            except YouTubeQuotaExceeded:
                logger.error("YouTube API quota exceeded during playlist sync")
                raise

        # Fetch liked videos playlist
        try:
            liked_playlist_id = await youtube_api.get_liked_videos_playlist_id(credentials)
            await self.increment_quota(session, 1)  # channels.list = 1 unit

            # Fetch playlist details
            result = await youtube_api.get_user_playlists(credentials)
            liked_playlist_data = {
                "id": liked_playlist_id,
                "title": "Liked Videos",
                "description": "YouTube liked videos",
                "item_count": 0,  # Will be updated during item sync
            }

            playlist = await self._upsert_playlist(
                session, user, liked_playlist_data, is_liked=True
            )
            synced_playlists.append(playlist)

        except YouTubeAPIError as e:
            logger.error(f"Failed to fetch liked videos playlist: {e}")

        logger.info(f"Synced {len(synced_playlists)} playlists for {user.email}")
        return synced_playlists

    async def _upsert_playlist(
        self,
        session: Session,
        user: YouTubeUser,
        yt_playlist: dict,
        is_liked: bool = False,
    ) -> YouTubePlaylist:
        """
        Create or update a playlist in the database.

        Args:
            session: Database session
            user: YouTubeUser owner
            yt_playlist: Playlist data from YouTube API
            is_liked: Whether this is the liked videos playlist

        Returns:
            YouTubePlaylist object
        """
        # Check if playlist exists
        stmt = select(YouTubePlaylist).where(
            YouTubePlaylist.user_id == user.id,
            YouTubePlaylist.youtube_playlist_id == yt_playlist["id"],
        )
        playlist = session.scalar(stmt)

        if playlist:
            # Update existing playlist
            playlist.title = yt_playlist["title"]
            playlist.description = yt_playlist.get("description")
            playlist.is_liked_songs = is_liked
            playlist.updated_at = datetime.now(timezone.utc)
        else:
            # Create new playlist
            playlist = YouTubePlaylist(
                id=str(uuid4()),
                user_id=user.id,
                youtube_playlist_id=yt_playlist["id"],
                title=yt_playlist["title"],
                description=yt_playlist.get("description"),
                is_liked_songs=is_liked,
                download_type=DownloadType.AUDIO.value,  # Default to audio
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(playlist)

        session.commit()
        return playlist

    async def sync_playlist_items(
        self, session: Session, user: YouTubeUser, playlist: YouTubePlaylist
    ):
        """
        Sync items for a specific playlist (one-way add-only).

        Args:
            session: Database session
            user: YouTubeUser owner
            playlist: YouTubePlaylist to sync
        """
        logger.info(f"Syncing items for playlist '{playlist.title}'")
        self.current_playlist_id = playlist.id
        self.current_playlist_title = playlist.title

        # Get credentials
        credentials = youtube_api.get_credentials(
            user.access_token, user.refresh_token, user.token_expiry
        )

        # Refresh token if expired
        if credentials.expired:
            logger.info(f"Refreshing access token for {user.email}")
            (
                user.access_token,
                user.refresh_token,
                user.token_expiry,
            ) = await youtube_api.refresh_access_token(credentials)
            session.commit()

            credentials = youtube_api.get_credentials(
                user.access_token, user.refresh_token, user.token_expiry
            )

        # Fetch playlist items with pagination
        page_token = None
        new_items_count = 0

        while True:
            try:
                result = await youtube_api.get_playlist_items(
                    credentials, playlist.youtube_playlist_id, page_token
                )
                await self.increment_quota(session, 1)  # playlistItems.list = 1 unit

                for yt_item in result["items"]:
                    was_new = await self._upsert_playlist_item(
                        session, playlist, yt_item
                    )
                    if was_new:
                        new_items_count += 1

                page_token = result.get("next_page_token")
                if not page_token:
                    break

            except YouTubeQuotaExceeded:
                logger.error("YouTube API quota exceeded during item sync")
                raise

        # Update last synced timestamp
        playlist.last_synced_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(
            f"Synced {new_items_count} new items for playlist '{playlist.title}'"
        )

        # Queue pending downloads
        await self._queue_pending_downloads(session, playlist)

    async def _upsert_playlist_item(
        self, session: Session, playlist: YouTubePlaylist, yt_item: dict
    ) -> bool:
        """
        Create or update a playlist item (one-way add-only).

        Args:
            session: Database session
            playlist: YouTubePlaylist owner
            yt_item: Item data from YouTube API

        Returns:
            True if new item was created, False if it already existed
        """
        # Check if item exists
        stmt = select(YouTubePlaylistItem).where(
            YouTubePlaylistItem.playlist_id == playlist.id,
            YouTubePlaylistItem.youtube_video_id == yt_item["video_id"],
        )
        item = session.scalar(stmt)

        if item:
            # Item already exists - update position only
            item.position = yt_item["position"]
            item.updated_at = datetime.now(timezone.utc)
            session.commit()
            return False

        # Create new item
        item = YouTubePlaylistItem(
            id=str(uuid4()),
            playlist_id=playlist.id,
            youtube_video_id=yt_item["video_id"],
            title=yt_item["title"],
            artist=yt_item.get("artist"),
            position=yt_item["position"],
            download_status=YouTubeItemStatus.PENDING.value,
            added_to_playlist_at=yt_item["added_at"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(item)
        session.commit()

        logger.debug(f"Added new item: {item.title}")
        return True

    async def _queue_pending_downloads(
        self, session: Session, playlist: YouTubePlaylist
    ):
        """
        Queue downloads for all pending items in a playlist.

        Args:
            session: Database session
            playlist: YouTubePlaylist to process
        """
        # Get all pending items
        stmt = (
            select(YouTubePlaylistItem)
            .where(
                YouTubePlaylistItem.playlist_id == playlist.id,
                YouTubePlaylistItem.download_status == YouTubeItemStatus.PENDING.value,
            )
            .order_by(YouTubePlaylistItem.position)
        )

        pending_items = session.scalars(stmt).all()

        logger.info(f"Queueing {len(pending_items)} pending downloads")

        for item in pending_items:
            try:
                # Construct YouTube URL
                video_url = f"https://www.youtube.com/watch?v={item.youtube_video_id}"

                # Create metadata
                metadata = MusicMetadata(
                    artist=item.artist or "Unknown Artist",
                    track=item.title,
                    album=playlist.title if not playlist.is_liked_songs else None,
                )

                # Add to download queue (pass session to avoid nested session lock)
                job = self.download_queue.add_job(
                    url=video_url,
                    media_type=MediaType.MUSIC,
                    metadata=metadata,
                    session=session,
                )

                # Update item with download reference
                item.download_id = job.id
                item.download_status = YouTubeItemStatus.DOWNLOADING.value
                item.updated_at = datetime.now(timezone.utc)
                session.commit()

                logger.debug(f"Queued download for: {item.title}")

            except Exception as e:
                logger.error(f"Failed to queue download for {item.title}: {e}")
                item.download_status = YouTubeItemStatus.FAILED.value
                session.commit()

    async def sync_all(self):
        """Sync all users and their playlists."""
        if self.is_running:
            logger.warning("Sync already running, skipping")
            return

        self.is_running = True
        self.progress_message = "Starting sync..."

        try:
            with self._get_session() as session:
                # Check quota first
                if not await self.check_quota(session):
                    logger.warning("Quota exceeded, skipping sync")
                    self.progress_message = "Quota exceeded, sync skipped"
                    return

                # Get all users
                stmt = select(YouTubeUser)
                users = session.scalars(stmt).all()

                logger.info(f"Syncing {len(users)} YouTube users")

                for user in users:
                    self.current_user_id = user.id
                    self.progress_message = f"Syncing user {user.email}"

                    try:
                        # Sync user's playlists
                        playlists = await self.sync_user_playlists(session, user)

                        # Sync items for each playlist
                        for playlist in playlists:
                            await self.sync_playlist_items(session, user, playlist)

                    except YouTubeQuotaExceeded:
                        logger.error("Quota exceeded, stopping sync")
                        break
                    except Exception as e:
                        logger.error(f"Failed to sync user {user.email}: {e}")
                        continue

                self.progress_message = "Sync completed"
                logger.info("YouTube sync completed")

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            self.progress_message = f"Sync failed: {str(e)}"
            raise
        finally:
            self.is_running = False
            self.current_user_id = None
            self.current_playlist_id = None
            self.current_playlist_title = None

    async def sync_playlist(self, playlist_id: str):
        """
        Sync a specific playlist.

        Args:
            playlist_id: ID of playlist to sync
        """
        with self._get_session() as session:
            # Check quota first
            if not await self.check_quota(session):
                raise YouTubeAPIError("Quota exceeded, cannot sync")

            # Get playlist with user
            stmt = (
                select(YouTubePlaylist)
                .options(joinedload(YouTubePlaylist.user))
                .where(YouTubePlaylist.id == playlist_id)
            )
            playlist = session.scalar(stmt)

            if not playlist:
                raise ValueError(f"Playlist {playlist_id} not found")

            await self.sync_playlist_items(session, playlist.user, playlist)


# Global instance
youtube_sync = YouTubeSyncService()
