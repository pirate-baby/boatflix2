from fastapi import APIRouter

router = APIRouter()


@router.get("/pending")
async def list_pending():
    """List files pending organization."""
    return {"pending": []}


@router.post("/process")
async def process_files():
    """Process and organize downloaded files."""
    # TODO: Implement file organization
    return {"status": "processing", "count": 0}
