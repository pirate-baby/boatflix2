#!/usr/bin/env python3
"""
Standalone migration script to convert from OAuth-based to cookie-based YouTube schema.
Run this script inside the Docker container to fix the schema mismatch.

Usage:
    docker exec -it manager python /app/run_migration.py
"""

import sqlite3
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Run the migration."""
    # Database path (hardcoded for container environment)
    db_path = Path("/app/data/media_manager.db")

    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        return 1

    logger.info(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if youtube_playlists table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='youtube_playlists'")
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            logger.info("youtube_playlists table doesn't exist - no migration needed")
            return 0

        # Get current table schema
        cursor.execute("PRAGMA table_info(youtube_playlists)")
        columns = cursor.fetchall()
        column_info = {col[1]: col for col in columns}

        logger.info(f"Current columns in youtube_playlists: {list(column_info.keys())}")

        # Check if this is the old OAuth-based schema (has user_id)
        has_user_id = 'user_id' in column_info
        has_url = 'url' in column_info

        if has_user_id and not has_url:
            # This is the old OAuth schema - need to migrate to new cookie-based schema
            logger.info("Detected old OAuth-based schema (has user_id, no url)")
            logger.info("Converting to cookie-based YouTube playlist schema...")

            # Check if there's any data
            cursor.execute("SELECT COUNT(*) FROM youtube_playlists")
            row_count = cursor.fetchone()[0]

            if row_count > 0:
                logger.warning(f"⚠️  Found {row_count} playlists in old schema - these will be DELETED during migration")
                response = input("Continue? (yes/no): ")
                if response.lower() != 'yes':
                    logger.info("Migration cancelled")
                    return 0

            # Drop old tables
            logger.info("Dropping old OAuth-based YouTube tables...")
            cursor.execute("DROP TABLE IF EXISTS youtube_playlist_items")
            logger.info("  ✓ Dropped youtube_playlist_items")

            cursor.execute("DROP TABLE IF EXISTS youtube_playlists")
            logger.info("  ✓ Dropped youtube_playlists")

            cursor.execute("DROP TABLE IF EXISTS youtube_users")
            logger.info("  ✓ Dropped youtube_users")

            cursor.execute("DROP TABLE IF EXISTS youtube_quota")
            logger.info("  ✓ Dropped youtube_quota")

            conn.commit()
            logger.info("✅ Successfully dropped old OAuth-based YouTube tables")
            logger.info("ℹ️  New tables will be created automatically when the app starts")

        elif has_user_id and has_url:
            logger.warning("Table has both user_id and url - this is unexpected!")
            logger.info("Dropping table to recreate with correct schema...")

            cursor.execute("DROP TABLE IF EXISTS youtube_playlist_items")
            cursor.execute("DROP TABLE IF EXISTS youtube_playlists")
            conn.commit()
            logger.info("✅ Dropped tables - they will be recreated on next startup")

        elif not has_url:
            logger.info("Table is missing url column - dropping and recreating...")
            cursor.execute("DROP TABLE IF EXISTS youtube_playlist_items")
            cursor.execute("DROP TABLE IF EXISTS youtube_playlists")
            conn.commit()
            logger.info("✅ Dropped tables - they will be recreated on next startup")

        else:
            logger.info("✅ Schema is already correct (has url, no user_id) - no migration needed")

        return 0

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    exit(main())
