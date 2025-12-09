"""Torrent organizer service for sorting downloaded media."""

import os
import shutil
from pathlib import Path
from typing import Literal

from config import settings
from services.metadata import is_video_file, is_audio_file, VIDEO_EXTENSIONS, AUDIO_EXTENSIONS


def get_jellyfin_library_paths() -> dict[str, Path]:
    """Get Jellyfin library paths for different media types."""
    media_base = Path(settings.MEDIA_BASE)
    return {
        'movie': media_base / 'Movies',
        'tv': media_base / 'Shows',
        'music': media_base / 'Music'
    }


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename/folder name.

    Args:
        name: Raw name to sanitize

    Returns:
        Sanitized name safe for filesystem use
    """
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '')
    # Remove leading/trailing whitespace and periods
    name = name.strip().strip('.')
    # Replace multiple spaces with single space
    while '  ' in name:
        name = name.replace('  ', ' ')
    return name


def generate_movie_path(title: str, year: int | None = None) -> Path:
    """Generate destination path for a movie.

    Args:
        title: Movie title
        year: Release year (optional)

    Returns:
        Destination folder path
    """
    libraries = get_jellyfin_library_paths()
    folder_name = sanitize_filename(title)
    if year:
        folder_name = f"{folder_name} ({year})"
    return libraries['movie'] / folder_name


def generate_tv_path(title: str, season: int | None = None) -> Path:
    """Generate destination path for a TV show.

    Args:
        title: Show title
        season: Season number (optional)

    Returns:
        Destination folder path
    """
    libraries = get_jellyfin_library_paths()
    show_folder = sanitize_filename(title)
    base_path = libraries['tv'] / show_folder
    if season is not None:
        return base_path / f"Season {season:02d}"
    return base_path


def generate_tv_filename(title: str, season: int, episode: int, extension: str) -> str:
    """Generate filename for a TV episode following Jellyfin naming conventions.

    Args:
        title: Show title
        season: Season number
        episode: Episode number
        extension: File extension (including dot)

    Returns:
        Formatted filename
    """
    clean_title = sanitize_filename(title)
    return f"{clean_title} - S{season:02d}E{episode:02d}{extension}"


def generate_music_path(artist: str, album: str | None = None) -> Path:
    """Generate destination path for music.

    Args:
        artist: Artist name
        album: Album name (optional)

    Returns:
        Destination folder path
    """
    libraries = get_jellyfin_library_paths()
    artist_folder = sanitize_filename(artist) if artist else "Unknown Artist"
    base_path = libraries['music'] / artist_folder
    if album:
        return base_path / sanitize_filename(album)
    return base_path


def resolve_conflict(dest_path: Path) -> Path:
    """Resolve naming conflicts by appending a number.

    Args:
        dest_path: Original destination path

    Returns:
        Available path (original or with number suffix)
    """
    if not dest_path.exists():
        return dest_path

    # For files, insert number before extension
    if dest_path.suffix:
        base = dest_path.stem
        ext = dest_path.suffix
        parent = dest_path.parent
        counter = 1
        while True:
            new_path = parent / f"{base} ({counter}){ext}"
            if not new_path.exists():
                return new_path
            counter += 1

    # For directories, append number
    counter = 1
    while True:
        new_path = Path(f"{dest_path} ({counter})")
        if not new_path.exists():
            return new_path
        counter += 1


async def scan_downloads(downloads_path: str | None = None) -> list[dict]:
    """Scan downloads directory for files to organize.

    Args:
        downloads_path: Path to downloads directory (uses config default if None)

    Returns:
        List of items with basic info (not analyzed yet)
    """
    path = Path(downloads_path or f"{settings.MEDIA_BASE}/Downloads")

    if not path.exists():
        return []

    items = []
    for item in sorted(path.iterdir()):
        # Skip hidden files/folders
        if item.name.startswith('.'):
            continue

        # Determine basic type from extension or directory content
        item_type = 'unknown'
        size = 0

        if item.is_file():
            size = item.stat().st_size
            if is_video_file(str(item)):
                item_type = 'video'
            elif is_audio_file(str(item)):
                item_type = 'audio'
        elif item.is_dir():
            item_type = 'folder'
            # Calculate total size
            for f in item.rglob('*'):
                if f.is_file():
                    size += f.stat().st_size

        items.append({
            'path': str(item),
            'name': item.name,
            'type': item_type,
            'is_directory': item.is_dir(),
            'size': size,
            'size_formatted': format_size(size)
        })

    return items


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


async def move_item(
    source_path: str,
    media_type: Literal['movie', 'tv', 'music'],
    metadata: dict
) -> dict:
    """Move a file/folder to the appropriate library location.

    Args:
        source_path: Path to source file/folder
        media_type: Type of media ('movie', 'tv', 'music')
        metadata: Metadata dict with title, year, season, episode, artist, album

    Returns:
        Result dict with status, destination, and any errors
    """
    source = Path(source_path)

    if not source.exists():
        return {
            'success': False,
            'error': f"Source not found: {source_path}"
        }

    result = {
        'success': True,
        'source': str(source),
        'destination': None,
        'files_moved': [],
        'error': None
    }

    try:
        if media_type == 'movie':
            dest_folder = generate_movie_path(
                metadata.get('title', source.stem),
                metadata.get('year')
            )
            dest_folder = resolve_conflict(dest_folder)
            dest_folder.mkdir(parents=True, exist_ok=True)

            if source.is_file():
                # Move single file
                dest_file = dest_folder / source.name
                dest_file = resolve_conflict(dest_file)
                shutil.move(str(source), str(dest_file))
                result['files_moved'].append(str(dest_file))
            else:
                # Move all video files from folder
                for f in source.rglob('*'):
                    if f.is_file() and is_video_file(str(f)):
                        dest_file = dest_folder / f.name
                        dest_file = resolve_conflict(dest_file)
                        shutil.move(str(f), str(dest_file))
                        result['files_moved'].append(str(dest_file))

                # Clean up empty source folder
                _remove_empty_dirs(source)

            result['destination'] = str(dest_folder)

        elif media_type == 'tv':
            title = metadata.get('title', source.stem)
            season = metadata.get('season')
            episode = metadata.get('episode')

            dest_folder = generate_tv_path(title, season)
            dest_folder.mkdir(parents=True, exist_ok=True)

            if source.is_file():
                # Single episode file
                if season is not None and episode is not None:
                    new_name = generate_tv_filename(title, season, episode, source.suffix)
                else:
                    new_name = source.name
                dest_file = dest_folder / new_name
                dest_file = resolve_conflict(dest_file)
                shutil.move(str(source), str(dest_file))
                result['files_moved'].append(str(dest_file))
            else:
                # Folder with multiple episodes (season pack)
                from services.metadata import parse_filename
                for f in source.rglob('*'):
                    if f.is_file() and is_video_file(str(f)):
                        parsed = parse_filename(f.name)
                        ep_season = parsed.get('season', season)
                        ep_episode = parsed.get('episode')

                        # Determine correct season folder
                        ep_dest_folder = generate_tv_path(title, ep_season)
                        ep_dest_folder.mkdir(parents=True, exist_ok=True)

                        if ep_season is not None and ep_episode is not None:
                            new_name = generate_tv_filename(title, ep_season, ep_episode, f.suffix)
                        else:
                            new_name = f.name
                        dest_file = ep_dest_folder / new_name
                        dest_file = resolve_conflict(dest_file)
                        shutil.move(str(f), str(dest_file))
                        result['files_moved'].append(str(dest_file))

                # Clean up empty source folder
                _remove_empty_dirs(source)

            result['destination'] = str(generate_tv_path(title))

        elif media_type == 'music':
            artist = metadata.get('artist') or 'Unknown Artist'
            album = metadata.get('album')

            dest_folder = generate_music_path(artist, album)
            dest_folder.mkdir(parents=True, exist_ok=True)

            if source.is_file():
                dest_file = dest_folder / source.name
                dest_file = resolve_conflict(dest_file)
                shutil.move(str(source), str(dest_file))
                result['files_moved'].append(str(dest_file))
            else:
                # Move all audio files from folder
                for f in source.rglob('*'):
                    if f.is_file() and is_audio_file(str(f)):
                        dest_file = dest_folder / f.name
                        dest_file = resolve_conflict(dest_file)
                        shutil.move(str(f), str(dest_file))
                        result['files_moved'].append(str(dest_file))

                # Clean up empty source folder
                _remove_empty_dirs(source)

            result['destination'] = str(dest_folder)

        else:
            result['success'] = False
            result['error'] = f"Unknown media type: {media_type}"

    except Exception as e:
        result['success'] = False
        result['error'] = str(e)

    return result


def _remove_empty_dirs(path: Path) -> None:
    """Recursively remove empty directories.

    Args:
        path: Directory path to clean up
    """
    if not path.is_dir():
        return

    # First, recursively clean up subdirectories
    for item in path.iterdir():
        if item.is_dir():
            _remove_empty_dirs(item)

    # Check if directory is now empty (or only contains hidden files)
    remaining = [f for f in path.iterdir() if not f.name.startswith('.')]
    if not remaining:
        try:
            # Remove hidden files first
            for f in path.iterdir():
                if f.is_file():
                    f.unlink()
            path.rmdir()
        except OSError:
            pass


def preview_destination(
    source_path: str,
    media_type: Literal['movie', 'tv', 'music'],
    metadata: dict
) -> str:
    """Preview the destination path without actually moving.

    Args:
        source_path: Path to source file/folder
        media_type: Type of media
        metadata: Metadata dict

    Returns:
        Formatted destination path
    """
    source = Path(source_path)

    if media_type == 'movie':
        dest_folder = generate_movie_path(
            metadata.get('title', source.stem),
            metadata.get('year')
        )
        if source.is_file():
            return str(dest_folder / source.name)
        return str(dest_folder)

    elif media_type == 'tv':
        title = metadata.get('title', source.stem)
        season = metadata.get('season')
        episode = metadata.get('episode')
        dest_folder = generate_tv_path(title, season)

        if source.is_file() and season is not None and episode is not None:
            new_name = generate_tv_filename(title, season, episode, source.suffix)
            return str(dest_folder / new_name)
        return str(dest_folder)

    elif media_type == 'music':
        artist = metadata.get('artist') or 'Unknown Artist'
        album = metadata.get('album')
        return str(generate_music_path(artist, album))

    return str(source)
