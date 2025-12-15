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


class BatchAnalyzeRequest(BaseModel):
    """Request body for batch analyze endpoint."""
    paths: list[str]


class MoveRequest(BaseModel):
    """Request body for move endpoint."""
    source_path: str
    media_type: Literal['movie', 'tv', 'music']
    metadata: dict


class BulkMoveItem(BaseModel):
    """Single item for bulk move."""
    source_path: str
    media_type: Literal['movie', 'tv', 'music']
    metadata: dict


class BulkMoveRequest(BaseModel):
    """Request body for bulk move endpoint."""
    items: list[BulkMoveItem]


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
            "downloads_path": f"{settings.MEDIA_BASE}/Downloads",
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
        "downloads_path": f"{settings.MEDIA_BASE}/Downloads",
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
        downloads_path = Path(f"{settings.MEDIA_BASE}/Downloads").resolve()

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
        downloads_path = Path(f"{settings.MEDIA_BASE}/Downloads").resolve()

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


@router.post("/analyze-batch")
async def analyze_batch(request: BatchAnalyzeRequest):
    """Analyze multiple files/folders and return detected metadata for each.

    Args:
        request: BatchAnalyzeRequest with list of paths to analyze

    Returns:
        List of analysis results with media_type, metadata, confidence, and tmdb_matches
    """
    downloads_path = Path(f"{settings.MEDIA_BASE}/Downloads").resolve()
    results = []

    for path in request.paths:
        try:
            # Validate path is within downloads directory
            item_path = Path(path).resolve()

            if not str(item_path).startswith(str(downloads_path)):
                results.append({
                    "path": path,
                    "error": "Path must be within the downloads directory"
                })
                continue

            result = await analyze_item(path)
            results.append(result)

        except FileNotFoundError:
            results.append({
                "path": path,
                "error": "File not found"
            })
        except Exception as e:
            results.append({
                "path": path,
                "error": str(e)
            })

    return {"results": results}


@router.post("/move-bulk")
async def move_bulk(request: BulkMoveRequest):
    """Move multiple files/folders to their appropriate library locations.

    Args:
        request: BulkMoveRequest with list of items to move

    Returns:
        Bulk move result with success/failure status for each item
    """
    downloads_path = Path(f"{settings.MEDIA_BASE}/Downloads").resolve()
    results = []
    success_count = 0
    error_count = 0

    for item in request.items:
        try:
            # Validate path is within downloads directory
            item_path = Path(item.source_path).resolve()

            if not str(item_path).startswith(str(downloads_path)):
                results.append({
                    "source_path": item.source_path,
                    "success": False,
                    "error": "Source path must be within the downloads directory"
                })
                error_count += 1
                continue

            result = await move_item(
                item.source_path,
                item.media_type,
                item.metadata
            )

            if result['success']:
                success_count += 1
            else:
                error_count += 1

            results.append({
                "source_path": item.source_path,
                **result
            })

        except Exception as e:
            results.append({
                "source_path": item.source_path,
                "success": False,
                "error": str(e)
            })
            error_count += 1

    return {
        "results": results,
        "success_count": success_count,
        "error_count": error_count,
        "total": len(request.items)
    }


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
