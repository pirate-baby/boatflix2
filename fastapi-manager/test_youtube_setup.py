#!/usr/bin/env python3
"""Test script to verify YouTube cookie-based setup."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from database import init_db, SessionLocal
from models.db import YouTubeConfig, YouTubePlaylist, YouTubePlaylistItem

def test_database_setup():
    """Test that database tables are created correctly."""
    print("Initializing database...")
    init_db()

    print("Testing database tables...")

    with SessionLocal() as session:
        # Test YouTubeConfig table
        config = YouTubeConfig(
            cookies_uploaded=False,
        )
        session.add(config)
        session.commit()
        print("✓ YouTubeConfig table working")

        # Test YouTubePlaylist table
        playlist = YouTubePlaylist(
            id="test-playlist-id",
            url="https://www.youtube.com/playlist?list=PLtest",
            youtube_playlist_id="PLtest",
            title="Test Playlist",
            download_type="audio",
        )
        session.add(playlist)
        session.commit()
        print("✓ YouTubePlaylist table working")

        # Test YouTubePlaylistItem table
        item = YouTubePlaylistItem(
            playlist_id="test-playlist-id",
            youtube_video_id="test-video-id",
            title="Test Video",
            position=0,
            download_status="pending",
        )
        session.add(item)
        session.commit()
        print("✓ YouTubePlaylistItem table working")

        # Clean up test data
        session.delete(item)
        session.delete(playlist)
        session.delete(config)
        session.commit()
        print("✓ Test data cleaned up")

    print("\n✅ All database tests passed!")
    return True

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")

    try:
        from routers import youtube_simple
        print("✓ youtube_simple router imported")

        from services import youtube_extractor
        print("✓ youtube_extractor service imported")

        from services import youtube_sync_simple
        print("✓ youtube_sync_simple service imported")

        from models import youtube_simple as youtube_models
        print("✓ youtube_simple models imported")

        print("\n✅ All imports successful!")
        return True
    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=== YouTube Cookie-Based Setup Test ===\n")

    success = True

    if not test_imports():
        success = False

    print()

    if not test_database_setup():
        success = False

    if success:
        print("\n🎉 All tests passed! The cookie-based YouTube sync is ready to use.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
        sys.exit(1)
