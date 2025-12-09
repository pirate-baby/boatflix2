"""yt-dlp service for downloading media with Jellyfin folder structure."""

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse, unquote

from config import settings
from models.download import (
    MediaType,
    MovieMetadata,
    TVMetadata,
    MusicMetadata,
    CommercialMetadata,
    AnalyzeResponse,
)

logger = logging.getLogger(__name__)


class YtdlpService:
    """Service for yt-dlp operations with Jellyfin folder structure support."""

    def __init__(self, media_path: Optional[str] = None):
        self.media_path = Path(media_path or settings.MEDIA_BASE)

    async def analyze_url(self, url: str) -> AnalyzeResponse:
        """Analyze a URL and extract metadata for auto-detection.

        Args:
            url: URL to analyze

        Returns:
            AnalyzeResponse with detected media type and metadata
        """
        info = await self._extract_info(url)
        extraction_failed = info.get("_extraction_failed", False)

        # Build default response kwargs
        response_kwargs = {
            "url": url,
            "media_type": MediaType.MOVIE,
            "metadata": MovieMetadata(
                title=info.get("title", "Unknown Title"),
                year=None,
                description=None,
            ),
            "confidence": 0.0,
            "raw_title": info.get("title"),
            "thumbnail": None,
            "duration": None,
            "metadata_available": False,
            "extractor": info.get("extractor"),
            "extractor_error": info.get("_extraction_error"),
        }

        # Override with extracted data if available
        if not extraction_failed:
            media_type, metadata, confidence = self._detect_media_type(info)
            response_kwargs.update({
                "media_type": media_type,
                "metadata": metadata,
                "confidence": confidence,
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "metadata_available": True,
                "extractor": info.get("extractor") or info.get("extractor_key"),
                "extractor_error": None,
            })

        return AnalyzeResponse(**response_kwargs)

    def _detect_media_type(
        self, info: dict
    ) -> tuple[MediaType, MovieMetadata | TVMetadata | MusicMetadata, float]:
        """Detect media type from yt-dlp metadata.

        Priority:
        1. TV: has series, season_number, episode_number
        2. Music: has artist, album, track
        3. Movie: fallback

        Returns:
            Tuple of (media_type, metadata, confidence)
        """
        # Check for TV show indicators
        if self._has_tv_metadata(info):
            return self._extract_tv_metadata(info)

        # Check for music indicators
        if self._has_music_metadata(info):
            return self._extract_music_metadata(info)

        # Fallback to movie
        return self._extract_movie_metadata(info)

    def _has_tv_metadata(self, info: dict) -> bool:
        """Check if info contains TV show metadata."""
        return bool(
            info.get("series")
            or (info.get("season_number") and info.get("episode_number"))
            or info.get("episode")
        )

    def _has_music_metadata(self, info: dict) -> bool:
        """Check if info contains music metadata."""
        return bool(
            (info.get("artist") or info.get("creator"))
            and (info.get("album") or info.get("track"))
        )

    def _extract_tv_metadata(
        self, info: dict
    ) -> tuple[MediaType, TVMetadata, float]:
        """Extract TV show metadata from yt-dlp info."""
        series = info.get("series") or info.get("playlist_title") or ""
        season = info.get("season_number") or 1
        episode = info.get("episode_number") or 1
        episode_title = info.get("episode") or info.get("title")

        # Try to extract year from upload_date or release_date
        year = self._extract_year(info)

        # Calculate confidence
        confidence = 0.5
        if info.get("series"):
            confidence += 0.3
        if info.get("season_number") and info.get("episode_number"):
            confidence += 0.2

        # If series is empty, try to parse from title
        if not series and info.get("title"):
            parsed = self._parse_tv_from_title(info["title"])
            if parsed:
                series = parsed.get("series", series)
                season = parsed.get("season", season)
                episode = parsed.get("episode", episode)
                confidence = max(0.4, confidence - 0.2)

        return (
            MediaType.TV,
            TVMetadata(
                show=series or info.get("title", "Unknown Show"),
                year=year,
                season=season,
                episode=episode,
                episode_title=episode_title,
            ),
            min(confidence, 1.0),
        )

    def _extract_music_metadata(
        self, info: dict
    ) -> tuple[MediaType, MusicMetadata, float]:
        """Extract music metadata from yt-dlp info."""
        artist = info.get("artist") or info.get("creator") or info.get("uploader")
        album = info.get("album")
        track = info.get("track") or info.get("title")
        track_number = info.get("track_number")
        release_year = self._extract_year(info)

        confidence = 0.5
        if info.get("artist"):
            confidence += 0.2
        if info.get("album"):
            confidence += 0.2
        if info.get("track"):
            confidence += 0.1

        return (
            MediaType.MUSIC,
            MusicMetadata(
                artist=artist or "Unknown Artist",
                album=album,
                track=track or "Unknown Track",
                track_number=track_number,
                release_year=release_year,
            ),
            min(confidence, 1.0),
        )

    def _extract_movie_metadata(
        self, info: dict
    ) -> tuple[MediaType, MovieMetadata, float]:
        """Extract movie metadata from yt-dlp info."""
        title = info.get("title", "Unknown Title")
        year = self._extract_year(info)
        description = info.get("description")

        # Default confidence for movies (fallback type)
        confidence = 0.6

        return (
            MediaType.MOVIE,
            MovieMetadata(title=title, year=year, description=description),
            confidence,
        )

    def _extract_year(self, info: dict) -> Optional[int]:
        """Extract year from various date fields."""
        # Try release_year first
        if info.get("release_year"):
            return int(info["release_year"])

        # Try upload_date (format: YYYYMMDD)
        upload_date = info.get("upload_date")
        if upload_date and len(upload_date) >= 4:
            try:
                return int(upload_date[:4])
            except ValueError:
                pass

        # Try release_date
        release_date = info.get("release_date")
        if release_date and len(release_date) >= 4:
            try:
                return int(release_date[:4])
            except ValueError:
                pass

        return None

    def _parse_tv_from_title(self, title: str) -> Optional[dict]:
        """Try to parse TV show info from title (e.g., 'Show Name S01E05')."""
        patterns = [
            r"(.+?)\s*[Ss](\d+)[Ee](\d+)",  # Show S01E05
            r"(.+?)\s*(\d+)x(\d+)",  # Show 1x05
            r"(.+?)\s*Season\s*(\d+)\s*Episode\s*(\d+)",  # Show Season 1 Episode 5
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return {
                    "series": match.group(1).strip(),
                    "season": int(match.group(2)),
                    "episode": int(match.group(3)),
                }

        return None

    async def _extract_info(self, url: str) -> dict:
        """Run yt-dlp --dump-json to extract metadata.

        Args:
            url: URL to extract info from

        Returns:
            Parsed JSON metadata from yt-dlp
        """
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-warnings",
            url,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.warning(f"yt-dlp info extraction failed, attempting fallback: {error_msg}")
            # Return fallback info instead of raising - graceful degradation
            return self._create_fallback_info(url, error_msg)

        try:
            info = json.loads(stdout.decode())
            info["_extraction_failed"] = False
            return info
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse yt-dlp JSON output, using fallback: {e}")
            return self._create_fallback_info(url, f"JSON parse error: {e}")

    def _create_fallback_info(self, url: str, error_msg: str) -> dict:
        """Create minimal fallback metadata when yt-dlp extraction fails.

        This allows downloads to proceed with user-supplied metadata.
        """
        # Try to extract a reasonable title from the URL
        title = self._extract_title_from_url(url)

        return {
            "_extraction_failed": True,
            "_extraction_error": error_msg,
            "title": title,
            "webpage_url": url,
            "extractor": self._guess_extractor_from_url(url),
        }

    def _extract_title_from_url(self, url: str) -> str:
        """Try to extract a meaningful title from a URL."""
        parsed = urlparse(url)

        # Try path components
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts:
            # Use the last meaningful path component
            last_part = unquote(path_parts[-1])
            # Remove common extensions and clean up
            for ext in [".html", ".htm", ".php", ".aspx"]:
                if last_part.lower().endswith(ext):
                    last_part = last_part[: -len(ext)]
            # Replace dashes/underscores with spaces
            title = last_part.replace("-", " ").replace("_", " ")
            if title and len(title) > 2:
                return title.title()

        # Fallback to domain
        return parsed.netloc or "Unknown Title"

    def _guess_extractor_from_url(self, url: str) -> str:
        """Guess the extractor name from URL domain."""
        # Map keywords to extractor names - matches if keyword appears anywhere in host
        keyword_map = {
            "youtube": "youtube",
            "youtu.be": "youtube",
            "vimeo": "vimeo",
            "dailymotion": "dailymotion",
            "twitch": "twitch",
            "pluto": "pluto",
            "tubi": "tubi",
            "peacock": "peacock",
            "cbs": "cbs",
            "nbc": "nbc",
            "abc": "abc",
            "hulu": "hulu",
            "crunchyroll": "crunchyroll",
            "twitter": "twitter",
            "x.com": "twitter",
            "instagram": "instagram",
            "facebook": "facebook",
            "tiktok": "tiktok",
            "reddit": "reddit",
        }

        parsed = urlparse(url)
        host = parsed.netloc.lower()

        for keyword, extractor in keyword_map.items():
            if keyword in host:
                return extractor

        return "generic"

    def get_output_template(
        self,
        media_type: MediaType,
        metadata: MovieMetadata | TVMetadata | MusicMetadata | CommercialMetadata,
    ) -> str:
        """Generate yt-dlp output template for Jellyfin folder structure.

        Args:
            media_type: Type of media
            metadata: Metadata for the download

        Returns:
            yt-dlp output template string
        """
        if media_type == MediaType.MOVIE:
            assert isinstance(metadata, MovieMetadata)
            title = self._sanitize_filename(metadata.title)
            year = metadata.year or datetime.now().year
            folder = f"{title} ({year})"
            return str(
                self.media_path / "Movies" / folder / f"{folder}.%(ext)s"
            )

        elif media_type == MediaType.TV:
            assert isinstance(metadata, TVMetadata)
            show = self._sanitize_filename(metadata.show)
            year = f" ({metadata.year})" if metadata.year else ""
            season = f"Season {metadata.season:02d}"
            episode_name = f"{show} S{metadata.season:02d}E{metadata.episode:02d}"
            return str(
                self.media_path
                / "Shows"
                / f"{show}{year}"
                / season
                / f"{episode_name}.%(ext)s"
            )

        elif media_type == MediaType.MUSIC:
            assert isinstance(metadata, MusicMetadata)
            artist = self._sanitize_filename(metadata.artist)
            album = self._sanitize_filename(metadata.album or "Singles")
            year = f" ({metadata.release_year})" if metadata.release_year else ""
            track_num = f"{metadata.track_number:02d} - " if metadata.track_number else ""
            track = self._sanitize_filename(metadata.track)
            return str(
                self.media_path
                / "Music"
                / artist
                / f"{album}{year}"
                / f"{track_num}{track}.%(ext)s"
            )

        else:  # COMMERCIAL
            assert isinstance(metadata, CommercialMetadata)
            title = self._sanitize_filename(metadata.title)
            year = metadata.year or datetime.now().year
            filename = f"{title} ({year})"
            return str(
                self.media_path / "Commercials" / f"{filename}.%(ext)s"
            )

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use in filenames."""
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "")
        # Replace multiple spaces with single space
        name = " ".join(name.split())
        # Limit length
        return name[:200].strip()

    async def download(
        self,
        url: str,
        media_type: MediaType,
        metadata: MovieMetadata | TVMetadata | MusicMetadata | CommercialMetadata,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> str:
        """Download media using yt-dlp to the correct Jellyfin folder.

        Args:
            url: URL to download
            media_type: Type of media
            metadata: Metadata for folder/file naming
            progress_callback: Optional callback for progress updates (percent, status)

        Returns:
            Path to the downloaded file
        """
        output_template = self.get_output_template(media_type, metadata)

        # Ensure output directory exists
        output_dir = Path(output_template).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "yt-dlp",
            "--no-warnings",
            "--newline",  # Output progress on new lines
            "--progress",
            "-o",
            output_template,
            url,
        ]

        # Add format options based on media type
        if media_type == MediaType.MUSIC:
            cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
        else:
            cmd.extend([
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
            ])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        downloaded_file = None
        current_progress = 0.0

        while True:
            line = await process.stdout.readline()
            if not line:
                break

            line_text = line.decode().strip()

            # Parse progress from yt-dlp output
            if "[download]" in line_text:
                progress_match = re.search(r"(\d+\.?\d*)%", line_text)
                if progress_match:
                    current_progress = float(progress_match.group(1))
                    if progress_callback:
                        progress_callback(current_progress, "Downloading")

                # Capture the destination file
                dest_match = re.search(r"Destination:\s*(.+)", line_text)
                if dest_match:
                    downloaded_file = dest_match.group(1)

                # Check for merge destination
                merge_match = re.search(r"Merging formats into \"(.+)\"", line_text)
                if merge_match:
                    downloaded_file = merge_match.group(1)

            elif "[Merger]" in line_text or "[ExtractAudio]" in line_text:
                if progress_callback:
                    progress_callback(99.0, "Processing")

        await process.wait()

        if process.returncode != 0:
            raise RuntimeError(f"Download failed with return code {process.returncode}")

        if progress_callback:
            progress_callback(100.0, "Completed")

        # If we didn't capture the file, try to find it
        if not downloaded_file:
            # Look for recently created files in the output directory
            files = list(output_dir.glob("*"))
            if files:
                downloaded_file = str(max(files, key=lambda f: f.stat().st_mtime))

        return downloaded_file or str(output_dir)


# Singleton instance
ytdlp_service = YtdlpService()
