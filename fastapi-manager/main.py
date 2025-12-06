import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from routers import download, sync, organize
from services.download_queue import download_queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown tasks."""
    # Start the download worker
    logger.info("Starting download worker...")
    worker_task = asyncio.create_task(download_queue.start_worker())

    yield

    # Stop the download worker
    logger.info("Stopping download worker...")
    download_queue.stop_worker()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Media Manager", lifespan=lifespan)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Templates
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Include routers
app.include_router(download.router, prefix="/api/download", tags=["download"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(organize.router, prefix="/api/organize", tags=["organize"])


@app.get("/health")
def health_check():
    return {"status": "healthy"}
