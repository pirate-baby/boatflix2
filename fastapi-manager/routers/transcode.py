"""Transcode router for Chromium-compatible video conversion API endpoints."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from config import settings
from services import transcode

router = APIRouter()

# Track if transcoding is currently running
_transcode_in_progress = False


class TranscodeVideoRequest(BaseModel):
    """Request model for transcoding a single video."""

    video_path: str
    crf: Optional[int] = None  # Uses TRANSCODE_CRF from config
    preset: Optional[str] = None  # Uses TRANSCODE_PRESET from config
    audio_bitrate: Optional[str] = None  # Uses TRANSCODE_AUDIO_BITRATE from config
    hardware_accel: Optional[str] = None  # Uses TRANSCODE_HARDWARE_ACCEL from config
    force: bool = False
    archive_original: Optional[bool] = None  # Uses TRANSCODE_ARCHIVE_ORIGINAL from config


class TranscodeDirectoryRequest(BaseModel):
    """Request model for transcoding a directory."""

    directory: Optional[str] = None
    recursive: bool = True
    crf: Optional[int] = None
    preset: Optional[str] = None
    audio_bitrate: Optional[str] = None
    hardware_accel: Optional[str] = None
    archive_original: Optional[bool] = None


class ScanDirectoryRequest(BaseModel):
    """Request model for scanning a directory."""

    directory: Optional[str] = None
    recursive: bool = True


@router.post("/video")
async def transcode_video(
    request: TranscodeVideoRequest,
    background_tasks: BackgroundTasks,
):
    """Transcode a single video file to Chromium-compatible format.

    The transcode operation runs in the background. Use GET /transcode/status to monitor.

    Args:
        request: Video path and encoding parameters

    Returns:
        Status message indicating transcoding was started
    """
    global _transcode_in_progress

    video_path = Path(request.video_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video not found: {request.video_path}")

    if _transcode_in_progress:
        raise HTTPException(status_code=409, detail="Transcoding already in progress")

    # Use config defaults for any unspecified values
    crf = request.crf if request.crf is not None else settings.TRANSCODE_CRF
    preset = request.preset if request.preset is not None else settings.TRANSCODE_PRESET
    audio_bitrate = request.audio_bitrate if request.audio_bitrate is not None else settings.TRANSCODE_AUDIO_BITRATE
    hardware_accel = request.hardware_accel if request.hardware_accel is not None else settings.TRANSCODE_HARDWARE_ACCEL
    archive_original = request.archive_original if request.archive_original is not None else settings.TRANSCODE_ARCHIVE_ORIGINAL

    async def do_transcode():
        global _transcode_in_progress
        _transcode_in_progress = True
        try:
            await transcode.transcode_video(
                video_path,
                crf=crf,
                preset=preset,
                audio_bitrate=audio_bitrate,
                hardware_accel=hardware_accel,
                force=request.force,
                archive_original=archive_original,
            )
        finally:
            _transcode_in_progress = False

    background_tasks.add_task(do_transcode)

    return {
        "status": "started",
        "message": "Video transcode operation started in background",
        "video_path": str(video_path),
        "crf": crf,
        "preset": preset,
        "hardware_accel": hardware_accel,
        "archive_original": archive_original,
    }


@router.post("/probe")
async def probe_video(request: TranscodeVideoRequest):
    """Probe a video file to check its codec information and compatibility.

    This is a synchronous operation that returns codec info.

    Args:
        request: Video path to probe

    Returns:
        Probe results with codec information and compatibility status
    """
    video_path = Path(request.video_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video not found: {request.video_path}")

    probe_result = await transcode.probe_video(video_path)
    if not probe_result.get("success"):
        raise HTTPException(status_code=500, detail=probe_result.get("error", "Probe failed"))

    compatibility = transcode.check_chromium_compatibility(probe_result)

    return {
        "probe": probe_result,
        "compatibility": compatibility,
    }


@router.post("/scan")
async def scan_directory(request: ScanDirectoryRequest = None):
    """Scan a directory to check compatibility of all videos.

    Args:
        request: Directory path and scan options

    Returns:
        Scan results with compatibility breakdown
    """
    if request is None:
        request = ScanDirectoryRequest()

    directory = Path(request.directory) if request.directory else Path(settings.MEDIA_BASE)

    if not directory.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")

    result = await transcode.scan_directory(directory, recursive=request.recursive)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Scan failed"))

    return result


@router.post("/directory")
async def transcode_directory(
    background_tasks: BackgroundTasks,
    request: TranscodeDirectoryRequest = None,
):
    """Transcode all incompatible videos in a directory.

    The operation runs in the background. Use GET /transcode/status to monitor.

    Args:
        request: Directory path and encoding parameters

    Returns:
        Status message indicating transcoding was started
    """
    global _transcode_in_progress

    if _transcode_in_progress:
        raise HTTPException(status_code=409, detail="Transcoding already in progress")

    if request is None:
        request = TranscodeDirectoryRequest()

    directory = Path(request.directory) if request.directory else Path(settings.MEDIA_BASE)

    if not directory.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")

    # Use config defaults for any unspecified values
    crf = request.crf if request.crf is not None else settings.TRANSCODE_CRF
    preset = request.preset if request.preset is not None else settings.TRANSCODE_PRESET
    audio_bitrate = request.audio_bitrate if request.audio_bitrate is not None else settings.TRANSCODE_AUDIO_BITRATE
    hardware_accel = request.hardware_accel if request.hardware_accel is not None else settings.TRANSCODE_HARDWARE_ACCEL
    archive_original = request.archive_original if request.archive_original is not None else settings.TRANSCODE_ARCHIVE_ORIGINAL

    async def do_transcode():
        global _transcode_in_progress
        _transcode_in_progress = True
        try:
            await transcode.transcode_directory(
                directory,
                recursive=request.recursive,
                crf=crf,
                preset=preset,
                audio_bitrate=audio_bitrate,
                hardware_accel=hardware_accel,
                archive_original=archive_original,
            )
        finally:
            _transcode_in_progress = False

    background_tasks.add_task(do_transcode)

    return {
        "status": "started",
        "message": "Directory transcode operation started in background",
        "directory": str(directory),
        "recursive": request.recursive,
        "crf": crf,
        "preset": preset,
        "hardware_accel": hardware_accel,
        "archive_original": archive_original,
    }


@router.get("/list")
async def list_videos_to_transcode(
    directory: Optional[str] = Query(None, description="Directory to scan"),
    recursive: bool = Query(True, description="Scan subdirectories"),
):
    """List videos that need transcoding.

    Returns videos that haven't been processed yet.

    Args:
        directory: Optional directory to scan (default: MEDIA_BASE)
        recursive: Whether to scan subdirectories

    Returns:
        List of video files ready for transcoding
    """
    dir_path = Path(directory) if directory else Path(settings.MEDIA_BASE)

    if not dir_path.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {dir_path}")

    videos = transcode.find_videos_to_transcode(dir_path, recursive)

    return {
        "directory": str(dir_path),
        "recursive": recursive,
        "videos": [
            {
                "path": str(v),
                "name": v.name,
                "relative_path": str(v.relative_to(dir_path)),
                "size_mb": round(v.stat().st_size / (1024 * 1024), 2),
            }
            for v in videos
        ],
        "count": len(videos),
    }


@router.get("/status")
async def get_status():
    """Get the status of transcoding processing.

    Returns:
        - last_transcode: Timestamp of last transcoding
        - status: 'success', 'failed', 'never_run', or 'in_progress'
        - total_processed: Total number of videos processed
        - space_saved_mb: Total space difference from transcoding
    """
    status = transcode.get_transcode_status()
    status["in_progress"] = _transcode_in_progress
    if _transcode_in_progress:
        status["status"] = "in_progress"
    return status


@router.get("/logs")
async def get_logs(
    lines: int = Query(100, ge=1, le=1000, description="Number of log lines to return"),
):
    """Get recent transcoding log lines.

    Args:
        lines: Number of lines to return (1-1000, default 100)

    Returns:
        List of log lines with timestamps
    """
    return {"logs": transcode.get_transcode_logs(lines)}


@router.get("/config")
async def get_config():
    """Get transcoding configuration status.

    Returns:
        Configuration details including:
        - ffmpeg_installed: Whether ffmpeg is available
        - ffprobe_installed: Whether ffprobe is available
        - hardware_acceleration: Available hardware encoders
        - media_base: Path to media directory
        - default settings for transcoding
        - remote_transcode settings and status
    """
    config = transcode.check_transcode_config()
    config.update({
        "transcode_crf": settings.TRANSCODE_CRF,
        "transcode_preset": settings.TRANSCODE_PRESET,
        "transcode_audio_bitrate": settings.TRANSCODE_AUDIO_BITRATE,
        "transcode_hardware_accel": settings.TRANSCODE_HARDWARE_ACCEL,
        "transcode_archive_original": settings.TRANSCODE_ARCHIVE_ORIGINAL,
        "remote_transcode_enabled": settings.REMOTE_TRANSCODE_ENABLED,
        "remote_transcode_host": settings.REMOTE_TRANSCODE_HOST if settings.REMOTE_TRANSCODE_ENABLED else None,
    })
    return config


@router.get("/remote/check")
async def check_remote_host():
    """Check remote transcoding host status and capabilities.

    Returns:
        Remote host connection status and available features
    """
    from services import remote_transcode
    return await remote_transcode.check_remote_host()
