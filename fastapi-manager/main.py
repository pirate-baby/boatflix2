from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from routers import download, sync, organize

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Media Manager")

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
app.include_router(download.router, prefix="/download", tags=["download"])
app.include_router(sync.router, prefix="/sync", tags=["sync"])
app.include_router(organize.router, prefix="/organize", tags=["organize"])


@app.get("/health")
def health_check():
    return {"status": "healthy"}
