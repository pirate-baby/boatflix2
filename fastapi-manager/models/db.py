"""SQLAlchemy database models."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Text, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.download import (
    DownloadJob,
    DownloadStatus,
    MediaType,
    MovieMetadata,
    TVMetadata,
    MusicMetadata,
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

    def get_metadata(self) -> MovieMetadata | TVMetadata | MusicMetadata:
        """Deserialize metadata from JSON."""
        parsed = json.loads(self.metadata_json)
        media_type = MediaType(self.media_type)
        if media_type == MediaType.MOVIE:
            return MovieMetadata(**parsed)
        elif media_type == MediaType.TV:
            return TVMetadata(**parsed)
        else:
            return MusicMetadata(**parsed)

    def set_metadata(self, metadata: MovieMetadata | TVMetadata | MusicMetadata):
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
