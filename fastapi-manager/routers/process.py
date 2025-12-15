"""Process router for PySceneDetect video splitting API endpoints."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from services import pyscenedetect

router = APIRouter()

# Track if processing is currently running
_process_in_progress = False


class ProcessVideoRequest(BaseModel):
    """Request model for processing a single video."""

    video_path: str
    threshold: float = 27.0
    min_scene_len: float = 0.5
    algorithm: str = "content"  # content, adaptive, threshold, hash


class ProcessDirectoryRequest(BaseModel):
    """Request model for processing a directory."""

    directory: Optional[str] = None
    threshold: float = 27.0
    min_scene_len: float = 0.5
    algorithm: str = "content"  # content, adaptive, threshold, hash


@router.post("/split")
async def split_video(
    request: ProcessVideoRequest,
    background_tasks: BackgroundTasks,
):
    """Split a single video file into scenes.

    The split operation runs in the background. Use GET /process/status to monitor.

    Args:
        request: Video path and detection parameters

    Returns:
        Status message indicating processing was started
    """
    global _process_in_progress

    video_path = Path(request.video_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video not found: {request.video_path}")

    if _process_in_progress:
        raise HTTPException(status_code=409, detail="Processing already in progress")

    async def do_split():
        global _process_in_progress
        _process_in_progress = True
        try:
            await pyscenedetect.split_video(
                video_path,
                threshold=request.threshold,
                min_scene_len=request.min_scene_len,
                algorithm=request.algorithm,
            )
        finally:
            _process_in_progress = False

    background_tasks.add_task(do_split)

    return {
        "status": "started",
        "message": "Video split operation started in background",
        "video_path": str(video_path),
        "threshold": request.threshold,
        "min_scene_len": request.min_scene_len,
        "algorithm": request.algorithm,
    }


@router.post("/detect")
async def detect_scenes(request: ProcessVideoRequest):
    """Detect scenes in a video without splitting.

    This is a synchronous operation that returns scene boundaries.

    Args:
        request: Video path and detection parameters

    Returns:
        Scene detection results with timestamps
    """
    video_path = Path(request.video_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video not found: {request.video_path}")

    result = await pyscenedetect.detect_scenes(
        video_path,
        threshold=request.threshold,
        min_scene_len=request.min_scene_len,
        algorithm=request.algorithm,
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Scene detection failed"))

    return result


@router.post("/directory")
async def process_directory(
    background_tasks: BackgroundTasks,
    request: ProcessDirectoryRequest = None,
):
    """Process all unprocessed videos in a directory.

    By default processes the Commercials directory. The operation runs in the background.

    Args:
        request: Optional directory path and detection parameters

    Returns:
        Status message indicating processing was started
    """
    global _process_in_progress

    if _process_in_progress:
        raise HTTPException(status_code=409, detail="Processing already in progress")

    if request is None:
        request = ProcessDirectoryRequest()

    directory = Path(request.directory) if request.directory else None

    if directory and not directory.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {request.directory}")

    async def do_process():
        global _process_in_progress
        _process_in_progress = True
        try:
            await pyscenedetect.process_directory(
                directory,
                threshold=request.threshold,
                min_scene_len=request.min_scene_len,
                algorithm=request.algorithm,
            )
        finally:
            _process_in_progress = False

    background_tasks.add_task(do_process)

    target_dir = str(directory) if directory else str(pyscenedetect.get_commercials_directory())

    return {
        "status": "started",
        "message": "Directory processing started in background",
        "directory": target_dir,
        "threshold": request.threshold,
        "min_scene_len": request.min_scene_len,
        "algorithm": request.algorithm,
    }


@router.get("/list")
async def list_videos_to_process(
    directory: Optional[str] = Query(None, description="Directory to scan (default: Commercials)"),
):
    """List videos that are ready to be processed.

    Returns videos that haven't been processed yet and don't appear to be
    split output files.

    Args:
        directory: Optional directory to scan

    Returns:
        List of video files ready for processing
    """
    dir_path = Path(directory) if directory else None
    videos = pyscenedetect.find_videos_to_process(dir_path)

    return {
        "directory": str(dir_path or pyscenedetect.get_commercials_directory()),
        "videos": [
            {
                "path": str(v),
                "name": v.name,
                "size_mb": round(v.stat().st_size / (1024 * 1024), 2),
            }
            for v in videos
        ],
        "count": len(videos),
    }


@router.get("/status")
async def get_status():
    """Get the status of scene detection processing.

    Returns:
        - last_process: Timestamp of last processing
        - status: 'success', 'failed', 'never_run', or 'in_progress'
        - total_processed: Total number of videos processed
        - successful_processed: Number of successful processing operations
        - failed_processed: Number of failed processing operations
    """
    status = pyscenedetect.get_process_status()
    status["in_progress"] = _process_in_progress
    if _process_in_progress:
        status["status"] = "in_progress"
    return status


@router.get("/logs")
async def get_logs(
    lines: int = Query(100, ge=1, le=1000, description="Number of log lines to return"),
):
    """Get recent processing log lines.

    Args:
        lines: Number of lines to return (1-1000, default 100)

    Returns:
        List of log lines with timestamps
    """
    return {"logs": pyscenedetect.get_process_logs(lines)}


@router.get("/config")
async def get_config():
    """Get PySceneDetect configuration status.

    Returns:
        Configuration details including:
        - scenedetect_installed: Whether scenedetect binary is available
        - scenedetect_version: Version string if installed
        - ffmpeg_installed: Whether ffmpeg is available
        - commercials_dir: Path to Commercials directory
        - scene_detect_enabled: Whether scheduled processing is enabled
        - scene_detect_threshold: Detection threshold setting
        - scene_detect_cron: Cron expression for scheduled processing
    """
    return pyscenedetect.check_scenedetect_config()
