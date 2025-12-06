from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_downloads():
    """List active downloads."""
    return {"downloads": []}


@router.post("/")
async def start_download(url: str):
    """Start a new download using yt-dlp."""
    # TODO: Implement yt-dlp download
    return {"status": "queued", "url": url}
