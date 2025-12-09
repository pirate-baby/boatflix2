import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Container mount path - fixed to match docker-compose volume mount
    MEDIA_BASE: str = "/mnt/media"
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "/app/data/media_manager.db")
    TMDB_API_KEY: str | None = os.getenv("TMDB_API_KEY")
    SYNC_CRON: str = os.getenv("SYNC_CRON", "0 2 * * *")
    SYNC_ENABLED: bool = os.getenv("SYNC_ENABLED", "true").lower() == "true"
    RCLONE_REMOTE: str = os.getenv("RCLONE_REMOTE", "")
    RCLONE_BUCKET: str = os.getenv("RCLONE_BUCKET", "")


settings = Settings()
