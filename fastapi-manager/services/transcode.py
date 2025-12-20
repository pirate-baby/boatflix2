"""Transcode service for converting videos to Chromium-compatible formats.

Converts videos to H.264/AAC in MP4 container for direct playback in
Chromium-based browsers without Jellyfin transcoding.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

DATA_DIR = Path("/app/data")
TRANSCODE_HISTORY_FILE = DATA_DIR / "transcode_history.json"
TRANSCODE_LOG_FILE = DATA_DIR / "transcode.log"

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".m2ts"}

# Chromium-compatible codecs
COMPATIBLE_VIDEO_CODECS = {"h264", "avc1", "avc"}
COMPATIBLE_AUDIO_CODECS = {"aac", "mp3", "opus", "vorbis", "flac"}

# H.264 profiles and levels that work well in browsers
MAX_H264_LEVEL = 41  # Level 4.1
COMPATIBLE_H264_PROFILES = {"main", "high", "baseline", "constrained baseline"}


def _ensure_data_dir() -> None:
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_transcode_history() -> list[dict]:
    """Load transcoding history from JSON file."""
    _ensure_data_dir()
    if TRANSCODE_HISTORY_FILE.exists():
        try:
            return json.loads(TRANSCODE_HISTORY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_transcode_history(history: list[dict]) -> None:
    """Save transcoding history to JSON file."""
    _ensure_data_dir()
    history = history[-500:]  # Keep more history for transcoding
    TRANSCODE_HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str))


def _append_log(message: str) -> None:
    """Append message to transcoding log file."""
    _ensure_data_dir()
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(TRANSCODE_LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def _get_transcode_marker_path(video_path: Path) -> Path:
    """Get the marker file path for a transcoded video."""
    return video_path.parent / f".{video_path.stem}.chromium_compatible"


def _is_already_processed(video_path: Path) -> bool:
    """Check if a video has already been checked/transcoded."""
    marker = _get_transcode_marker_path(video_path)
    return marker.exists()


def _mark_as_compatible(video_path: Path, was_transcoded: bool, info: dict) -> None:
    """Mark a video as Chromium-compatible."""
    marker = _get_transcode_marker_path(video_path)
    marker.write_text(json.dumps({
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "was_transcoded": was_transcoded,
        "original_file": video_path.name,
        "video_codec": info.get("video_codec"),
        "audio_codec": info.get("audio_codec"),
    }))


async def probe_video(video_path: Path) -> dict:
    """Probe a video file to get codec information.

    Args:
        video_path: Path to the video file

    Returns:
        Dict with video and audio codec info, or error
    """
    if not video_path.exists():
        return {"success": False, "error": f"File not found: {video_path}"}

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return {
                "success": False,
                "error": f"ffprobe failed: {stderr.decode('utf-8', errors='replace')}",
            }

        data = json.loads(stdout.decode("utf-8"))

        video_stream = None
        audio_stream = None

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video" and video_stream is None:
                video_stream = stream
            elif stream.get("codec_type") == "audio" and audio_stream is None:
                audio_stream = stream

        result = {
            "success": True,
            "video_codec": video_stream.get("codec_name") if video_stream else None,
            "video_profile": video_stream.get("profile", "").lower() if video_stream else None,
            "video_level": video_stream.get("level") if video_stream else None,
            "video_width": video_stream.get("width") if video_stream else None,
            "video_height": video_stream.get("height") if video_stream else None,
            "video_pix_fmt": video_stream.get("pix_fmt") if video_stream else None,
            "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
            "audio_channels": audio_stream.get("channels") if audio_stream else None,
            "audio_sample_rate": audio_stream.get("sample_rate") if audio_stream else None,
            "container": data.get("format", {}).get("format_name"),
            "duration": float(data.get("format", {}).get("duration", 0)),
            "size_bytes": int(data.get("format", {}).get("size", 0)),
        }

        return result

    except FileNotFoundError:
        return {"success": False, "error": "ffprobe not found in PATH"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Failed to parse ffprobe output: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_chromium_compatibility(probe_result: dict) -> dict:
    """Check if a video is compatible with Chromium browser.

    Args:
        probe_result: Result from probe_video()

    Returns:
        Dict with compatibility status and reasons
    """
    if not probe_result.get("success"):
        return {
            "compatible": False,
            "needs_video_transcode": True,
            "needs_audio_transcode": True,
            "needs_remux": True,
            "reasons": [probe_result.get("error", "Unknown error")],
        }

    reasons = []
    needs_video_transcode = False
    needs_audio_transcode = False
    needs_remux = False

    video_codec = (probe_result.get("video_codec") or "").lower()
    audio_codec = (probe_result.get("audio_codec") or "").lower()
    container = (probe_result.get("container") or "").lower()
    video_profile = (probe_result.get("video_profile") or "").lower()
    video_level = probe_result.get("video_level")
    pix_fmt = (probe_result.get("video_pix_fmt") or "").lower()

    # Check video codec
    if video_codec not in COMPATIBLE_VIDEO_CODECS:
        needs_video_transcode = True
        reasons.append(f"Video codec '{video_codec}' not compatible (need H.264)")

    # Check H.264 profile if applicable
    if video_codec in COMPATIBLE_VIDEO_CODECS:
        if video_profile and video_profile not in COMPATIBLE_H264_PROFILES:
            needs_video_transcode = True
            reasons.append(f"H.264 profile '{video_profile}' may not be compatible")

        # Check H.264 level
        if video_level and video_level > MAX_H264_LEVEL:
            needs_video_transcode = True
            reasons.append(f"H.264 level {video_level} too high (max {MAX_H264_LEVEL})")

    # Check pixel format (10-bit content won't play in most browsers)
    if "10" in pix_fmt or "12" in pix_fmt:
        needs_video_transcode = True
        reasons.append(f"Pixel format '{pix_fmt}' (10/12-bit) not widely supported")

    # Check audio codec
    if audio_codec and audio_codec not in COMPATIBLE_AUDIO_CODECS:
        needs_audio_transcode = True
        reasons.append(f"Audio codec '{audio_codec}' not compatible (need AAC/MP3/Opus)")

    # Check container
    if "mp4" not in container and "m4v" not in container:
        needs_remux = True
        reasons.append(f"Container '{container}' should be MP4 for best compatibility")

    compatible = not (needs_video_transcode or needs_audio_transcode or needs_remux)

    return {
        "compatible": compatible,
        "needs_video_transcode": needs_video_transcode,
        "needs_audio_transcode": needs_audio_transcode,
        "needs_remux": needs_remux,
        "reasons": reasons if reasons else ["Already compatible"],
        "current_video_codec": video_codec,
        "current_audio_codec": audio_codec,
        "current_container": container,
    }


def _get_archive_path(video_path: Path, media_base: Path) -> Path:
    """Get the archive path for an original file.

    Mirrors the directory structure under .originals/
    e.g., /mnt/media/Movies/Foo/Foo.mkv -> /mnt/media/.originals/Movies/Foo/Foo.mkv
    """
    try:
        relative = video_path.relative_to(media_base)
        return media_base / ".originals" / relative
    except ValueError:
        # video_path is not under media_base, use sibling .originals folder
        return video_path.parent / ".originals" / video_path.name


def _archive_original(video_path: Path, media_base: Optional[Path] = None) -> Optional[Path]:
    """Move original file to .originals archive directory.

    Args:
        video_path: Path to the original video
        media_base: Base media directory for mirroring structure

    Returns:
        Path to archived file, or None if failed
    """
    if media_base is None:
        media_base = Path(settings.MEDIA_BASE)

    archive_path = _get_archive_path(video_path, media_base)

    try:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.rename(archive_path)
        _append_log(f"Archived original: {video_path.name} -> {archive_path}")
        return archive_path
    except OSError as e:
        _append_log(f"Failed to archive {video_path.name}: {e}")
        return None


async def transcode_video(
    video_path: Path,
    output_path: Optional[Path] = None,
    crf: int = 18,
    preset: str = "medium",
    audio_bitrate: str = "192k",
    force: bool = False,
    hardware_accel: Optional[str] = None,
    archive_original: bool = False,
) -> dict:
    """Transcode a video to Chromium-compatible format.

    Args:
        video_path: Path to the input video
        output_path: Path for output (default: same location with .mp4)
        crf: Constant Rate Factor for quality (18-23 recommended, lower = better)
        preset: Encoding preset (slower = better compression)
        audio_bitrate: Audio bitrate
        force: Force transcode even if already compatible
        hardware_accel: Hardware acceleration method (None, 'videotoolbox', 'nvenc', 'vaapi')
        archive_original: Move original to .originals/ folder (hidden from Jellyfin)

    Returns:
        Dict with transcoding result
    """
    if not video_path.exists():
        return {"success": False, "error": f"File not found: {video_path}"}

    # Probe the video first
    probe_result = await probe_video(video_path)
    if not probe_result.get("success"):
        return {"success": False, "error": probe_result.get("error")}

    compat = check_chromium_compatibility(probe_result)

    if compat["compatible"] and not force:
        _append_log(f"Video already compatible: {video_path.name}")
        _mark_as_compatible(video_path, was_transcoded=False, info=probe_result)
        return {
            "success": True,
            "skipped": True,
            "reason": "Already compatible",
            "probe_result": probe_result,
            "compatibility": compat,
        }

    # Determine output path
    if output_path is None:
        if archive_original:
            # When archiving, transcoded file takes the original's place (with .mp4 extension)
            # But if input is already .mp4, we need a temp name first
            if video_path.suffix.lower() == ".mp4":
                output_path = video_path.parent / f"{video_path.stem}_transcoded.mp4"
            else:
                output_path = video_path.parent / f"{video_path.stem}.mp4"
        else:
            # Not archiving - add _chromium suffix to avoid overwriting
            if video_path.suffix.lower() == ".mp4":
                output_path = video_path.parent / f"{video_path.stem}_chromium.mp4"
            else:
                output_path = video_path.parent / f"{video_path.stem}.mp4"

    # Make sure output path is different from input
    if output_path == video_path:
        output_path = video_path.parent / f"{video_path.stem}_transcoded.mp4"

    temp_output = output_path.parent / f".{output_path.name}.temp"

    _append_log(f"Transcoding: {video_path.name} -> {output_path.name}")
    _append_log(f"  Reasons: {', '.join(compat['reasons'])}")

    # Build ffmpeg command
    cmd = ["ffmpeg", "-y", "-hide_banner"]

    # Add hardware acceleration input options
    if hardware_accel == "videotoolbox":
        cmd.extend(["-hwaccel", "videotoolbox"])
    elif hardware_accel == "nvenc":
        cmd.extend(["-hwaccel", "cuda"])
    elif hardware_accel == "vaapi":
        cmd.extend(["-hwaccel", "vaapi", "-hwaccel_output_format", "vaapi"])

    cmd.extend(["-i", str(video_path)])

    # Video encoding options
    if compat["needs_video_transcode"]:
        if hardware_accel == "videotoolbox":
            cmd.extend([
                "-c:v", "h264_videotoolbox",
                "-profile:v", "high",
                "-level:v", "4.1",
                "-b:v", "8M",  # videotoolbox doesn't support CRF well
            ])
        elif hardware_accel == "nvenc":
            cmd.extend([
                "-c:v", "h264_nvenc",
                "-profile:v", "high",
                "-level:v", "4.1",
                "-cq", str(crf),
                "-preset", "p4",  # nvenc preset naming
            ])
        elif hardware_accel == "vaapi":
            cmd.extend([
                "-c:v", "h264_vaapi",
                "-profile:v", "high",
                "-level:v", "41",
            ])
        else:
            # Software encoding (libx264)
            cmd.extend([
                "-c:v", "libx264",
                "-profile:v", "high",
                "-level:v", "4.1",
                "-crf", str(crf),
                "-preset", preset,
                "-pix_fmt", "yuv420p",  # 8-bit for compatibility
            ])
    elif compat["needs_remux"]:
        # Just copy video stream
        cmd.extend(["-c:v", "copy"])
    else:
        cmd.extend(["-c:v", "copy"])

    # Audio encoding options
    if compat["needs_audio_transcode"]:
        cmd.extend([
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            "-ac", "2",  # Stereo for compatibility
        ])
    else:
        cmd.extend(["-c:a", "copy"])

    # Output options - MP4 has limited subtitle support, so we skip them
    cmd.extend([
        "-movflags", "+faststart",  # Enable streaming
        "-map", "0:v:0",  # First video stream
        "-map", "0:a:0?",  # First audio stream (optional)
        str(temp_output),
    ])

    _append_log(f"FFmpeg command: {' '.join(cmd)}")

    started_at = datetime.now(timezone.utc)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ},
        )

        stdout, _ = await process.communicate()
        output = stdout.decode("utf-8", errors="replace") if stdout else ""

        ended_at = datetime.now(timezone.utc)
        duration = (ended_at - started_at).total_seconds()

        if process.returncode != 0:
            # Clean up temp file
            if temp_output.exists():
                temp_output.unlink()

            _append_log(f"Transcode failed for {video_path.name}: exit code {process.returncode}")
            # Log last 500 chars of output for debugging
            if output:
                _append_log(f"FFmpeg output: {output[-500:]}")

            # If hardware accel failed, suggest fallback
            if hardware_accel and "Error" in output:
                _append_log("Hardware acceleration may not be available, try without it")

            return {
                "success": False,
                "error": f"ffmpeg failed with code {process.returncode}",
                "output": output[-2000:] if len(output) > 2000 else output,
                "duration_seconds": duration,
            }

        # Move temp to final
        temp_output.rename(output_path)

        # Get output file info
        output_size = output_path.stat().st_size
        input_size = probe_result.get("size_bytes", 0)

        _append_log(f"Transcoded {video_path.name} in {duration:.1f}s "
                   f"({input_size / 1024 / 1024:.1f}MB -> {output_size / 1024 / 1024:.1f}MB)")

        # Archive original if requested (moves to .originals/ folder, hidden from Jellyfin)
        archived_path = None
        if archive_original and video_path.exists():
            archived_path = _archive_original(video_path)

            # If input was .mp4, rename output to take its place (remove _transcoded suffix)
            if archived_path and video_path.suffix.lower() == ".mp4":
                final_path = video_path.parent / f"{video_path.stem}.mp4"
                if final_path != output_path and not final_path.exists():
                    try:
                        output_path.rename(final_path)
                        _append_log(f"Renamed {output_path.name} -> {final_path.name}")
                        output_path = final_path
                    except OSError as e:
                        _append_log(f"Warning: Could not rename to original name: {e}")

        _mark_as_compatible(output_path, was_transcoded=True, info=probe_result)

        # Save to history
        history = _load_transcode_history()
        history.append({
            "input_file": str(video_path),
            "output_file": str(output_path),
            "archived_to": str(archived_path) if archived_path else None,
            "started_at": started_at.isoformat(),
            "duration_seconds": duration,
            "input_size_bytes": input_size,
            "output_size_bytes": output_size,
            "video_transcoded": compat["needs_video_transcode"],
            "audio_transcoded": compat["needs_audio_transcode"],
            "remuxed": compat["needs_remux"],
            "success": True,
        })
        _save_transcode_history(history)

        return {
            "success": True,
            "input_file": str(video_path),
            "output_file": str(output_path),
            "archived_to": str(archived_path) if archived_path else None,
            "duration_seconds": duration,
            "input_size_mb": round(input_size / 1024 / 1024, 2),
            "output_size_mb": round(output_size / 1024 / 1024, 2),
            "video_transcoded": compat["needs_video_transcode"],
            "audio_transcoded": compat["needs_audio_transcode"],
            "remuxed_only": compat["needs_remux"] and not (compat["needs_video_transcode"] or compat["needs_audio_transcode"]),
        }

    except FileNotFoundError:
        _append_log("ERROR: ffmpeg not found in PATH")
        return {"success": False, "error": "ffmpeg not found in PATH"}
    except Exception as e:
        _append_log(f"ERROR transcoding: {e}")
        if temp_output.exists():
            temp_output.unlink()
        return {"success": False, "error": str(e)}


def find_videos_to_transcode(
    directory: Path,
    recursive: bool = True,
    skip_processed: bool = True,
) -> list[Path]:
    """Find all video files that need transcoding.

    Args:
        directory: Directory to scan
        recursive: Whether to scan subdirectories
        skip_processed: Skip files with .chromium_compatible marker

    Returns:
        List of video file paths
    """
    if not directory.exists():
        logger.warning(f"Directory does not exist: {directory}")
        return []

    videos = []

    if recursive:
        pattern = "**/*"
    else:
        pattern = "*"

    for file_path in directory.glob(pattern):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if file_path.name.startswith("."):
            continue
        # Skip files that end with _chromium (our output files)
        if file_path.stem.endswith("_chromium"):
            continue
        if skip_processed and _is_already_processed(file_path):
            continue
        videos.append(file_path)

    return sorted(videos)


async def scan_directory(
    directory: Path,
    recursive: bool = True,
) -> dict:
    """Scan a directory and check compatibility of all videos.

    Args:
        directory: Directory to scan
        recursive: Whether to scan subdirectories

    Returns:
        Dict with scan results
    """
    if not directory.exists():
        return {"success": False, "error": f"Directory not found: {directory}"}

    _append_log(f"Scanning directory: {directory} (recursive={recursive})")

    videos = find_videos_to_transcode(directory, recursive, skip_processed=False)

    results = {
        "compatible": [],
        "needs_transcode": [],
        "needs_remux_only": [],
        "errors": [],
    }

    for video_path in videos:
        probe_result = await probe_video(video_path)
        if not probe_result.get("success"):
            results["errors"].append({
                "file": str(video_path),
                "error": probe_result.get("error"),
            })
            continue

        compat = check_chromium_compatibility(probe_result)

        entry = {
            "file": str(video_path),
            "relative_path": str(video_path.relative_to(directory)),
            "size_mb": round(probe_result.get("size_bytes", 0) / 1024 / 1024, 2),
            "video_codec": probe_result.get("video_codec"),
            "audio_codec": probe_result.get("audio_codec"),
            "container": probe_result.get("container"),
            "reasons": compat.get("reasons", []),
        }

        if compat["compatible"]:
            results["compatible"].append(entry)
        elif compat["needs_video_transcode"] or compat["needs_audio_transcode"]:
            results["needs_transcode"].append(entry)
        else:
            results["needs_remux_only"].append(entry)

    _append_log(f"Scan complete: {len(results['compatible'])} compatible, "
               f"{len(results['needs_transcode'])} need transcode, "
               f"{len(results['needs_remux_only'])} need remux only, "
               f"{len(results['errors'])} errors")

    return {
        "success": True,
        "directory": str(directory),
        "total_videos": len(videos),
        "compatible_count": len(results["compatible"]),
        "needs_transcode_count": len(results["needs_transcode"]),
        "needs_remux_count": len(results["needs_remux_only"]),
        "error_count": len(results["errors"]),
        "results": results,
    }


async def transcode_directory(
    directory: Path,
    recursive: bool = True,
    crf: int = 18,
    preset: str = "medium",
    audio_bitrate: str = "192k",
    hardware_accel: Optional[str] = None,
    archive_original: bool = False,
) -> dict:
    """Transcode all videos in a directory that need it.

    Args:
        directory: Directory to process
        recursive: Whether to scan subdirectories
        crf: Constant Rate Factor for quality
        preset: Encoding preset
        audio_bitrate: Audio bitrate
        hardware_accel: Hardware acceleration method
        archive_original: Move originals to .originals/ folder (hidden from Jellyfin)

    Returns:
        Dict with processing results
    """
    if not directory.exists():
        return {"success": False, "error": f"Directory not found: {directory}"}

    _append_log(f"Transcoding directory: {directory} (recursive={recursive}, crf={crf}, preset={preset})")

    videos = find_videos_to_transcode(directory, recursive)

    if not videos:
        _append_log("No videos to transcode")
        return {
            "success": True,
            "videos_found": 0,
            "videos_processed": 0,
            "videos_skipped": 0,
            "videos_failed": 0,
            "results": [],
        }

    _append_log(f"Found {len(videos)} videos to check/transcode")

    results = []
    processed = 0
    skipped = 0
    failed = 0

    for video_path in videos:
        result = await transcode_video(
            video_path,
            crf=crf,
            preset=preset,
            audio_bitrate=audio_bitrate,
            hardware_accel=hardware_accel,
            archive_original=archive_original,
        )

        results.append({
            "file": str(video_path),
            "result": result,
        })

        if result.get("success"):
            if result.get("skipped"):
                skipped += 1
            else:
                processed += 1
        else:
            failed += 1

    _append_log(f"Directory complete: {processed} transcoded, {skipped} skipped, {failed} failed")

    return {
        "success": True,
        "videos_found": len(videos),
        "videos_processed": processed,
        "videos_skipped": skipped,
        "videos_failed": failed,
        "results": results,
    }


def get_transcode_status() -> dict:
    """Get the status of transcoding processing.

    Returns:
        Status information including recent transcoding history
    """
    history = _load_transcode_history()

    if not history:
        return {
            "last_transcode": None,
            "status": "never_run",
            "total_processed": 0,
            "successful_processed": 0,
            "failed_processed": 0,
            "total_space_saved_mb": 0,
        }

    last = history[-1]
    successful = [h for h in history if h.get("success")]
    failed_count = len(history) - len(successful)

    # Calculate space saved (can be negative if transcoded files are larger)
    total_input = sum(h.get("input_size_bytes", 0) for h in successful)
    total_output = sum(h.get("output_size_bytes", 0) for h in successful)
    space_diff_mb = (total_input - total_output) / 1024 / 1024

    return {
        "last_transcode": last.get("started_at"),
        "last_file": last.get("input_file"),
        "status": "success" if last.get("success") else "failed",
        "total_processed": len(history),
        "successful_processed": len(successful),
        "failed_processed": failed_count,
        "total_space_saved_mb": round(space_diff_mb, 2),
    }


def get_transcode_logs(lines: int = 100) -> list[str]:
    """Get recent transcoding log lines.

    Args:
        lines: Number of lines to return (default 100)

    Returns:
        List of log lines
    """
    if not TRANSCODE_LOG_FILE.exists():
        return []

    try:
        all_lines = TRANSCODE_LOG_FILE.read_text().strip().split("\n")
        return all_lines[-lines:] if all_lines else []
    except OSError:
        return []


def check_transcode_config() -> dict:
    """Check if transcoding tools are properly configured.

    Returns:
        Configuration status
    """
    import subprocess

    result = {
        "ffmpeg_installed": False,
        "ffmpeg_version": None,
        "ffprobe_installed": False,
        "hardware_acceleration": [],
        "media_base": settings.MEDIA_BASE,
        "media_base_exists": Path(settings.MEDIA_BASE).exists(),
    }

    # Check ffmpeg
    try:
        output = subprocess.check_output(
            ["ffmpeg", "-version"],
            stderr=subprocess.STDOUT,
            timeout=10,
        )
        version_line = output.decode().split("\n")[0]
        result["ffmpeg_installed"] = True
        result["ffmpeg_version"] = version_line
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check ffprobe
    try:
        subprocess.check_output(
            ["ffprobe", "-version"],
            stderr=subprocess.STDOUT,
            timeout=10,
        )
        result["ffprobe_installed"] = True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check hardware acceleration (macOS VideoToolbox)
    try:
        output = subprocess.check_output(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stderr=subprocess.STDOUT,
            timeout=10,
        ).decode()
        if "h264_videotoolbox" in output:
            result["hardware_acceleration"].append("videotoolbox")
        if "h264_nvenc" in output:
            result["hardware_acceleration"].append("nvenc")
        if "h264_vaapi" in output:
            result["hardware_acceleration"].append("vaapi")
        if "h264_qsv" in output:
            result["hardware_acceleration"].append("qsv")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return result
