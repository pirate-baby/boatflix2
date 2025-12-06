"""Shared metadata detection utilities."""

from pathlib import Path


def detect_media_type(file_path: str) -> str:
    """Detect if file is a movie, TV show, or music.

    Args:
        file_path: Path to media file

    Returns:
        Media type: 'movie', 'tv', 'music', or 'unknown'
    """
    # TODO: Implement media type detection using guessit
    pass


def parse_filename(filename: str) -> dict:
    """Parse media filename to extract metadata.

    Args:
        filename: Media filename to parse

    Returns:
        Parsed metadata (title, year, season, episode, etc.)
    """
    # TODO: Implement filename parsing using guessit
    pass


async def lookup_tmdb(title: str, year: int | None = None, media_type: str = "movie") -> dict | None:
    """Look up media on TMDB.

    Args:
        title: Media title
        year: Release year (optional)
        media_type: 'movie' or 'tv'

    Returns:
        TMDB metadata or None if not found
    """
    # TODO: Implement TMDB lookup using tmdbsimple
    pass


def extract_audio_metadata(file_path: str) -> dict:
    """Extract metadata from audio file.

    Args:
        file_path: Path to audio file

    Returns:
        Audio metadata (artist, album, title, etc.)
    """
    # TODO: Implement audio metadata extraction using mutagen
    pass
