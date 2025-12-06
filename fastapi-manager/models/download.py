"""Download-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Optional, Union
from pydantic import BaseModel, Field


class MediaType(str, Enum):
    """Type of media being downloaded."""
    MOVIE = "movie"
    TV = "tv"
    MUSIC = "music"


class DownloadStatus(str, Enum):
    """Status of a download job."""
    PENDING = "pending"
    ANALYZING = "analyzing"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MovieMetadata(BaseModel):
    """Metadata for a movie download."""
    title: str
    year: Optional[int] = None
    description: Optional[str] = None


class TVMetadata(BaseModel):
    """Metadata for a TV episode download."""
    show: str
    year: Optional[int] = None
    season: int
    episode: int
    episode_title: Optional[str] = None


class MusicMetadata(BaseModel):
    """Metadata for a music track download."""
    artist: str
    album: Optional[str] = None
    track: str
    track_number: Optional[int] = None
    release_year: Optional[int] = None


class AnalyzeRequest(BaseModel):
    """Request to analyze a URL for metadata."""
    url: str


class AnalyzeResponse(BaseModel):
    """Response from URL analysis with detected metadata."""
    url: str
    media_type: MediaType
    metadata: Union[MovieMetadata, TVMetadata, MusicMetadata]
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0-1")
    raw_title: Optional[str] = None
    thumbnail: Optional[str] = None
    duration: Optional[int] = None


class DownloadRequest(BaseModel):
    """Request to start a download with confirmed metadata."""
    url: str
    media_type: MediaType
    metadata: Union[MovieMetadata, TVMetadata, MusicMetadata]


class DownloadJob(BaseModel):
    """A download job in the queue or history."""
    id: str
    url: str
    media_type: MediaType
    metadata: Union[MovieMetadata, TVMetadata, MusicMetadata]
    status: DownloadStatus
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    error: Optional[str] = None
    output_path: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class DownloadQueueResponse(BaseModel):
    """Response listing the download queue."""
    active: Optional[DownloadJob] = None
    pending: list[DownloadJob] = []


class DownloadHistoryResponse(BaseModel):
    """Response listing download history."""
    downloads: list[DownloadJob] = []
    total: int = 0
