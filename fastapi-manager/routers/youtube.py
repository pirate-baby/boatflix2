"""YouTube sync router with OAuth2 and playlist management endpoints."""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from database import SessionLocal
from models.db import (
    YouTubeUser,
    YouTubePlaylist,
    YouTubePlaylistItem,
    YouTubeQuota,
)
from models.youtube import (
    YouTubeAuthStartResponse,
    YouTubeUserResponse,
    YouTubePlaylistUpdate,
    YouTubePlaylistResponse,
    YouTubePlaylistDetailResponse,
    YouTubePlaylistItemResponse,
    YouTubeAllPlaylistsResponse,
    YouTubePlaylistsGroupedResponse,
    YouTubeSyncStatusResponse,
    YouTubeQuotaResponse,
    YouTubeItemStatus,
)
from services.youtube_api import youtube_api, YouTubeAPIError
from services.youtube_sync import youtube_sync

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_session():
    """Get database session."""
    return SessionLocal()


# OAuth Authentication


@router.get("/auth/start", response_model=YouTubeAuthStartResponse)
async def start_oauth():
    """
    Start OAuth2 flow to add a new YouTube user.

    Returns authorization URL to redirect user to.
    """
    try:
        auth_url, state = youtube_api.get_authorization_url()
        return YouTubeAuthStartResponse(auth_url=auth_url, state=state)
    except YouTubeAPIError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/callback")
