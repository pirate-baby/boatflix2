"""YouTube sync router - Cookie-based approach (simple!)."""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, case

from config import settings
from database import SessionLocal
from models.db import YouTubeConfig, YouTubePlaylist, YouTubePlaylistItem
from models.youtube_simple import (
    YouTubeConfigResponse,
    YouTubePlaylistCreate,
    YouTubePlaylistUpdate,
    YouTubePlaylistResponse,
    YouTubePlaylistDetailResponse,
    YouTubePlaylistItemResponse,
    YouTubeSyncStatusResponse,
    YouTubeItemStatus,
    DownloadType,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_session():
    """Get database session."""
    return SessionLocal()


async def _create_liked_playlist_if_not_exists() -> str | None:
    """
    Check if Liked Videos playlist exists, create if not.

    Returns:
        Playlist ID if created or already exists, None if creation failed
    """
    # Special URL for YouTube's Liked Videos playlist
    liked_url = "https://www.youtube.com/playlist?list=LL"
    liked_playlist_id = "LL"

    with _get_session() as session:
        # Check if Liked playlist already exists
        existing = session.scalar(
            select(YouTubePlaylist).where(
                (YouTubePlaylist.youtube_playlist_id == liked_playlist_id) |
                (YouTubePlaylist.url == liked_url)
            )
        )

        if existing:
            logger.info(f"Liked Videos playlist already exists: {existing.id}")
            return existing.id

        # Create the Liked Videos playlist
        try:
            playlist = YouTubePlaylist(
                id=str(uuid4()),
                url=liked_url,
                youtube_playlist_id=liked_playlist_id,
                title="Liked Videos",
                description="Your liked YouTube videos (automatically synced)",
                download_type=DownloadType.AUDIO.value,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            session.add(playlist)
            session.commit()
            session.refresh(playlist)

            logger.info(f"Created Liked Videos playlist: {playlist.id}")
            return playlist.id

        except Exception as e:
            logger.error(f"Failed to create Liked Videos playlist: {e}")
            session.rollback()
            return None


# Cookie Management


@router.get("/config", response_model=YouTubeConfigResponse)
async def get_config():
    """Get YouTube configuration status (cookies uploaded, etc)."""
    with _get_session() as session:
        config = session.scalar(select(YouTubeConfig).limit(1))

        if not config:
            return YouTubeConfigResponse(
                cookies_uploaded=False,
                cookies_uploaded_at=None
            )

        return YouTubeConfigResponse(
            cookies_uploaded=config.cookies_uploaded,
            cookies_uploaded_at=config.cookies_uploaded_at
        )


@router.post("/upload-cookies")
async def upload_cookies(file: UploadFile = File(...), background_tasks: BackgroundTasks):
    """
    Upload YouTube cookies.txt file.

    This file should be exported from your browser using an extension.
    """
    # Validate file
    if not file.filename.endswith('.txt'):
        raise HTTPException(status_code=400, detail="File must be a .txt file")

    # Read file content
    try:
        content = await file.read()
        content_str = content.decode('utf-8')

        # Basic validation - check if it looks like a Netscape cookies file
        if '# Netscape HTTP Cookie File' not in content_str and 'youtube.com' not in content_str:
            raise HTTPException(
                status_code=400,
                detail="This doesn't look like a valid YouTube cookies file. Make sure to export cookies for youtube.com"
            )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    # Save cookies to configured location
    cookies_path = Path(settings.YOUTUBE_COOKIES_FILE)
    cookies_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(cookies_path, 'wb') as f:
            f.write(content)

        logger.info(f"Saved YouTube cookies to {cookies_path}")

    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save cookies: {str(e)}")

    # Update config in database
    with _get_session() as session:
        config = session.scalar(select(YouTubeConfig).limit(1))

        if config:
            config.cookies_uploaded = True
            config.cookies_uploaded_at = datetime.now(timezone.utc)
            config.updated_at = datetime.now(timezone.utc)
        else:
            config = YouTubeConfig(
                cookies_uploaded=True,
                cookies_uploaded_at=datetime.now(timezone.utc),
            )
            session.add(config)

        session.commit()

    # Automatically create Liked Videos playlist if it doesn't exist
    try:
        liked_playlist_id = await _create_liked_playlist_if_not_exists()
        if liked_playlist_id:
            logger.info(f"Automatically created Liked Videos playlist: {liked_playlist_id}")
            # Trigger background sync for the Liked playlist
            from services.youtube_sync_simple import sync_playlist_items
            background_tasks.add_task(sync_playlist_items, liked_playlist_id)
    except Exception as e:
        # Don't fail the cookie upload if Liked playlist creation fails
        logger.warning(f"Failed to auto-create Liked Videos playlist: {e}")

    return {"status": "success", "message": "Cookies uploaded successfully"}


@router.delete("/cookies")
async def delete_cookies():
    """Delete uploaded cookies."""
    cookies_path = Path(settings.YOUTUBE_COOKIES_FILE)

    if cookies_path.exists():
        try:
            cookies_path.unlink()
            logger.info("Deleted YouTube cookies file")
        except Exception as e:
            logger.error(f"Failed to delete cookies: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete cookies: {str(e)}")

    # Update config
    with _get_session() as session:
        config = session.scalar(select(YouTubeConfig).limit(1))
        if config:
            config.cookies_uploaded = False
            config.cookies_uploaded_at = None
            config.updated_at = datetime.now(timezone.utc)
            session.commit()

    return {"status": "success", "message": "Cookies deleted"}


# Playlist Management


@router.get("/playlists", response_model=list[YouTubePlaylistResponse])
async def list_playlists():
    """List all manually added playlists."""
    with _get_session() as session:
        playlists = session.scalars(
            select(YouTubePlaylist).order_by(YouTubePlaylist.created_at.desc())
        ).all()

        result = []
        for playlist in playlists:
            # Count items by status
            item_counts = session.execute(
                select(
                    func.count(YouTubePlaylistItem.id).label("total"),
                    func.sum(
                        case(
                            (YouTubePlaylistItem.download_status == YouTubeItemStatus.PENDING.value, 1),
                            else_=0
                        )
                    ).label("pending"),
                    func.sum(
                        case(
                            (YouTubePlaylistItem.download_status == YouTubeItemStatus.COMPLETED.value, 1),
                            else_=0
                        )
                    ).label("completed"),
                    func.sum(
                        case(
                            (YouTubePlaylistItem.download_status == YouTubeItemStatus.FAILED.value, 1),
                            else_=0
                        )
                    ).label("failed"),
                ).where(YouTubePlaylistItem.playlist_id == playlist.id)
            ).one()

            result.append(
                YouTubePlaylistResponse(
                    id=playlist.id,
                    url=playlist.url,
                    youtube_playlist_id=playlist.youtube_playlist_id,
                    title=playlist.title,
                    description=playlist.description,
                    download_type=DownloadType(playlist.download_type),
                    jellyfin_playlist_id=playlist.jellyfin_playlist_id,
                    last_synced_at=playlist.last_synced_at,
                    item_count=item_counts.total or 0,
                    pending_count=item_counts.pending or 0,
                    completed_count=item_counts.completed or 0,
                    failed_count=item_counts.failed or 0,
                    created_at=playlist.created_at,
                    updated_at=playlist.updated_at,
                )
            )

        return result


@router.post("/playlists", response_model=YouTubePlaylistResponse)
async def add_playlist(request: YouTubePlaylistCreate, background_tasks: BackgroundTasks):
    """
    Manually add a YouTube playlist by URL.

    The system will use yt-dlp to extract playlist info and items.
    """
    # Check if cookies are uploaded
    cookies_path = Path(settings.YOUTUBE_COOKIES_FILE)
    if not cookies_path.exists():
        raise HTTPException(
            status_code=400,
            detail="Please upload YouTube cookies first before adding playlists"
        )

    # Import here to avoid circular import
    from services.youtube_extractor import extract_playlist_info

    # Extract playlist info using yt-dlp
    try:
        playlist_info = await extract_playlist_info(request.url)
    except Exception as e:
        logger.error(f"Failed to extract playlist info: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to extract playlist info: {str(e)}. Make sure the URL is valid and your cookies are up to date."
        )

    # Create playlist in database
    with _get_session() as session:
        # Check if playlist already exists
        existing = session.scalar(
            select(YouTubePlaylist).where(
                (YouTubePlaylist.url == request.url) |
                (YouTubePlaylist.youtube_playlist_id == playlist_info.get("playlist_id"))
            )
        )

        if existing:
            raise HTTPException(status_code=400, detail="This playlist has already been added")

        playlist = YouTubePlaylist(
            id=str(uuid4()),
            url=request.url,
            youtube_playlist_id=playlist_info.get("playlist_id"),
            title=playlist_info.get("title", "Unknown Playlist"),
            description=playlist_info.get("description"),
            download_type=request.download_type.value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        session.add(playlist)
        session.commit()
        session.refresh(playlist)

        playlist_id = playlist.id

    # Trigger background extraction of playlist items
    from services.youtube_sync_simple import sync_playlist_items
    background_tasks.add_task(sync_playlist_items, playlist_id)

    return YouTubePlaylistResponse(
        id=playlist_id,
        url=request.url,
        youtube_playlist_id=playlist_info.get("playlist_id"),
        title=playlist_info.get("title", "Unknown Playlist"),
        description=playlist_info.get("description"),
        download_type=request.download_type,
        jellyfin_playlist_id=None,
        last_synced_at=None,
        item_count=0,
        pending_count=0,
        completed_count=0,
        failed_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@router.get("/playlists/{playlist_id}", response_model=YouTubePlaylistDetailResponse)
async def get_playlist_detail(
    playlist_id: str,
    status_filter: str | None = Query(None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Get detailed playlist with items."""
    with _get_session() as session:
        playlist = session.get(YouTubePlaylist, playlist_id)

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Count items
        item_counts = session.execute(
            select(
                func.count(YouTubePlaylistItem.id).label("total"),
                func.sum(
                    case(
                        (YouTubePlaylistItem.download_status == YouTubeItemStatus.PENDING.value, 1),
                        else_=0
                    )
                ).label("pending"),
                func.sum(
                    case(
                        (YouTubePlaylistItem.download_status == YouTubeItemStatus.COMPLETED.value, 1),
                        else_=0
                    )
                ).label("completed"),
                func.sum(
                    case(
                        (YouTubePlaylistItem.download_status == YouTubeItemStatus.FAILED.value, 1),
                        else_=0
                    )
                ).label("failed"),
            ).where(YouTubePlaylistItem.playlist_id == playlist_id)
        ).one()

        playlist_response = YouTubePlaylistResponse(
            id=playlist.id,
            url=playlist.url,
            youtube_playlist_id=playlist.youtube_playlist_id,
            title=playlist.title,
            description=playlist.description,
            download_type=DownloadType(playlist.download_type),
            jellyfin_playlist_id=playlist.jellyfin_playlist_id,
            last_synced_at=playlist.last_synced_at,
            item_count=item_counts.total or 0,
            pending_count=item_counts.pending or 0,
            completed_count=item_counts.completed or 0,
            failed_count=item_counts.failed or 0,
            created_at=playlist.created_at,
            updated_at=playlist.updated_at,
        )

        # Get items
        items_stmt = (
            select(YouTubePlaylistItem)
            .where(YouTubePlaylistItem.playlist_id == playlist_id)
            .order_by(YouTubePlaylistItem.position)
        )

        if status_filter:
            items_stmt = items_stmt.where(
                YouTubePlaylistItem.download_status == status_filter
            )

        items_stmt = items_stmt.limit(limit).offset(offset)
        items = session.scalars(items_stmt).all()

        items_response = [
            YouTubePlaylistItemResponse(
                id=item.id,
                playlist_id=item.playlist_id,
                youtube_video_id=item.youtube_video_id,
                title=item.title,
                artist=item.artist,
                position=item.position,
                download_status=YouTubeItemStatus(item.download_status),
                download_id=item.download_id,
                file_path=item.file_path,
                added_to_playlist_at=item.added_to_playlist_at,
                downloaded_at=item.downloaded_at,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ]

        return YouTubePlaylistDetailResponse(
            playlist=playlist_response,
            items=items_response,
            total_items=item_counts.total or 0,
        )


@router.patch("/playlists/{playlist_id}", response_model=YouTubePlaylistResponse)
async def update_playlist(playlist_id: str, update: YouTubePlaylistUpdate):
    """Update playlist settings (download type)."""
    with _get_session() as session:
        playlist = session.get(YouTubePlaylist, playlist_id)

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        if update.download_type is not None:
            playlist.download_type = update.download_type.value

        playlist.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(playlist)

        # Get counts
        item_counts = session.execute(
            select(
                func.count(YouTubePlaylistItem.id).label("total"),
                func.sum(
                    case(
                        (YouTubePlaylistItem.download_status == YouTubeItemStatus.PENDING.value, 1),
                        else_=0
                    )
                ).label("pending"),
                func.sum(
                    case(
                        (YouTubePlaylistItem.download_status == YouTubeItemStatus.COMPLETED.value, 1),
                        else_=0
                    )
                ).label("completed"),
                func.sum(
                    case(
                        (YouTubePlaylistItem.download_status == YouTubeItemStatus.FAILED.value, 1),
                        else_=0
                    )
                ).label("failed"),
            ).where(YouTubePlaylistItem.playlist_id == playlist_id)
        ).one()

        return YouTubePlaylistResponse(
            id=playlist.id,
            url=playlist.url,
            youtube_playlist_id=playlist.youtube_playlist_id,
            title=playlist.title,
            description=playlist.description,
            download_type=DownloadType(playlist.download_type),
            jellyfin_playlist_id=playlist.jellyfin_playlist_id,
            last_synced_at=playlist.last_synced_at,
            item_count=item_counts.total or 0,
            pending_count=item_counts.pending or 0,
            completed_count=item_counts.completed or 0,
            failed_count=item_counts.failed or 0,
            created_at=playlist.created_at,
            updated_at=playlist.updated_at,
        )


@router.delete("/playlists/{playlist_id}")
async def delete_playlist(playlist_id: str):
    """Delete a playlist."""
    with _get_session() as session:
        playlist = session.get(YouTubePlaylist, playlist_id)

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        session.delete(playlist)
        session.commit()

        return {"status": "deleted", "playlist_id": playlist_id}


@router.post("/playlists/{playlist_id}/sync")
async def sync_playlist(playlist_id: str, background_tasks: BackgroundTasks):
    """Manually trigger sync for a playlist."""
    with _get_session() as session:
        playlist = session.get(YouTubePlaylist, playlist_id)

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

    from services.youtube_sync_simple import sync_playlist_items
    background_tasks.add_task(sync_playlist_items, playlist_id)

    return {"status": "started", "message": f"Sync started for playlist {playlist_id}"}


@router.post("/sync/all")
async def sync_all_playlists(background_tasks: BackgroundTasks):
    """Manually trigger sync for all playlists."""
    from services.youtube_sync_simple import youtube_sync_simple

    if youtube_sync_simple.is_running:
        raise HTTPException(status_code=400, detail="Sync is already running")

    # Check if cookies exist
    cookies_path = Path(settings.YOUTUBE_COOKIES_FILE)
    if not cookies_path.exists():
        raise HTTPException(
            status_code=400,
            detail="YouTube cookies not uploaded. Please upload cookies first."
        )

    background_tasks.add_task(youtube_sync_simple.sync_all_playlists)

    return {"status": "started", "message": "Sync started for all playlists"}


@router.get("/sync/status", response_model=YouTubeSyncStatusResponse)
async def get_sync_status():
    """Get current sync status."""
    # Import to avoid circular dependency
    from services.youtube_sync_simple import youtube_sync_simple

    return YouTubeSyncStatusResponse(
        is_running=youtube_sync_simple.is_running,
        current_playlist_id=youtube_sync_simple.current_playlist_id,
        current_playlist_title=youtube_sync_simple.current_playlist_title,
        progress_message=youtube_sync_simple.progress_message,
    )
