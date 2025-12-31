"""YouTube-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DownloadType(str, Enum):
    """Type of download for YouTube content."""
    AUDIO = "audio"
    VIDEO = "video"


class YouTubeItemStatus(str, Enum):
    """Status of a YouTube playlist item download."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


class YouTubeUserCreate(BaseModel):
    """Request to create a new YouTube user (from OAuth callback)."""
    email: str
    display_name: str
    channel_id: str
    access_token: str
    refresh_token: str
    token_expiry: datetime


class YouTubeUserResponse(BaseModel):
    """Response containing YouTube user information."""
    id: str
    email: str
    display_name: str
    channel_id: str
    created_at: datetime
    updated_at: datetime
    playlist_count: int = 0


class YouTubePlaylistCreate(BaseModel):
    """Request to create a new YouTube playlist tracking."""
    user_id: str
    youtube_playlist_id: str
    title: str
    description: Optional[str] = None
    download_type: DownloadType = DownloadType.AUDIO
    is_liked_songs: bool = False


class YouTubePlaylistUpdate(BaseModel):
    """Request to update a YouTube playlist."""
    download_type: Optional[DownloadType] = None


class YouTubePlaylistResponse(BaseModel):
    """Response containing YouTube playlist information."""
    id: str
    user_id: str
    user_email: str
    user_display_name: str
    youtube_playlist_id: str
    title: str
    description: Optional[str] = None
    download_type: DownloadType
    is_liked_songs: bool
    jellyfin_playlist_id: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    item_count: int = 0
    pending_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    created_at: datetime
    updated_at: datetime


class YouTubePlaylistItemResponse(BaseModel):
    """Response containing YouTube playlist item information."""
    id: str
    playlist_id: str
    youtube_video_id: str
    title: str
    artist: Optional[str] = None
    position: int
    download_status: YouTubeItemStatus
    download_id: Optional[str] = None
    file_path: Optional[str] = None
    added_to_playlist_at: datetime
    downloaded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class YouTubePlaylistDetailResponse(BaseModel):
    """Response containing detailed YouTube playlist with items."""
    playlist: YouTubePlaylistResponse
    items: list[YouTubePlaylistItemResponse] = []
    total_items: int = 0


class YouTubePlaylistsGroupedResponse(BaseModel):
    """Response containing playlists grouped by user."""
    user_id: str
    user_email: str
    user_display_name: str
    playlists: list[YouTubePlaylistResponse] = []


class YouTubeAllPlaylistsResponse(BaseModel):
    """Response containing all playlists grouped by user."""
    users: list[YouTubePlaylistsGroupedResponse] = []
    total_playlists: int = 0


class YouTubeSyncRequest(BaseModel):
    """Request to sync YouTube playlists."""
    playlist_id: Optional[str] = None
    user_id: Optional[str] = None


class YouTubeSyncStatusResponse(BaseModel):
    """Response containing YouTube sync status."""
    is_running: bool
    current_user_id: Optional[str] = None
    current_playlist_id: Optional[str] = None
    current_playlist_title: Optional[str] = None
    progress_message: Optional[str] = None
    quota_exceeded: bool = False
    quota_reset_at: Optional[datetime] = None


class YouTubeQuotaResponse(BaseModel):
    """Response containing YouTube API quota information."""
    units_used: int
    units_remaining: int = Field(description="Remaining units out of 10,000 daily quota")
    quota_exceeded: bool = False
    reset_date: datetime
    quota_exceeded_until: Optional[datetime] = None


class YouTubeAuthStartResponse(BaseModel):
    """Response to start OAuth flow."""
    auth_url: str
    state: str


class YouTubeAuthCallbackRequest(BaseModel):
    """Request from OAuth callback."""
    code: str
    state: str
