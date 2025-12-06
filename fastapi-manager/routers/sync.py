"""Sync router for rclone bidirectional sync API endpoints."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from services import rclone

router = APIRouter()

# Track if a sync is currently running
_sync_in_progress = False


@router.post("/run")
async def run_sync(
    background_tasks: BackgroundTasks,
    resync: bool = Query(False, description="Force resync (use for recovery)"),
):
    """Trigger a manual sync operation.

    The sync runs in the background. Use GET /sync/status to monitor progress.

    Args:
        resync: Force --resync flag (normally only used on first run)

    Returns:
        Status message indicating sync was started
    """
    global _sync_in_progress

    if _sync_in_progress:
        raise HTTPException(status_code=409, detail="Sync already in progress")

    # Check configuration
    config = rclone.check_rclone_config()
    if not config["remote_configured"] or not config["bucket_configured"]:
        raise HTTPException(
            status_code=400,
            detail="RCLONE_REMOTE and RCLONE_BUCKET must be configured",
        )

    async def do_sync():
        global _sync_in_progress
        _sync_in_progress = True
        try:
            await rclone.run_bisync(force_resync=resync)
        finally:
            _sync_in_progress = False

    background_tasks.add_task(do_sync)

    return {
        "status": "started",
        "message": "Sync operation started in background",
        "resync": resync,
    }


@router.get("/status")
async def get_status():
    """Get the status of sync operations.

    Returns:
        - last_sync: Timestamp of last sync
        - status: 'success', 'failed', 'never_run', or 'in_progress'
        - success: Boolean of last sync result
        - duration_seconds: Duration of last sync
        - total_syncs: Total number of sync operations
        - successful_syncs: Number of successful syncs
        - failed_syncs: Number of failed syncs
    """
    status = rclone.get_sync_status()
    status["in_progress"] = _sync_in_progress
    if _sync_in_progress:
        status["status"] = "in_progress"
    return status


@router.get("/logs")
async def get_logs(
    lines: int = Query(100, ge=1, le=1000, description="Number of log lines to return"),
):
    """Get recent sync log lines.

    Args:
        lines: Number of lines to return (1-1000, default 100)

    Returns:
        List of log lines with timestamps
    """
    return {"logs": rclone.get_sync_logs(lines)}


@router.get("/config")
async def get_config():
    """Get rclone configuration status.

    Returns:
        Configuration details including:
        - rclone_installed: Whether rclone binary is available
        - rclone_version: Version string if installed
        - remote_configured: Whether RCLONE_REMOTE env is set
        - bucket_configured: Whether RCLONE_BUCKET env is set
        - remote_exists: Whether the remote is configured in rclone
        - sync_enabled: Whether scheduled sync is enabled
        - sync_cron: Cron expression for scheduled sync
    """
    return rclone.check_rclone_config()
