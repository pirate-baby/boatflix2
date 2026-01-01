"""SQLAlchemy database models."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Text, DateTime, Index, ForeignKey, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.download import (
    DownloadJob,
    DownloadStatus,
    MediaType,
    MovieMetadata,
    TVMetadata,
    MusicMetadata,
    CommercialMetadata,
)


class Download(Base):
    """SQLAlchemy model for download jobs."""

    __tablename__ = "downloads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_created_at", "created_at"),
        Index("idx_completed_at", "completed_at"),
    )

    def get_metadata(self) -> MovieMetadata | TVMetadata | MusicMetadata | CommercialMetadata:
        """Deserialize metadata from JSON."""
        parsed = json.loads(self.metadata_json)
        media_type = MediaType(self.media_type)
        if media_type == MediaType.MOVIE:
            return MovieMetadata(**parsed)
        elif media_type == MediaType.TV:
            return TVMetadata(**parsed)
        elif media_type == MediaType.MUSIC:
            return MusicMetadata(**parsed)
        else:
            return CommercialMetadata(**parsed)

    def set_metadata(self, metadata: MovieMetadata | TVMetadata | MusicMetadata | CommercialMetadata):
        """Serialize metadata to JSON."""
        self.metadata_json = json.dumps(metadata.model_dump())

    def to_pydantic(self) -> DownloadJob:
        """Convert to Pydantic model."""
        return DownloadJob(
            id=self.id,
            url=self.url,
            media_type=MediaType(self.media_type),
            metadata=self.get_metadata(),
            status=DownloadStatus(self.status),
            progress=self.progress or 0.0,
            error=self.error,
            output_path=self.output_path,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
        )


class YouTubeConfig(Base):
    """SQLAlchemy model for YouTube configuration (cookies status)."""

    __tablename__ = "youtube_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cookies_uploaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cookies_uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )


class YouTubePlaylist(Base):
    """SQLAlchemy model for YouTube playlists (added manually by user)."""

    __tablename__ = "youtube_playlists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)  # Original playlist URL
    youtube_playlist_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Extracted from URL
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # ENUM: audio, video
    download_type: Mapped[str] = mapped_column(String(20), nullable=False, default="audio")
    jellyfin_playlist_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    # Relationships
    items: Mapped[list["YouTubePlaylistItem"]] = relationship(
        "YouTubePlaylistItem", back_populates="playlist", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_youtube_playlist_youtube_id", "youtube_playlist_id", unique=True),
        Index("idx_youtube_playlist_url", "url", unique=True),
    )


class YouTubePlaylistItem(Base):
    """SQLAlchemy model for items in YouTube playlists."""

    __tablename__ = "youtube_playlist_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    playlist_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_playlists.id"), nullable=False
    )
    youtube_video_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    artist: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # ENUM: pending, downloading, completed, failed
    download_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    download_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("downloads.id"), nullable=True
    )
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_to_playlist_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False
    )
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    # Relationships
    playlist: Mapped["YouTubePlaylist"] = relationship(
        "YouTubePlaylist", back_populates="items"
    )

    __table_args__ = (
        Index("idx_youtube_item_playlist", "playlist_id"),
        Index("idx_youtube_item_video_id", "youtube_video_id", "playlist_id", unique=True),
        Index("idx_youtube_item_status", "download_status"),
    )


