"""API endpoints for torrent organization."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config import settings
from services.metadata import analyze_item
from services.organizer import scan_downloads, move_item, preview_destination

router = APIRouter()

# Templates
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


class AnalyzeRequest(BaseModel):
    """Request body for analyze endpoint."""
    path: str


class MoveRequest(BaseModel):
    """Request body for move endpoint."""
    source_path: str
    media_type: Literal['movie', 'tv', 'music']
    metadata: dict


class PreviewRequest(BaseModel):
    """Request body for preview endpoint."""
    source_path: str
    media_type: Literal['movie', 'tv', 'music']
    metadata: dict


@router.get("/", response_class=HTMLResponse)
async def organize_page(request: Request):
    """Render the organize page."""
    return templates.TemplateResponse(
        "organize.html",
        {
            "request": request,
            "downloads_path": settings.DOWNLOADS_PATH,
            "tmdb_enabled": bool(settings.TMDB_API_KEY)
        }
    )


@router.get("/list")
async def list_downloads():
    """List items in the Downloads folder.

    Returns:
        List of items with name, type, size, and path
    """
    items = await scan_downloads()
    return {
        "downloads_path": settings.DOWNLOADS_PATH,
        "items": items,
        "count": len(items)
    }


@router.post("/analyze")
async def analyze_file(request: AnalyzeRequest):
    """Analyze a file or folder and return detected metadata.

    Args:
        request: AnalyzeRequest with path to analyze

    Returns:
        Analysis result with media_type, metadata, confidence, and tmdb_matches
    """
    try:
        # Validate path is within downloads directory
        item_path = Path(request.path).resolve()
        downloads_path = Path(settings.DOWNLOADS_PATH).resolve()

        if not str(item_path).startswith(str(downloads_path)):
            raise HTTPException(
                status_code=400,
                detail="Path must be within the downloads directory"
            )

        result = await analyze_item(request.path)
        return result

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview")
async def preview_move(request: PreviewRequest):
    """Preview the destination path for a move operation.

    Args:
        request: PreviewRequest with source_path, media_type, and metadata

    Returns:
        Preview with destination path
    """
    try:
        destination = preview_destination(
            request.source_path,
            request.media_type,
            request.metadata
        )
        return {
            "source": request.source_path,
            "destination": destination,
            "media_type": request.media_type
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/move")
async def move_file(request: MoveRequest):
    """Move a file or folder to the appropriate library location.

    Args:
        request: MoveRequest with source_path, media_type, and metadata

    Returns:
        Move result with success status and destination
    """
    try:
        # Validate path is within downloads directory
        item_path = Path(request.source_path).resolve()
        downloads_path = Path(settings.DOWNLOADS_PATH).resolve()

        if not str(item_path).startswith(str(downloads_path)):
            raise HTTPException(
                status_code=400,
                detail="Source path must be within the downloads directory"
            )

        result = await move_item(
            request.source_path,
            request.media_type,
            request.metadata
        )

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Legacy endpoints for backward compatibility
@router.get("/pending")
async def list_pending():
    """List files pending organization (legacy endpoint)."""
    items = await scan_downloads()
    return {"pending": items}


@router.post("/process")
async def process_files():
    """Process and organize downloaded files (legacy endpoint).

    Note: This endpoint is deprecated. Use /analyze and /move instead.
    """
    return {
        "status": "deprecated",
        "message": "Use /organize/analyze and /organize/move endpoints instead",
        "count": 0
    }
