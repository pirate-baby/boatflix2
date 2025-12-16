"""PySceneDetect service for splitting commercial compilation videos."""

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
PROCESS_HISTORY_FILE = DATA_DIR / "scene_detect_history.json"
PROCESS_LOG_FILE = DATA_DIR / "scene_detect.log"

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".m2ts"}


def _ensure_data_dir() -> None:
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_process_history() -> list[dict]:
    """Load processing history from JSON file."""
    _ensure_data_dir()
    if PROCESS_HISTORY_FILE.exists():
        try:
            return json.loads(PROCESS_HISTORY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_process_history(history: list[dict]) -> None:
    """Save processing history to JSON file."""
    _ensure_data_dir()
    history = history[-100:]
    PROCESS_HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str))


def _append_log(message: str) -> None:
    """Append message to processing log file."""
    _ensure_data_dir()
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(PROCESS_LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def _get_processed_marker_path(video_path: Path) -> Path:
    """Get the marker file path for a processed video."""
    return video_path.parent / f".{video_path.stem}.processed"


def _is_already_processed(video_path: Path) -> bool:
    """Check if a video has already been processed."""
    marker = _get_processed_marker_path(video_path)
    return marker.exists()


def _mark_as_processed(video_path: Path, scenes_count: int) -> None:
    """Mark a video as processed."""
    marker = _get_processed_marker_path(video_path)
    marker.write_text(json.dumps({
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "scenes_count": scenes_count,
        "original_file": video_path.name,
    }))


def _is_split_output(filename: str) -> bool:
    """Check if a filename appears to be a split output (has -NNN suffix)."""
    return bool(re.search(r"-\d{3,}\.[^.]+$", filename))


def get_commercials_directory() -> Path:
    """Get the Commercials directory path."""
    return Path(settings.MEDIA_BASE) / "Commercials"


def find_videos_to_process(directory: Optional[Path] = None) -> list[Path]:
    """Find all video files in a directory that haven't been processed yet.

    Args:
        directory: Directory to scan (defaults to Commercials directory)

    Returns:
        List of video file paths to process
    """
    if directory is None:
        directory = get_commercials_directory()

    if not directory.exists():
        logger.warning(f"Directory does not exist: {directory}")
        return []

    videos = []
    for file_path in directory.iterdir():
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if _is_split_output(file_path.name):
            continue
        if _is_already_processed(file_path):
            continue
        videos.append(file_path)

    return sorted(videos)


async def detect_scenes(
    video_path: Path,
    threshold: float = 27.0,
    min_scene_len: float = 0.5,
    algorithm: str = "content",
) -> dict:
    """Detect scene boundaries in a video file.

    Args:
        video_path: Path to the video file
        threshold: Content detector threshold (default 27.0)
        min_scene_len: Minimum scene length in seconds (default 0.5)
        algorithm: Detection algorithm - 'content', 'adaptive', 'threshold', or 'hash'

    Returns:
        Dict with success status, scene count, and scene list
    """
    if not video_path.exists():
        return {
            "success": False,
            "error": f"File not found: {video_path}",
            "scenes": [],
            "scenes_count": 0,
        }

    _append_log(f"Detecting scenes in: {video_path.name} (algorithm={algorithm}, threshold={threshold})")

    # Build detection command based on algorithm
    if algorithm == "adaptive":
        detect_cmd = ["detect-adaptive", "-t", str(threshold), "--min-scene-len", f"{min_scene_len}s"]
    elif algorithm == "threshold":
        detect_cmd = ["detect-threshold", "-t", str(threshold), "--min-scene-len", f"{min_scene_len}s"]
    elif algorithm == "hash":
        detect_cmd = ["detect-hash", "-t", str(threshold), "--min-scene-len", f"{min_scene_len}s"]
    else:  # default to content
        detect_cmd = ["detect-content", "-t", str(threshold), "--min-scene-len", f"{min_scene_len}s"]

    cmd = [
        "scenedetect",
        "-i", str(video_path),
        "-o", str(video_path.parent),
        "-b", "pyav",
    ] + detect_cmd + ["list-scenes"]

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
            _append_log(f"Scene detection failed for {video_path.name}: {output}")
            return {
                "success": False,
                "error": f"scenedetect failed with code {process.returncode}: {output}",
                "scenes": [],
                "scenes_count": 0,
                "duration_seconds": duration,
            }

        scenes = _parse_scene_list(output)
        _append_log(f"Detected {len(scenes)} scenes in {video_path.name} ({duration:.1f}s)")

        return {
            "success": True,
            "scenes": scenes,
            "scenes_count": len(scenes),
            "duration_seconds": duration,
            "output": output,
        }

    except FileNotFoundError:
        _append_log("ERROR: scenedetect not found in PATH")
        return {
            "success": False,
            "error": "scenedetect not found in PATH",
            "scenes": [],
            "scenes_count": 0,
        }
    except Exception as e:
        _append_log(f"ERROR detecting scenes: {e}")
        return {
            "success": False,
            "error": str(e),
            "scenes": [],
            "scenes_count": 0,
        }


def _parse_scene_list(output: str) -> list[dict]:
    """Parse scene list from scenedetect output."""
    scenes = []
    lines = output.strip().split("\n")

    for line in lines:
        # Try format: "Scene  1: 00:00:00.000 - 00:01:23.456"
        match = re.search(
            r"Scene\s+(\d+):\s+(\d+:\d+:\d+\.\d+)\s+-\s+(\d+:\d+:\d+\.\d+)",
            line
        )
        if match:
            scenes.append({
                "scene_number": int(match.group(1)),
                "start_time": match.group(2),
                "end_time": match.group(3),
            })
            continue

        # Try format from table: "| 1 | 00:00:00.000 | 1 | 00:01:23.456 |"
        match = re.search(
            r"\|\s*(\d+)\s*\|\s*(\d+:\d+:\d+\.\d+)\s*\|\s*\d+\s*\|\s*(\d+:\d+:\d+\.\d+)",
            line
        )
        if match:
            scenes.append({
                "scene_number": int(match.group(1)),
                "start_time": match.group(2),
                "end_time": match.group(3),
            })

    return scenes


async def split_video(
    video_path: Path,
    threshold: float = 27.0,
    min_scene_len: float = 0.5,
    algorithm: str = "content",
) -> dict:
    """Split a video into scenes using PySceneDetect.

    Args:
        video_path: Path to the video file
        threshold: Content detector threshold (default 27.0)
        min_scene_len: Minimum scene length in seconds (default 0.5)
        algorithm: Detection algorithm - 'content', 'adaptive', 'threshold', or 'hash'

    Returns:
        Dict with success status and split results
    """
    if not video_path.exists():
        return {
            "success": False,
            "error": f"File not found: {video_path}",
            "output_files": [],
        }

    _append_log(f"Splitting video: {video_path.name} (algorithm={algorithm}, threshold={threshold})")

    output_dir = video_path.parent
    base_name = video_path.stem

    # Build detection command based on algorithm
    if algorithm == "adaptive":
        detect_cmd = ["detect-adaptive", "-t", str(threshold), "--min-scene-len", f"{min_scene_len}s"]
    elif algorithm == "threshold":
        detect_cmd = ["detect-threshold", "-t", str(threshold), "--min-scene-len", f"{min_scene_len}s"]
    elif algorithm == "hash":
        detect_cmd = ["detect-hash", "-t", str(threshold), "--min-scene-len", f"{min_scene_len}s"]
    else:  # default to content
        detect_cmd = ["detect-content", "-t", str(threshold), "--min-scene-len", f"{min_scene_len}s"]

    cmd = [
        "scenedetect",
        "-i", str(video_path),
        "-o", str(output_dir),
        "-b", "pyav",
    ] + detect_cmd + [
        "split-video",
        "-f", f"{base_name}-$SCENE_NUMBER",
        "-c",  # copy codec (use ffmpeg, not mkvmerge)
    ]

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
            _append_log(f"Video split failed for {video_path.name}: {output}")
            return {
                "success": False,
                "error": f"scenedetect split-video failed with code {process.returncode}: {output}",
                "output_files": [],
                "duration_seconds": duration,
            }

        output_files = _find_split_files(output_dir, base_name)
        scenes_count = len(output_files)

        _mark_as_processed(video_path, scenes_count)

        _append_log(f"Split {video_path.name} into {scenes_count} clips ({duration:.1f}s)")

        history = _load_process_history()
        history.append({
            "input_file": str(video_path),
            "output_files": [str(f) for f in output_files],
            "scenes_count": scenes_count,
            "started_at": started_at.isoformat(),
            "duration_seconds": duration,
            "success": True,
        })
        _save_process_history(history)

        return {
            "success": True,
            "input_file": str(video_path),
            "output_files": [str(f) for f in output_files],
            "scenes_count": scenes_count,
            "duration_seconds": duration,
            "output": output,
        }

    except FileNotFoundError:
        _append_log("ERROR: scenedetect not found in PATH")
        return {
            "success": False,
            "error": "scenedetect not found in PATH",
            "output_files": [],
        }
    except Exception as e:
        _append_log(f"ERROR splitting video: {e}")
        return {
            "success": False,
            "error": str(e),
            "output_files": [],
        }


def _find_split_files(output_dir: Path, base_name: str) -> list[Path]:
    """Find split output files matching the base name pattern."""
    # Match base_name-NNN.ext where NNN is 1 or more digits
    pattern = re.compile(rf"^{re.escape(base_name)}-\d+\.[^.]+$")
    files = []

    for file_path in output_dir.iterdir():
        if file_path.is_file() and pattern.match(file_path.name):
            files.append(file_path)

    return sorted(files)


async def process_directory(
    directory: Optional[Path] = None,
    threshold: float = 27.0,
    min_scene_len: float = 0.5,
    algorithm: str = "content",
) -> dict:
    """Process all unprocessed videos in a directory.

    Args:
        directory: Directory to process (defaults to Commercials directory)
        threshold: Content detector threshold
        min_scene_len: Minimum scene length in seconds
        algorithm: Detection algorithm - 'content', 'adaptive', 'threshold', or 'hash'

    Returns:
        Dict with processing results
    """
    if directory is None:
        directory = get_commercials_directory()

    _append_log(f"Processing directory: {directory} (algorithm={algorithm})")

    videos = find_videos_to_process(directory)

    if not videos:
        _append_log("No videos to process")
        return {
            "success": True,
            "videos_found": 0,
            "videos_processed": 0,
            "results": [],
        }

    _append_log(f"Found {len(videos)} videos to process")

    results = []
    processed_count = 0

    for video_path in videos:
        result = await split_video(video_path, threshold, min_scene_len, algorithm)
        results.append({
            "file": str(video_path),
            "result": result,
        })
        if result["success"]:
            processed_count += 1

    _append_log(f"Processed {processed_count}/{len(videos)} videos successfully")

    return {
        "success": True,
        "videos_found": len(videos),
        "videos_processed": processed_count,
        "results": results,
    }


def get_process_status() -> dict:
    """Get the status of scene detection processing.

    Returns:
        Status information including recent processing history
    """
    history = _load_process_history()

    if not history:
        return {
            "last_process": None,
            "status": "never_run",
            "total_processed": 0,
            "successful_processed": 0,
            "failed_processed": 0,
        }

    last = history[-1]
    successful = sum(1 for h in history if h.get("success"))
    failed = len(history) - successful

    return {
        "last_process": last.get("started_at"),
        "last_file": last.get("input_file"),
        "last_scenes_count": last.get("scenes_count"),
        "status": "success" if last.get("success") else "failed",
        "total_processed": len(history),
        "successful_processed": successful,
        "failed_processed": failed,
    }


def get_process_logs(lines: int = 100) -> list[str]:
    """Get recent processing log lines.

    Args:
        lines: Number of lines to return (default 100)

    Returns:
        List of log lines
    """
    if not PROCESS_LOG_FILE.exists():
        return []

    try:
        all_lines = PROCESS_LOG_FILE.read_text().strip().split("\n")
        return all_lines[-lines:] if all_lines else []
    except OSError:
        return []


def check_scenedetect_config() -> dict:
    """Check if PySceneDetect is properly configured.

    Returns:
        Configuration status
    """
    import subprocess

    result = {
        "scenedetect_installed": False,
        "scenedetect_version": None,
        "ffmpeg_installed": False,
        "ffmpeg_version": None,
        "commercials_dir": str(get_commercials_directory()),
        "commercials_dir_exists": get_commercials_directory().exists(),
        "scene_detect_enabled": settings.SCENE_DETECT_ENABLED,
        "scene_detect_threshold": settings.SCENE_DETECT_THRESHOLD,
        "scene_detect_min_scene_len": settings.SCENE_DETECT_MIN_SCENE_LEN,
        "scene_detect_cron": settings.SCENE_DETECT_CRON,
    }

    try:
        output = subprocess.check_output(
            ["scenedetect", "--version"],
            stderr=subprocess.STDOUT,
            timeout=10,
        )
        version_line = output.decode().strip()
        result["scenedetect_installed"] = True
        result["scenedetect_version"] = version_line
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

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

    return result