async def oauth_callback(code: str, state: str):
    """
    Handle OAuth2 callback and create YouTube user.

    This endpoint is called by Google after user authorizes.
    """
    try:
        # Exchange code for tokens
        user_data = await youtube_api.exchange_code_for_tokens(code, state)

        # Encrypt tokens
        encrypted_access = youtube_api.encrypt_token(user_data["access_token"])
        encrypted_refresh = youtube_api.encrypt_token(user_data["refresh_token"])

        # Create or update user in database
        with _get_session() as session:
            # Check if user already exists
            stmt = select(YouTubeUser).where(
                YouTubeUser.email == user_data["email"]
            )
            user = session.scalar(stmt)

            if user:
                # Update existing user
                user.display_name = user_data["display_name"]
                user.channel_id = user_data["channel_id"]
                user.access_token = encrypted_access
                user.refresh_token = encrypted_refresh
                user.token_expiry = user_data["token_expiry"]
                user.updated_at = datetime.now(timezone.utc)
            else:
                # Create new user
                user = YouTubeUser(
                    id=str(uuid4()),
                    email=user_data["email"],
                    display_name=user_data["display_name"],
                    channel_id=user_data["channel_id"],
                    access_token=encrypted_access,
                    refresh_token=encrypted_refresh,
                    token_expiry=user_data["token_expiry"],
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(user)

            session.commit()
            user_id = user.id

        logger.info(f"Added YouTube user: {user_data['email']}")

        # Redirect to YouTube management page
        return {
            "message": "YouTube account connected successfully",
            "user_id": user_id,
            "redirect": "/manager/youtube",
        }

    except YouTubeAPIError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to connect YouTube account")


# User Management


@router.get("/users", response_model=list[YouTubeUserResponse])
async def list_users():
    """List all connected YouTube users."""
    with _get_session() as session:
        stmt = select(YouTubeUser).order_by(YouTubeUser.created_at.desc())
        users = session.scalars(stmt).all()

        result = []
        for user in users:
            # Count playlists
            playlist_count = session.scalar(
                select(func.count(YouTubePlaylist.id)).where(
                    YouTubePlaylist.user_id == user.id
                )
            )

            result.append(
                YouTubeUserResponse(
                    id=user.id,
                    email=user.email,
                    display_name=user.display_name,
                    channel_id=user.channel_id,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                    playlist_count=playlist_count or 0,
                )
            )

        return result


@router.delete("/users/{user_id}")
async def delete_user(user_id: str):
    """Remove a YouTube user and all their playlists."""
    with _get_session() as session:
        user = session.get(YouTubeUser, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        email = user.email
        session.delete(user)
        session.commit()

        logger.info(f"Deleted YouTube user: {email}")
        return {"status": "deleted", "user_id": user_id}


# Playlist Management


@router.get("/playlists", response_model=YouTubeAllPlaylistsResponse)
async def list_all_playlists():
    """List all playlists grouped by user."""
    with _get_session() as session:
        # Get all users with their playlists
        stmt = (
            select(YouTubeUser)
            .options(joinedload(YouTubeUser.playlists))
            .order_by(YouTubeUser.display_name)
        )
        users = session.scalars(stmt).unique().all()

        user_groups = []
        total_playlists = 0

        for user in users:
            playlists = []

            for playlist in user.playlists:
                # Count items by status
                item_counts = session.execute(
                    select(
                        func.count(YouTubePlaylistItem.id).label("total"),
                        func.sum(
                            func.case(
                                (YouTubePlaylistItem.download_status == YouTubeItemStatus.PENDING.value, 1),
                                else_=0
                            )
                        ).label("pending"),
                        func.sum(
                            func.case(
                                (YouTubePlaylistItem.download_status == YouTubeItemStatus.COMPLETED.value, 1),
                                else_=0
                            )
                        ).label("completed"),
                        func.sum(
                            func.case(
                                (YouTubePlaylistItem.download_status == YouTubeItemStatus.FAILED.value, 1),
                                else_=0
                            )
                        ).label("failed"),
                    ).where(YouTubePlaylistItem.playlist_id == playlist.id)
                ).one()

                playlists.append(
                    YouTubePlaylistResponse(
                        id=playlist.id,
                        user_id=user.id,
                        user_email=user.email,
                        user_display_name=user.display_name,
                        youtube_playlist_id=playlist.youtube_playlist_id,
                        title=playlist.title,
                        description=playlist.description,
                        download_type=playlist.download_type,
                        is_liked_songs=playlist.is_liked_songs,
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

            if playlists:
                user_groups.append(
                    YouTubePlaylistsGroupedResponse(
                        user_id=user.id,
                        user_email=user.email,
                        user_display_name=user.display_name,
                        playlists=playlists,
                    )
                )
                total_playlists += len(playlists)

        return YouTubeAllPlaylistsResponse(
            users=user_groups,
            total_playlists=total_playlists,
        )


@router.get("/playlists/{playlist_id}", response_model=YouTubePlaylistDetailResponse)
async def get_playlist_detail(
    playlist_id: str,
    status_filter: str | None = Query(None, description="Filter by status: pending, downloading, completed, failed"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Get detailed playlist information with items."""
    with _get_session() as session:
        # Get playlist with user
        stmt = (
            select(YouTubePlaylist)
            .options(joinedload(YouTubePlaylist.user))
            .where(YouTubePlaylist.id == playlist_id)
        )
        playlist = session.scalar(stmt)

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Count items by status
        item_counts = session.execute(
            select(
                func.count(YouTubePlaylistItem.id).label("total"),
                func.sum(
                    func.case(
                        (YouTubePlaylistItem.download_status == YouTubeItemStatus.PENDING.value, 1),
                        else_=0
                    )
                ).label("pending"),
                func.sum(
                    func.case(
                        (YouTubePlaylistItem.download_status == YouTubeItemStatus.COMPLETED.value, 1),
                        else_=0
                    )
                ).label("completed"),
                func.sum(
                    func.case(
                        (YouTubePlaylistItem.download_status == YouTubeItemStatus.FAILED.value, 1),
                        else_=0
                    )
                ).label("failed"),
            ).where(YouTubePlaylistItem.playlist_id == playlist_id)
        ).one()

        playlist_response = YouTubePlaylistResponse(
            id=playlist.id,
            user_id=playlist.user.id,
            user_email=playlist.user.email,
            user_display_name=playlist.user.display_name,
            youtube_playlist_id=playlist.youtube_playlist_id,
            title=playlist.title,
            description=playlist.description,
            download_type=playlist.download_type,
            is_liked_songs=playlist.is_liked_songs,
            jellyfin_playlist_id=playlist.jellyfin_playlist_id,
            last_synced_at=playlist.last_synced_at,
            item_count=item_counts.total or 0,
            pending_count=item_counts.pending or 0,
            completed_count=item_counts.completed or 0,
            failed_count=item_counts.failed or 0,
            created_at=playlist.created_at,
            updated_at=playlist.updated_at,
        )

        # Get items with optional filter
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
    """Update playlist settings (e.g., download type)."""
    with _get_session() as session:
        stmt = (
            select(YouTubePlaylist)
            .options(joinedload(YouTubePlaylist.user))
            .where(YouTubePlaylist.id == playlist_id)
        )
        playlist = session.scalar(stmt)

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        if update.download_type is not None:
            playlist.download_type = update.download_type.value

        playlist.updated_at = datetime.now(timezone.utc)
        session.commit()

        # Get counts for response
        item_counts = session.execute(
            select(
                func.count(YouTubePlaylistItem.id).label("total"),
                func.sum(
                    func.case(
                        (YouTubePlaylistItem.download_status == YouTubeItemStatus.PENDING.value, 1),
                        else_=0
                    )
                ).label("pending"),
                func.sum(
                    func.case(
                        (YouTubePlaylistItem.download_status == YouTubeItemStatus.COMPLETED.value, 1),
                        else_=0
                    )
                ).label("completed"),
                func.sum(
                    func.case(
                        (YouTubePlaylistItem.download_status == YouTubeItemStatus.FAILED.value, 1),
                        else_=0
                    )
                ).label("failed"),
            ).where(YouTubePlaylistItem.playlist_id == playlist_id)
        ).one()

        return YouTubePlaylistResponse(
            id=playlist.id,
            user_id=playlist.user.id,
            user_email=playlist.user.email,
            user_display_name=playlist.user.display_name,
            youtube_playlist_id=playlist.youtube_playlist_id,
            title=playlist.title,
            description=playlist.description,
            download_type=playlist.download_type,
            is_liked_songs=playlist.is_liked_songs,
            jellyfin_playlist_id=playlist.jellyfin_playlist_id,
            last_synced_at=playlist.last_synced_at,
            item_count=item_counts.total or 0,
            pending_count=item_counts.pending or 0,
            completed_count=item_counts.completed or 0,
            failed_count=item_counts.failed or 0,
            created_at=playlist.created_at,
            updated_at=playlist.updated_at,
        )


# Sync Operations


@router.post("/sync/all")
async def sync_all_playlists(background_tasks: BackgroundTasks):
    """Trigger sync for all users and playlists."""
    if youtube_sync.is_running:
        raise HTTPException(status_code=409, detail="Sync already running")

    background_tasks.add_task(youtube_sync.sync_all)
    return {"status": "started", "message": "YouTube sync started in background"}


@router.post("/playlists/{playlist_id}/sync")
async def sync_playlist(playlist_id: str, background_tasks: BackgroundTasks):
    """Trigger sync for a specific playlist."""
    with _get_session() as session:
        playlist = session.get(YouTubePlaylist, playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

    background_tasks.add_task(youtube_sync.sync_playlist, playlist_id)
    return {"status": "started", "message": f"Sync started for playlist {playlist_id}"}


@router.get("/sync/status", response_model=YouTubeSyncStatusResponse)
async def get_sync_status():
    """Get current sync status."""
    with _get_session() as session:
        # Check quota
        quota_stmt = (
            select(YouTubeQuota)
            .where(YouTubeQuota.reset_date >= datetime.now(timezone.utc))
            .order_by(YouTubeQuota.created_at.desc())
            .limit(1)
        )
        quota = session.scalar(quota_stmt)

        quota_exceeded = False
        quota_reset_at = None

        if quota and quota.quota_exceeded_until:
            if datetime.now(timezone.utc) < quota.quota_exceeded_until:
                quota_exceeded = True
                quota_reset_at = quota.quota_exceeded_until

    return YouTubeSyncStatusResponse(
        is_running=youtube_sync.is_running,
        current_user_id=youtube_sync.current_user_id,
        current_playlist_id=youtube_sync.current_playlist_id,
        current_playlist_title=youtube_sync.current_playlist_title,
        progress_message=youtube_sync.progress_message,
        quota_exceeded=quota_exceeded,
        quota_reset_at=quota_reset_at,
    )


@router.get("/quota", response_model=YouTubeQuotaResponse)
async def get_quota_info():
    """Get YouTube API quota information."""
    with _get_session() as session:
        stmt = (
            select(YouTubeQuota)
            .where(YouTubeQuota.reset_date >= datetime.now(timezone.utc))
            .order_by(YouTubeQuota.created_at.desc())
            .limit(1)
        )
        quota = session.scalar(stmt)

        if not quota:
            # No quota record yet
            return YouTubeQuotaResponse(
                units_used=0,
                units_remaining=10000,
                quota_exceeded=False,
                reset_date=datetime.now(timezone.utc),
            )

        quota_exceeded = False
        if quota.quota_exceeded_until:
            if datetime.now(timezone.utc) < quota.quota_exceeded_until:
                quota_exceeded = True

        return YouTubeQuotaResponse(
            units_used=quota.units_used,
            units_remaining=max(0, 10000 - quota.units_used),
            quota_exceeded=quota_exceeded,
            reset_date=quota.reset_date,
            quota_exceeded_until=quota.quota_exceeded_until,
        )
