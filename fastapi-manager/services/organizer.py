"""Torrent organizer service for sorting downloaded media."""

import logging
import os
import shutil
from pathlib import Path
from typing import Literal

from config import settings
from services.metadata import is_video_file, is_audio_file, VIDEO_EXTENSIONS, AUDIO_EXTENSIONS

logger = logging.getLogger(__name__)


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

    logger.warning(f"Destination already exists, resolving conflict: {dest_path}")

    # For files, insert number before extension
    if dest_path.suffix:
        base = dest_path.stem
        ext = dest_path.suffix
        parent = dest_path.parent
        counter = 1
        while True:
            new_path = parent / f"{base} ({counter}){ext}"
            if not new_path.exists():
                logger.info(f"Resolved conflict by renaming to: {new_path}")
                return new_path
            counter += 1

    # For directories, append number
    counter = 1
    while True:
        new_path = Path(f"{dest_path} ({counter})")
        if not new_path.exists():
            logger.info(f"Resolved conflict by renaming to: {new_path}")
            return new_path
        counter += 1


def _has_matching_folder(file_stem: str, all_items: list[Path]) -> bool:
    """Check if a file stem matches or significantly overlaps with any folder name."""
    MIN_NAME_LENGTH = 5
    OVERLAP_THRESHOLD = 0.8

    for item in all_items:
        if not item.is_dir():
            continue

        folder_name = item.name.lower()

        if file_stem == folder_name:
            return True

        if file_stem.startswith(folder_name) or folder_name.startswith(file_stem):
            min_len = min(len(file_stem), len(folder_name))
            if min_len > MIN_NAME_LENGTH:
                common_prefix_len = len(os.path.commonprefix([file_stem, folder_name]))
                if common_prefix_len >= min_len * OVERLAP_THRESHOLD:
                    return True

    return False


