"""Shared metadata detection utilities."""

import hashlib
import time
from pathlib import Path
from typing import Any

import guessit
import tmdbsimple as tmdb
from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC

from config import settings

# Configure TMDB API
if settings.TMDB_API_KEY:
    tmdb.API_KEY = settings.TMDB_API_KEY

# Simple in-memory cache for TMDB results
_tmdb_cache: dict[str, tuple[float, Any]] = {}
CACHE_TTL = 3600  # 1 hour

# Video file extensions
VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.m2ts'}
# Audio file extensions
AUDIO_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wav', '.wma', '.alac'}


def _get_cache_key(title: str, year: int | None, media_type: str) -> str:
    """Generate cache key for TMDB lookups."""
    return hashlib.md5(f"{title}:{year}:{media_type}".encode()).hexdigest()


def _get_from_cache(key: str) -> Any | None:
    """Get value from cache if not expired."""
    if key in _tmdb_cache:
        timestamp, value = _tmdb_cache[key]
        if time.time() - timestamp < CACHE_TTL:
            return value
        del _tmdb_cache[key]
    return None


def _set_cache(key: str, value: Any) -> None:
    """Set value in cache."""
    _tmdb_cache[key] = (time.time(), value)


def get_file_extension(file_path: str) -> str:
    """Get lowercase file extension."""
    return Path(file_path).suffix.lower()


def is_video_file(file_path: str) -> bool:
    """Check if file is a video file."""
    return get_file_extension(file_path) in VIDEO_EXTENSIONS


def is_audio_file(file_path: str) -> bool:
    """Check if file is an audio file."""
    return get_file_extension(file_path) in AUDIO_EXTENSIONS


def detect_media_type(file_path: str) -> str:
    """Detect if file is a movie, TV show, or music.

    Args:
        file_path: Path to media file

    Returns:
        Media type: 'movie', 'tv', 'music', or 'unknown'
    """
    path = Path(file_path)

    # Check if it's a directory (could be a season pack or album)
    if path.is_dir():
        # Look at files inside
        video_count = 0
        audio_count = 0
        for item in path.rglob('*'):
            if item.is_file():
                if is_video_file(str(item)):
                    video_count += 1
                elif is_audio_file(str(item)):
                    audio_count += 1

        if audio_count > video_count and audio_count > 0:
            return 'music'
        elif video_count > 0:
            # Parse the folder name to determine type
            parsed = parse_filename(path.name)
            return parsed.get('type', 'movie')
        return 'unknown'

    # Check by extension first
    if is_audio_file(file_path):
        return 'music'

    if is_video_file(file_path):
        # Use guessit to determine if it's a movie or TV show
        parsed = parse_filename(path.name)
        guessit_type = parsed.get('type', 'movie')

        if guessit_type == 'episode':
            return 'tv'
        return 'movie'

    return 'unknown'


def parse_filename(filename: str) -> dict:
    """Parse media filename to extract metadata.

    Args:
        filename: Media filename to parse

    Returns:
        Parsed metadata (title, year, season, episode, etc.)
    """
    try:
        result = guessit.guessit(filename)
        # Convert MatchesDict to regular dict
        return dict(result)
    except Exception:
        return {'title': Path(filename).stem, 'type': 'unknown'}


def calculate_confidence(parsed: dict, media_type: str) -> str:
    """Calculate confidence level based on parsed metadata.

    Args:
        parsed: Parsed metadata from guessit
        media_type: Detected media type

    Returns:
        Confidence level: 'high', 'medium', or 'low'
    """
    score = 0

    # Title is essential
    if parsed.get('title'):
        score += 2

    if media_type == 'tv':
        if parsed.get('season') is not None:
            score += 2
        if parsed.get('episode') is not None:
            score += 2
    elif media_type == 'movie':
        if parsed.get('year'):
            score += 2
        # Source and quality info add confidence
        if parsed.get('source'):
            score += 1
        if parsed.get('screen_size'):
            score += 1

    if score >= 5:
        return 'high'
    elif score >= 3:
        return 'medium'
    return 'low'


async def lookup_tmdb(title: str, year: int | None = None, media_type: str = "movie") -> list[dict]:
    """Look up media on TMDB.

    Args:
        title: Media title
        year: Release year (optional)
        media_type: 'movie' or 'tv'

    Returns:
        List of TMDB matches with metadata
    """
    if not settings.TMDB_API_KEY:
        return []

    # Check cache
    cache_key = _get_cache_key(title, year, media_type)
    cached = _get_from_cache(cache_key)
    if cached is not None:
        return cached

    try:
        search = tmdb.Search()
        results = []

        if media_type == 'tv':
            if year:
                response = search.tv(query=title, first_air_date_year=year)
            else:
                response = search.tv(query=title)

            for item in response.get('results', [])[:5]:
                results.append({
                    'tmdb_id': item['id'],
                    'title': item['name'],
                    'original_title': item.get('original_name'),
                    'year': item.get('first_air_date', '')[:4] if item.get('first_air_date') else None,
                    'overview': item.get('overview', ''),
                    'poster_path': f"https://image.tmdb.org/t/p/w200{item['poster_path']}" if item.get('poster_path') else None,
                    'vote_average': item.get('vote_average', 0),
                    'media_type': 'tv'
                })
        else:
            if year:
                response = search.movie(query=title, year=year)
            else:
                response = search.movie(query=title)

            for item in response.get('results', [])[:5]:
                results.append({
                    'tmdb_id': item['id'],
                    'title': item['title'],
                    'original_title': item.get('original_title'),
                    'year': item.get('release_date', '')[:4] if item.get('release_date') else None,
                    'overview': item.get('overview', ''),
                    'poster_path': f"https://image.tmdb.org/t/p/w200{item['poster_path']}" if item.get('poster_path') else None,
                    'vote_average': item.get('vote_average', 0),
                    'media_type': 'movie'
                })

        # Cache results
        _set_cache(cache_key, results)
        return results

    except Exception as e:
        print(f"TMDB lookup error: {e}")
        return []


