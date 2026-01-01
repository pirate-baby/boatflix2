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
        # Migration 1: Add url column to youtube_playlists if it doesn't exist
        cursor.execute("PRAGMA table_info(youtube_playlists)")
        columns = cursor.fetchall()

        if columns:  # Table exists
            column_names = [col[1] for col in columns]

            if 'url' not in column_names:
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