def is_companion_file(file_path: Path, all_items: list[Path], max_size_mb: float = 5.0) -> bool:
    """Check if a file is a small companion file that should be hidden.

    Companion files are small files (< max_size_mb) that share a name stem with
    a folder in the same directory. These are typically torrent metadata files
    (.nfo, .txt), magnet links, or sample files that clutter the organize view.

    Args:
        file_path: Path to the file to check
        all_items: List of all items in the directory
        max_size_mb: Maximum size in MB to consider as a companion file

    Returns:
        True if the file should be hidden as a companion file
    """
    if not file_path.is_file():
        return False

    try:
        size_bytes = file_path.stat().st_size
        max_size_bytes = max_size_mb * 1024 * 1024
        if size_bytes > max_size_bytes:
            return False
    except OSError:
        return False

    file_stem = file_path.stem.lower()
    return _has_matching_folder(file_stem, all_items)


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

    all_items = [item for item in path.iterdir() if not item.name.startswith('.')]

    items = []
    for item in sorted(all_items):
        if is_companion_file(item, all_items):
            continue

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

    logger.info(f"Starting move operation: {source_path} -> {media_type}")
    logger.debug(f"Metadata: {metadata}")

    if not source.exists():
        error_msg = f"Source not found: {source_path}"
        logger.error(error_msg)
        return {
            'success': False,
            'error': error_msg
        }

    result = {
        'success': True,
        'source': str(source),
        'destination': None,
        'files_moved': [],
        'files_skipped': [],
        'warnings': [],
        'error': None
    }

    try:
        if media_type == 'movie':
            dest_folder = generate_movie_path(
                metadata.get('title', source.stem),
                metadata.get('year')
            )
            original_dest = str(dest_folder)
            dest_folder = resolve_conflict(dest_folder)
            if str(dest_folder) != original_dest:
                result['warnings'].append(f"Destination was renamed to avoid conflict")

            dest_folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created destination folder: {dest_folder}")

            if source.is_file():
                # Move single file
                dest_file = dest_folder / source.name
                original_file = str(dest_file)
                dest_file = resolve_conflict(dest_file)
                if str(dest_file) != original_file:
                    result['warnings'].append(f"File renamed to avoid conflict: {dest_file.name}")

                logger.info(f"Moving file: {source} -> {dest_file}")
                shutil.move(str(source), str(dest_file))
                result['files_moved'].append(str(dest_file))
            else:
                # Move entire folder contents (preserves subtitles, images, etc.)
                all_files = list(source.rglob('*'))
                files_to_move = [f for f in all_files if f.is_file()]

                logger.info(f"Moving entire folder with {len(files_to_move)} files (preserving all companion files)")

                for f in files_to_move:
                    # Preserve directory structure for files in subdirectories
                    relative_path = f.relative_to(source)
                    dest_file = dest_folder / relative_path

                    # Create subdirectories if needed
                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    original_file = str(dest_file)
                    dest_file = resolve_conflict(dest_file)
                    if str(dest_file) != original_file:
                        result['warnings'].append(f"File renamed to avoid conflict: {dest_file.name}")

                    logger.info(f"Moving file: {relative_path}")
                    shutil.move(str(f), str(dest_file))
                    result['files_moved'].append(str(dest_file))

                # Clean up empty source folder
                cleanup_info = _remove_empty_dirs(source)
                if cleanup_info.get('dirs_removed'):
                    logger.info(f"Removed {len(cleanup_info['dirs_removed'])} empty directories during cleanup")

            result['destination'] = str(dest_folder)

        elif media_type == 'tv':
            title = metadata.get('title', source.stem)
            season = metadata.get('season')
            episode = metadata.get('episode')

            dest_folder = generate_tv_path(title, season)
            dest_folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created destination folder: {dest_folder}")

            if source.is_file():
                # Single episode file
                if season is not None and episode is not None:
                    new_name = generate_tv_filename(title, season, episode, source.suffix)
                else:
                    new_name = source.name
                dest_file = dest_folder / new_name
                original_file = str(dest_file)
                dest_file = resolve_conflict(dest_file)
                if str(dest_file) != original_file:
                    result['warnings'].append(f"File renamed to avoid conflict: {dest_file.name}")

                logger.info(f"Moving TV episode: {source} -> {dest_file}")
                shutil.move(str(source), str(dest_file))
                result['files_moved'].append(str(dest_file))
            else:
                # Folder with multiple episodes (season pack)
                from services.metadata import parse_filename

                all_files = list(source.rglob('*'))
                files_to_move = [f for f in all_files if f.is_file()]
                video_files = [f for f in files_to_move if is_video_file(str(f))]

                logger.info(f"Moving entire folder with {len(files_to_move)} files (preserving all companion files)")

                # Process video files with proper naming
                for f in video_files:
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
                    original_file = str(dest_file)
                    dest_file = resolve_conflict(dest_file)
                    if str(dest_file) != original_file:
                        result['warnings'].append(f"File renamed to avoid conflict: {dest_file.name}")

                    logger.info(f"Moving TV episode: {f.name} -> {dest_file}")
                    shutil.move(str(f), str(dest_file))
                    result['files_moved'].append(str(dest_file))

                # Move non-video files (subtitles, images, etc.) to the season folder
                non_video_files = [f for f in files_to_move if not is_video_file(str(f))]
                for f in non_video_files:
                    # Preserve relative path for companion files
                    relative_path = f.relative_to(source)
                    dest_file = dest_folder / relative_path

                    # Create subdirectories if needed
                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    original_file = str(dest_file)
                    dest_file = resolve_conflict(dest_file)
                    if str(dest_file) != original_file:
                        result['warnings'].append(f"File renamed to avoid conflict: {dest_file.name}")

                    logger.info(f"Moving companion file: {relative_path}")
                    shutil.move(str(f), str(dest_file))
                    result['files_moved'].append(str(dest_file))

                # Clean up empty source folder
                cleanup_info = _remove_empty_dirs(source)
                if cleanup_info.get('dirs_removed'):
                    logger.info(f"Removed {len(cleanup_info['dirs_removed'])} empty directories during cleanup")

            result['destination'] = str(generate_tv_path(title))

        elif media_type == 'music':
            artist = metadata.get('artist') or 'Unknown Artist'
            album = metadata.get('album')

            dest_folder = generate_music_path(artist, album)
            original_dest = str(dest_folder)
            dest_folder = resolve_conflict(dest_folder)
            if str(dest_folder) != original_dest:
                result['warnings'].append(f"Destination was renamed to avoid conflict")

            dest_folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created destination folder: {dest_folder}")

            if source.is_file():
                dest_file = dest_folder / source.name
                original_file = str(dest_file)
                dest_file = resolve_conflict(dest_file)
                if str(dest_file) != original_file:
                    result['warnings'].append(f"File renamed to avoid conflict: {dest_file.name}")

                logger.info(f"Moving music file: {source} -> {dest_file}")
                shutil.move(str(source), str(dest_file))
                result['files_moved'].append(str(dest_file))
            else:
                # Move entire album folder (preserves cover art, lyrics, etc.)
                all_files = list(source.rglob('*'))
                files_to_move = [f for f in all_files if f.is_file()]

                logger.info(f"Moving entire folder with {len(files_to_move)} files (preserving all companion files)")

                for f in files_to_move:
                    # Preserve directory structure for files in subdirectories
                    relative_path = f.relative_to(source)
                    dest_file = dest_folder / relative_path

                    # Create subdirectories if needed
                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    original_file = str(dest_file)
                    dest_file = resolve_conflict(dest_file)
                    if str(dest_file) != original_file:
                        result['warnings'].append(f"File renamed to avoid conflict: {dest_file.name}")

                    logger.info(f"Moving file: {relative_path}")
                    shutil.move(str(f), str(dest_file))
                    result['files_moved'].append(str(dest_file))

                # Clean up empty source folder
                cleanup_info = _remove_empty_dirs(source)
                if cleanup_info.get('dirs_removed'):
                    logger.info(f"Removed {len(cleanup_info['dirs_removed'])} empty directories during cleanup")

            result['destination'] = str(dest_folder)

        else:
            error_msg = f"Unknown media type: {media_type}"
            logger.error(error_msg)
            result['success'] = False
            result['error'] = error_msg

        if result['success']:
            logger.info(f"Move operation completed successfully: moved {len(result['files_moved'])} files to {result['destination']}")
            if result['warnings']:
                logger.warning(f"Warnings during move: {', '.join(result['warnings'])}")

    except Exception as e:
        error_msg = f"Error during move operation: {str(e)}"
        logger.exception(error_msg)
        result['success'] = False
        result['error'] = str(e)

    return result


