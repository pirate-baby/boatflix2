"""Web routes for the Manager UI."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from config import settings

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the dashboard page."""
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request},
    )


@router.get("/download", response_class=HTMLResponse)
async def download_page(request: Request, url: Optional[str] = Query(None)):
    """Render the download page with optional prefilled URL."""
    return templates.TemplateResponse(
        "download.html",
        {
            "request": request,
            "prefill_url": url,
        },
    )


@router.get("/organize", response_class=HTMLResponse)
async def organize_page(request: Request):
    """Render the organize page."""
    return templates.TemplateResponse(
        "organize.html",
        {
            "request": request,
            "downloads_path": settings.DOWNLOADS_PATH,
            "tmdb_enabled": bool(settings.TMDB_API_KEY),
        },
    )


@router.get("/sync", response_class=HTMLResponse)
async def sync_page(request: Request):
    """Render the sync page."""
    return templates.TemplateResponse(
        "sync.html",
        {"request": request},
    )


# API endpoints for the web UI

@router.get("/api/pending-count")
async def get_pending_count():
    """Get count of items pending organization in Downloads folder."""
    downloads_path = Path(settings.DOWNLOADS_PATH)

    if not downloads_path.exists():
        return JSONResponse({"count": 0, "html": "<p class='muted'>Downloads folder not found</p>"})

    items = list(downloads_path.iterdir())
    count = len(items)

    if count == 0:
        html = "<p class='muted'>No items pending</p>"
    else:
        html = f"<p><strong>{count}</strong> item{'s' if count != 1 else ''} awaiting organization</p>"

    return JSONResponse({"count": count, "html": html})


@router.get("/api/sync-summary")
async def get_sync_summary():
    """Get a quick summary of sync status for the dashboard."""
    from services.rclone import get_sync_status

    try:
        status = await get_sync_status()

        if status.get("is_syncing"):
            html = "<p><span class='badge badge-primary'>Syncing...</span></p>"
        elif status.get("last_sync"):
            last = status["last_sync"]
            if last.get("success"):
                html = f"<p><span class='badge badge-success'>Synced</span> {_format_relative_time(last.get('started_at'))}</p>"
            else:
                html = f"<p><span class='badge badge-error'>Failed</span> {_format_relative_time(last.get('started_at'))}</p>"
        else:
            html = "<p class='muted'>Never synced</p>"

        return JSONResponse({"html": html, **status})
    except Exception as e:
        return JSONResponse({"html": f"<p class='error'>Error: {str(e)}</p>"})


@router.get("/api/files")
async def list_files():
    """List files in the Downloads folder for the file browser."""
    downloads_path = Path(settings.DOWNLOADS_PATH)

    if not downloads_path.exists():
        return JSONResponse({"items": [], "error": "Downloads folder not found"})

    items = []
    for item in sorted(downloads_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        # Skip hidden files
        if item.name.startswith("."):
            continue

        file_type = _detect_file_type(item)
        size_bytes = _get_size(item)

        items.append({
            "name": item.name,
            "path": str(item),
            "is_directory": item.is_dir(),
            "type": file_type,
            "size_bytes": size_bytes,
            "size_formatted": _format_size(size_bytes),
        })

    return JSONResponse({"items": items})


def _detect_file_type(path: Path) -> str:
    """Detect file type based on extension."""
    if path.is_dir():
        return "folder"

    ext = path.suffix.lower()
    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}
    audio_exts = {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma"}

    if ext in video_exts:
        return "video"
    elif ext in audio_exts:
        return "audio"
    else:
        return "unknown"


def _get_size(path: Path) -> int:
    """Get size of file or directory in bytes."""
    if path.is_file():
        return path.stat().st_size
    elif path.is_dir():
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except (OSError, PermissionError):
                    pass
        return total
    return 0


def _format_size(size_bytes: int) -> str:
    """Format size in human-readable format."""
    if size_bytes >= 1073741824:
        return f"{size_bytes / 1073741824:.2f} GB"
    elif size_bytes >= 1048576:
        return f"{size_bytes / 1048576:.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    else:
        return f"{size_bytes} B"


def _format_relative_time(iso_string: Optional[str]) -> str:
    """Format ISO timestamp as relative time."""
    if not iso_string:
        return "Unknown"

    from datetime import datetime

    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo)
        diff = (now - dt).total_seconds()

        if diff < 60:
            return "just now"
        elif diff < 3600:
            return f"{int(diff / 60)}m ago"
        elif diff < 86400:
            return f"{int(diff / 3600)}h ago"
        else:
            return f"{int(diff / 86400)}d ago"
    except Exception:
        return iso_string
