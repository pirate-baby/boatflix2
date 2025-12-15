import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import settings
from routers import download, sync, organize, web, process
from services import rclone, pyscenedetect
from services.download_queue import download_queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

# Scheduler instance
scheduler = AsyncIOScheduler()


def parse_cron_expression(cron_expr: str) -> dict:
    """Parse a standard cron expression into APScheduler CronTrigger kwargs.

    Args:
        cron_expr: Standard cron expression (minute hour day month day_of_week)

    Returns:
        Dict with minute, hour, day, month, day_of_week keys
    """
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr}")

    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


async def scheduled_sync():
    """Run scheduled sync job."""
    logger.info("Starting scheduled sync job")
    try:
        result = await rclone.run_bisync()
        if result["success"]:
            logger.info(f"Scheduled sync completed successfully in {result['duration_seconds']:.1f}s")
        else:
            logger.error(f"Scheduled sync failed: {result.get('error', 'Unknown error')}")
    except Exception as e:
        logger.exception(f"Scheduled sync error: {e}")


async def scheduled_scene_detect():
    """Run scheduled scene detection job for commercial splitting."""
    logger.info("Starting scheduled scene detection job")
    try:
        result = await pyscenedetect.process_directory(
            threshold=settings.SCENE_DETECT_THRESHOLD,
            min_scene_len=settings.SCENE_DETECT_MIN_SCENE_LEN,
        )
        if result["success"]:
            logger.info(
                f"Scheduled scene detection completed: "
                f"{result['videos_processed']}/{result['videos_found']} videos processed"
            )
        else:
            logger.error(f"Scheduled scene detection failed: {result.get('error', 'Unknown error')}")
    except Exception as e:
        logger.exception(f"Scheduled scene detection error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown tasks."""
    # Start the download worker
    logger.info("Starting download worker...")
    worker_task = asyncio.create_task(download_queue.start_worker())

    # Start sync scheduler if configured
    if settings.SYNC_ENABLED and settings.RCLONE_REMOTE and settings.RCLONE_BUCKET:
        try:
            cron_kwargs = parse_cron_expression(settings.SYNC_CRON)
            scheduler.add_job(
                scheduled_sync,
                CronTrigger(**cron_kwargs),
                id="rclone_bisync",
                name="rclone bidirectional sync",
                replace_existing=True,
            )
            logger.info(f"Sync scheduler configured with cron: {settings.SYNC_CRON}")
        except Exception as e:
            logger.error(f"Failed to configure sync scheduler: {e}")
    else:
        if not settings.SYNC_ENABLED:
            logger.info("Sync scheduler disabled (SYNC_ENABLED=false)")
        else:
            logger.warning("Sync scheduler not started: RCLONE_REMOTE and RCLONE_BUCKET must be configured")

    # Start scene detection scheduler if configured
    if settings.SCENE_DETECT_ENABLED:
        try:
            cron_kwargs = parse_cron_expression(settings.SCENE_DETECT_CRON)
            scheduler.add_job(
                scheduled_scene_detect,
                CronTrigger(**cron_kwargs),
                id="scene_detect",
                name="PySceneDetect commercial splitting",
                replace_existing=True,
            )
            logger.info(f"Scene detection scheduler configured with cron: {settings.SCENE_DETECT_CRON}")
        except Exception as e:
            logger.error(f"Failed to configure scene detection scheduler: {e}")
    else:
        logger.info("Scene detection scheduler disabled (SCENE_DETECT_ENABLED=false)")

    # Start the scheduler if any jobs were added
    if scheduler.get_jobs():
        scheduler.start()
        logger.info("Scheduler started")

    yield

    # Shutdown sync scheduler
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Sync scheduler stopped")

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
app.include_router(process.router, prefix="/api/process", tags=["process"])
app.include_router(web.router, prefix="/manager", tags=["web"])


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/scheduler/status")
def scheduler_status():
    """Get the status of the scheduler and its jobs."""
    jobs = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })

    return {
        "running": scheduler.running,
        "sync_enabled": settings.SYNC_ENABLED,
        "sync_cron": settings.SYNC_CRON,
        "jobs": jobs,
    }
