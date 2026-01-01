"""Simple YouTube models for cookie-based approach."""

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


class YouTubeConfigResponse(BaseModel):
    """Response containing YouTube configuration status."""
    cookies_uploaded: bool
    cookies_uploaded_at: Optional[datetime] = None


class YouTubePlaylistCreate(BaseModel):
    """Request to manually add a YouTube playlist."""
    url: str = Field(description="YouTube playlist URL")
    download_type: DownloadType = DownloadType.AUDIO


class YouTubePlaylistUpdate(BaseModel):
    """Request to update a YouTube playlist."""
    download_type: Optional[DownloadType] = None


class YouTubePlaylistResponse(BaseModel):
    """Response containing YouTube playlist information."""
    id: str
    url: str
    youtube_playlist_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    download_type: DownloadType
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


class YouTubeSyncStatusResponse(BaseModel):
    """Response containing YouTube sync status."""
    is_running: bool
    current_playlist_id: Optional[str] = None
    current_playlist_title: Optional[str] = None
    progress_message: Optional[str] = None


class YouTubeExtractResponse(BaseModel):
    """Response from extracting playlist info."""
    playlist_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    item_count: int = 0
