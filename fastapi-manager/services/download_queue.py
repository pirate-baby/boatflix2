"""Download queue manager with SQLAlchemy storage."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, init_db
from models.db import Download
from models.download import (
    DownloadJob,
    DownloadStatus,
    MediaType,
    MovieMetadata,
    TVMetadata,
    MusicMetadata,
    DownloadQueueResponse,
    DownloadHistoryResponse,
)
from services.ytdlp import ytdlp_service

logger = logging.getLogger(__name__)


class DownloadQueueManager:
    """Manages the download queue with SQLAlchemy persistence."""

    def __init__(self):
        init_db()
        self._processing = False
        self._current_job_id: Optional[str] = None

    def _get_session(self) -> Session:
        """Get a new database session."""
        return SessionLocal()

    def add_job(
        self,
        url: str,
        media_type: MediaType,
        metadata: MovieMetadata | TVMetadata | MusicMetadata,
        session: Optional[Session] = None,
    ) -> DownloadJob:
        """Add a new download job to the queue.

        Args:
            url: URL to download
            media_type: Type of media (movie/tv/music)
            metadata: Metadata for the download
            session: Optional existing session to use (avoids nested session locks)

        Returns:
            DownloadJob: The created job
        """
        job_id = str(uuid4())
        now = datetime.now()

        download = Download(
            id=job_id,
            url=url,
            media_type=media_type.value,
            metadata_json=json.dumps(metadata.model_dump()),
            status=DownloadStatus.PENDING.value,
            created_at=now,
        )

        if session is not None:
            # Use existing session (don't commit - let caller handle it)
            session.add(download)
        else:
            # Create new session and commit immediately
            with self._get_session() as new_session:
                new_session.add(download)
                new_session.commit()

        return DownloadJob(
            id=job_id,
            url=url,
            media_type=media_type,
            metadata=metadata,
            status=DownloadStatus.PENDING,
            created_at=now,
        )

    def get_job(self, job_id: str) -> Optional[DownloadJob]:
        """Get a job by ID."""
        with self._get_session() as session:
            download = session.get(Download, job_id)
            if download:
                return download.to_pydantic()
        return None

    def update_job(
        self,
        job_id: str,
        status: Optional[DownloadStatus] = None,
        progress: Optional[float] = None,
        error: Optional[str] = None,
        output_path: Optional[str] = None,
    ):
        """Update a job's status/progress."""
        with self._get_session() as session:
            download = session.get(Download, job_id)
            if not download:
                return

            if status is not None:
                download.status = status.value
                if status == DownloadStatus.DOWNLOADING:
                    download.started_at = datetime.now()
                elif status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED):
                    download.completed_at = datetime.now()

            if progress is not None:
                download.progress = progress

            if error is not None:
                download.error = error

            if output_path is not None:
                download.output_path = output_path

            session.commit()

    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID."""
        with self._get_session() as session:
            download = session.get(Download, job_id)
            if download:
                session.delete(download)
                session.commit()
                return True
        return False

    def get_queue(self) -> DownloadQueueResponse:
        """Get the current download queue."""
        with self._get_session() as session:
            # Get active job
            active_stmt = (
                select(Download)
                .where(
                    or_(
                        Download.status == DownloadStatus.DOWNLOADING.value,
                        Download.status == DownloadStatus.ANALYZING.value,
                    )
                )
                .order_by(Download.started_at.desc())
                .limit(1)
            )
            active_download = session.scalar(active_stmt)

            # Get pending jobs
            pending_stmt = (
                select(Download)
                .where(Download.status == DownloadStatus.PENDING.value)
                .order_by(Download.created_at.asc())
            )
            pending_downloads = session.scalars(pending_stmt).all()

            return DownloadQueueResponse(
                active=active_download.to_pydantic() if active_download else None,
                pending=[d.to_pydantic() for d in pending_downloads],
            )

    def get_history(
        self, limit: int = 50, offset: int = 0
    ) -> DownloadHistoryResponse:
        """Get download history (completed/failed jobs)."""
        with self._get_session() as session:
            # Get total count
            count_stmt = select(Download).where(
                or_(
                    Download.status == DownloadStatus.COMPLETED.value,
                    Download.status == DownloadStatus.FAILED.value,
                    Download.status == DownloadStatus.CANCELLED.value,
                )
            )
            total = len(session.scalars(count_stmt).all())

            # Get paginated results
            stmt = (
                select(Download)
                .where(
                    or_(
                        Download.status == DownloadStatus.COMPLETED.value,
                        Download.status == DownloadStatus.FAILED.value,
                        Download.status == DownloadStatus.CANCELLED.value,
                    )
                )
                .order_by(Download.completed_at.desc())
                .offset(offset)
                .limit(limit)
            )
            downloads = session.scalars(stmt).all()

            return DownloadHistoryResponse(
                downloads=[d.to_pydantic() for d in downloads],
                total=total,
            )

    def get_next_pending(self) -> Optional[DownloadJob]:
        """Get the next pending job from the queue."""
        with self._get_session() as session:
            stmt = (
                select(Download)
                .where(Download.status == DownloadStatus.PENDING.value)
                .order_by(Download.created_at.asc())
                .limit(1)
            )
            download = session.scalar(stmt)
            if download:
                return download.to_pydantic()
        return None

    async def process_job(self, job: DownloadJob):
        """Process a single download job."""
        self._current_job_id = job.id
        logger.info(f"Starting download: {job.id} - {job.url}")

        try:
            self.update_job(job.id, status=DownloadStatus.DOWNLOADING)

            def progress_callback(progress: float, status: str):
                self.update_job(job.id, progress=progress)

            output_path = await ytdlp_service.download(
                url=job.url,
                media_type=job.media_type,
                metadata=job.metadata,
                progress_callback=progress_callback,
            )

            self.update_job(
                job.id,
                status=DownloadStatus.COMPLETED,
                progress=100.0,
                output_path=output_path,
            )
            logger.info(f"Download completed: {job.id} -> {output_path}")

        except Exception as e:
            logger.error(f"Download failed: {job.id} - {e}")
            self.update_job(
                job.id,
                status=DownloadStatus.FAILED,
                error=str(e),
            )
        finally:
            self._current_job_id = None

    async def start_worker(self):
        """Start the background worker to process downloads one at a time."""
        if self._processing:
            logger.warning("Worker already running")
            return

        self._processing = True
        logger.info("Download worker started")

        try:
            while self._processing:
                job = self.get_next_pending()
                if job:
                    await self.process_job(job)
                else:
                    await asyncio.sleep(2)
        except asyncio.CancelledError:
            logger.info("Download worker cancelled")
        finally:
            self._processing = False

    def stop_worker(self):
        """Stop the background worker."""
        self._processing = False

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or active job."""
        job = self.get_job(job_id)
        if not job:
            return False

        if job.status in (DownloadStatus.COMPLETED, DownloadStatus.CANCELLED):
            return False

        self.update_job(job_id, status=DownloadStatus.CANCELLED)
        return True


# Singleton instance
download_queue = DownloadQueueManager()