def extract_audio_metadata(file_path: str) -> dict:
    """Extract metadata from audio file.

    Args:
        file_path: Path to audio file

    Returns:
        Audio metadata (artist, album, title, track, etc.)
    """
    metadata = {
        'artist': None,
        'album': None,
        'title': None,
        'track': None,
        'year': None,
        'genre': None
    }

    try:
        audio = MutagenFile(file_path, easy=True)

        if audio is None:
            # Try with EasyID3 for MP3 files
            if file_path.lower().endswith('.mp3'):
                try:
                    audio = EasyID3(file_path)
                except Exception:
                    pass

        if audio:
            # Extract common tags
            if 'artist' in audio:
                metadata['artist'] = audio['artist'][0] if audio['artist'] else None
            if 'album' in audio:
                metadata['album'] = audio['album'][0] if audio['album'] else None
            if 'title' in audio:
                metadata['title'] = audio['title'][0] if audio['title'] else None
            if 'tracknumber' in audio:
                track = audio['tracknumber'][0] if audio['tracknumber'] else None
                if track:
                    # Handle "1/12" format
                    metadata['track'] = track.split('/')[0]
            if 'date' in audio:
                date = audio['date'][0] if audio['date'] else None
                if date:
                    metadata['year'] = date[:4]
            if 'genre' in audio:
                metadata['genre'] = audio['genre'][0] if audio['genre'] else None

    except Exception as e:
        print(f"Error extracting audio metadata: {e}")

    return metadata


async def analyze_item(path: str) -> dict:
    """Analyze a file or folder and return detected metadata.

    Args:
        path: Path to file or folder to analyze

    Returns:
        Analysis result with media_type, metadata, confidence, and tmdb_matches
    """
    item_path = Path(path)

    if not item_path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    result = {
        'path': str(item_path),
        'name': item_path.name,
        'is_directory': item_path.is_dir(),
        'media_type': 'unknown',
        'metadata': {},
        'confidence': 'low',
        'tmdb_matches': [],
        'files': []
    }

    # Detect media type
    media_type = detect_media_type(path)
    result['media_type'] = media_type

    if media_type == 'music':
        # Handle music files/folders
        if item_path.is_dir():
            # Scan directory for audio files
            audio_files = []
            for f in item_path.rglob('*'):
                if f.is_file() and is_audio_file(str(f)):
                    audio_meta = extract_audio_metadata(str(f))
                    audio_files.append({
                        'path': str(f),
                        'name': f.name,
                        'metadata': audio_meta
                    })
            result['files'] = audio_files

            # Try to determine album metadata from files
            if audio_files:
                # Use first file with metadata as reference
                for af in audio_files:
                    if af['metadata'].get('artist') and af['metadata'].get('album'):
                        result['metadata'] = {
                            'artist': af['metadata']['artist'],
                            'album': af['metadata']['album'],
                            'year': af['metadata'].get('year')
                        }
                        break

                if not result['metadata'].get('artist'):
                    # Fall back to folder name parsing
                    result['metadata'] = {'artist': None, 'album': item_path.name}
        else:
            # Single audio file
            audio_meta = extract_audio_metadata(path)
            result['metadata'] = audio_meta
            if audio_meta.get('artist') and audio_meta.get('title'):
                result['confidence'] = 'high'
            elif audio_meta.get('artist') or audio_meta.get('album'):
                result['confidence'] = 'medium'

    elif media_type in ('movie', 'tv'):
        # Handle video files/folders
        name_to_parse = item_path.name

        if item_path.is_dir():
            # Find video files in directory
            video_files = []
            for f in item_path.rglob('*'):
                if f.is_file() and is_video_file(str(f)):
                    parsed = parse_filename(f.name)
                    video_files.append({
                        'path': str(f),
                        'name': f.name,
                        'metadata': parsed
                    })
            result['files'] = sorted(video_files, key=lambda x: x['name'])

            # Check if it's a season pack
            episodes_found = []
            for vf in video_files:
                if vf['metadata'].get('episode') is not None:
                    episodes_found.append(vf['metadata'].get('episode'))

            if len(episodes_found) > 1:
                result['is_season_pack'] = True

        # Parse the main name
        parsed = parse_filename(name_to_parse)
        result['metadata'] = {
            'title': parsed.get('title'),
            'year': parsed.get('year'),
            'season': parsed.get('season'),
            'episode': parsed.get('episode'),
            'screen_size': parsed.get('screen_size'),
            'source': parsed.get('source'),
            'video_codec': parsed.get('video_codec'),
            'audio_codec': parsed.get('audio_codec'),
            'release_group': parsed.get('release_group')
        }

        # Calculate confidence
        result['confidence'] = calculate_confidence(parsed, media_type)

        # Look up on TMDB if we have a title
        if parsed.get('title'):
            tmdb_type = 'tv' if media_type == 'tv' else 'movie'
            result['tmdb_matches'] = await lookup_tmdb(
                parsed['title'],
                parsed.get('year'),
                tmdb_type
            )

    return result
