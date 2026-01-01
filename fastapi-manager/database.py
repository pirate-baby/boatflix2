"""Database configuration and session management."""

import logging
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


# Create engine
engine = create_engine(
    f"sqlite:///{settings.DATABASE_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _run_migrations():
    """Run database migrations."""
    db_path = Path(settings.DATABASE_PATH)

    if not db_path.exists():
        logger.info("Database does not exist yet, skipping migrations")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if youtube_playlists table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='youtube_playlists'")
        table_exists = cursor.fetchone() is not None

        if table_exists:
            # Get current table schema
            cursor.execute("PRAGMA table_info(youtube_playlists)")
            columns = cursor.fetchall()
            column_info = {col[1]: col for col in columns}

            # Check if this is the old OAuth-based schema (has user_id)
            has_user_id = 'user_id' in column_info
            has_url = 'url' in column_info

            if has_user_id and not has_url:
                # This is the old OAuth schema - need to migrate to new cookie-based schema
                logger.info("Running migration: Converting from OAuth-based to cookie-based YouTube playlist schema")

                # Check if there's any data
                cursor.execute("SELECT COUNT(*) FROM youtube_playlists")
                row_count = cursor.fetchone()[0]

                if row_count > 0:
                    logger.warning(f"Found {row_count} playlists in old OAuth schema - these will be cleared during migration")

                # Drop old tables
                cursor.execute("DROP TABLE IF EXISTS youtube_playlist_items")
                cursor.execute("DROP TABLE IF EXISTS youtube_playlists")
                cursor.execute("DROP TABLE IF EXISTS youtube_users")
                cursor.execute("DROP TABLE IF EXISTS youtube_quota")

                conn.commit()
                logger.info("Successfully dropped old OAuth-based YouTube tables")

            elif not has_url:
                # Table exists but missing url column
                logger.info("Running migration: Adding url column to youtube_playlists table")
                cursor.execute("""
                    ALTER TABLE youtube_playlists
                    ADD COLUMN url TEXT NOT NULL DEFAULT ''
                """)

                # Create unique index on url
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_youtube_playlist_url
                    ON youtube_playlists(url)
                """)

                conn.commit()
                logger.info("Successfully added url column and index")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database by running migrations and creating all tables."""
    # Run migrations first
    _run_migrations()

    # Create any missing tables
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
