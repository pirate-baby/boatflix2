from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def sync_status():
    """Get current sync status."""
    return {"status": "idle", "last_sync": None}


@router.post("/trigger")
async def trigger_sync():
    """Manually trigger a sync operation."""
    # TODO: Implement rclone sync
    return {"status": "started"}
