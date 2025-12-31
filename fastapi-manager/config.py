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

    # PySceneDetect settings for commercial splitting
    SCENE_DETECT_ENABLED: bool = os.getenv("SCENE_DETECT_ENABLED", "false").lower() == "true"
    SCENE_DETECT_CRON: str = os.getenv("SCENE_DETECT_CRON", "0 3 * * *")
    SCENE_DETECT_THRESHOLD: float = float(os.getenv("SCENE_DETECT_THRESHOLD", "27.0"))
    SCENE_DETECT_MIN_SCENE_LEN: float = float(os.getenv("SCENE_DETECT_MIN_SCENE_LEN", "0.5"))

    # Transcode settings for Chromium-compatible video conversion
    # CRF 22 = good quality/size balance for Pi storage, preset slow = better compression
    TRANSCODE_CRF: int = int(os.getenv("TRANSCODE_CRF", "22"))
    TRANSCODE_PRESET: str = os.getenv("TRANSCODE_PRESET", "slow")
    TRANSCODE_AUDIO_BITRATE: str = os.getenv("TRANSCODE_AUDIO_BITRATE", "128k")
    TRANSCODE_HARDWARE_ACCEL: str | None = os.getenv("TRANSCODE_HARDWARE_ACCEL")
    TRANSCODE_ARCHIVE_ORIGINAL: bool = os.getenv("TRANSCODE_ARCHIVE_ORIGINAL", "true").lower() == "true"

    # YouTube sync settings
    YOUTUBE_SYNC_ENABLED: bool = os.getenv("YOUTUBE_SYNC_ENABLED", "true").lower() == "true"
    YOUTUBE_SYNC_CRON: str = os.getenv("YOUTUBE_SYNC_CRON", "0 */6 * * *")  # Every 6 hours
    YOUTUBE_CLIENT_ID: str | None = os.getenv("YOUTUBE_CLIENT_ID")
    YOUTUBE_CLIENT_SECRET: str | None = os.getenv("YOUTUBE_CLIENT_SECRET")
    YOUTUBE_REDIRECT_URI: str = os.getenv("YOUTUBE_REDIRECT_URI", "http://manager.localhost/manager/youtube")
    # Encryption key for OAuth tokens (must be 32 url-safe base64-encoded bytes)
    YOUTUBE_ENCRYPTION_KEY: str | None = os.getenv("YOUTUBE_ENCRYPTION_KEY")


settings = Settings()
