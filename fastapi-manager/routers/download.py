"""Download router with yt-dlp endpoints."""

from fastapi import APIRouter, HTTPException, Query

from models.download import (
    AnalyzeRequest,
    AnalyzeResponse,
    DownloadRequest,
    DownloadJob,
    DownloadQueueResponse,
    DownloadHistoryResponse,
)
from services.ytdlp import ytdlp_service
from services.download_queue import download_queue

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_url(request: AnalyzeRequest):
    """Analyze a URL and return detected metadata.

    This endpoint runs yt-dlp --dump-json to extract metadata
    and auto-detects the media type (Movie, TV, or Music).
    """
    try:
        return await ytdlp_service.analyze_url(request.url)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.post("", response_model=DownloadJob)
async def start_download(request: DownloadRequest):
    """Submit a download job with confirmed metadata.

    The download will be queued and processed in order.
    Downloads are processed one at a time to avoid overloading the system.
    """
    job = download_queue.add_job(
        url=request.url,
        media_type=request.media_type,
        metadata=request.metadata,
    )
    return job


@router.get("/queue", response_model=DownloadQueueResponse)
async def get_queue():
    """List pending and active downloads."""
    return download_queue.get_queue()


@router.get("/history", response_model=DownloadHistoryResponse)
async def get_history(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List completed downloads with pagination."""
    return download_queue.get_history(limit=limit, offset=offset)


@router.get("/{download_id}", response_model=DownloadJob)
async def get_download(download_id: str):
    """Get a specific download by ID."""
    job = download_queue.get_job(download_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download not found")
    return job


@router.delete("/{download_id}")
async def cancel_download(download_id: str):
    """Cancel a pending or active download."""
    job = download_queue.get_job(download_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download not found")

    if download_queue.cancel_job(download_id):
        return {"status": "cancelled", "id": download_id}
    else:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel download (already completed or cancelled)",
        )
