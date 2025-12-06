"""Pydantic models for the media manager API."""

from .download import (
    MediaType,
    DownloadStatus,
    MovieMetadata,
    TVMetadata,
    MusicMetadata,
    AnalyzeRequest,
    AnalyzeResponse,
    DownloadRequest,
    DownloadJob,
    DownloadQueueResponse,
    DownloadHistoryResponse,
)
from .db import Download

__all__ = [
    "MediaType",
    "DownloadStatus",
    "MovieMetadata",
    "TVMetadata",
    "MusicMetadata",
    "AnalyzeRequest",
    "AnalyzeResponse",
    "DownloadRequest",
    "DownloadJob",
    "DownloadQueueResponse",
    "DownloadHistoryResponse",
    "Download",
]