def _remove_empty_dirs(path: Path) -> dict:
    """Recursively remove empty directories.

    Args:
        path: Directory path to clean up

    Returns:
        Dict with cleanup info (files_removed, dirs_removed)
    """
    cleanup_info = {
        'files_removed': [],
        'dirs_removed': []
    }

    if not path.is_dir():
        return cleanup_info

    try:
        # First, recursively clean up subdirectories
        for item in path.iterdir():
            if item.is_dir():
                subdir_info = _remove_empty_dirs(item)
                cleanup_info['files_removed'].extend(subdir_info['files_removed'])
                cleanup_info['dirs_removed'].extend(subdir_info['dirs_removed'])

        # Check if directory is now empty (or only contains hidden/small files)
        remaining = [f for f in path.iterdir() if not f.name.startswith('.')]
        if not remaining:
            # Remove hidden files first
            for f in path.iterdir():
                if f.is_file():
                    logger.debug(f"Removing leftover file during cleanup: {f}")
                    f.unlink()
                    cleanup_info['files_removed'].append(str(f))

            logger.info(f"Removing empty directory: {path}")
            path.rmdir()
            cleanup_info['dirs_removed'].append(str(path))
        elif remaining:
            # Log what's preventing cleanup
            remaining_files = [f for f in remaining if f.is_file()]
            remaining_dirs = [f for f in remaining if f.is_dir()]
            if remaining_files:
                logger.info(f"Cannot remove {path}: {len(remaining_files)} files still present ({', '.join(f.name for f in remaining_files[:3])}{'...' if len(remaining_files) > 3 else ''})")
            if remaining_dirs:
                logger.debug(f"Cannot remove {path}: {len(remaining_dirs)} non-empty subdirectories still present")

    except OSError as e:
        logger.warning(f"Could not clean up directory {path}: {e}")

    return cleanup_info


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
