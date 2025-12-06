"""rclone service for bidirectional cloud sync operations."""

import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from config import settings

DATA_DIR = Path("/app/data")
SYNC_HISTORY_FILE = DATA_DIR / "sync_history.json"
SYNC_LOG_FILE = DATA_DIR / "sync.log"
RESYNC_MARKER_FILE = DATA_DIR / ".resync_done"


def _ensure_data_dir() -> None:
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_sync_history() -> list[dict]:
    """Load sync history from JSON file."""
    _ensure_data_dir()
    if SYNC_HISTORY_FILE.exists():
        try:
            return json.loads(SYNC_HISTORY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_sync_history(history: list[dict]) -> None:
    """Save sync history to JSON file."""
    _ensure_data_dir()
    # Keep only last 100 entries
    history = history[-100:]
    SYNC_HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str))


def _append_log(message: str) -> None:
    """Append message to sync log file."""
    _ensure_data_dir()
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(SYNC_LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def _needs_resync() -> bool:
    """Check if this is the first run and --resync is needed."""
    return not RESYNC_MARKER_FILE.exists()


def _mark_resync_done() -> None:
    """Mark that initial resync has been completed."""
    _ensure_data_dir()
    RESYNC_MARKER_FILE.write_text(datetime.now(timezone.utc).isoformat())


async def run_bisync(force_resync: bool = False) -> dict:
    """Run rclone bisync between local media and remote storage.

    Args:
        force_resync: Force a resync even if not first run

    Returns:
        Sync result with status, duration, and output
    """
    if not settings.RCLONE_REMOTE or not settings.RCLONE_BUCKET:
        return {
            "success": False,
            "error": "RCLONE_REMOTE and RCLONE_BUCKET must be configured",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 0,
        }

    local_path = settings.MEDIA_PATH
    remote_path = f"{settings.RCLONE_REMOTE}:{settings.RCLONE_BUCKET}"

    # Build command
    cmd = [
        "rclone",
        "bisync",
        local_path,
        remote_path,
        "--verbose",
        "--check-access",
    ]

    # Add --resync flag if first run or forced
    needs_resync = _needs_resync() or force_resync
    if needs_resync:
        cmd.append("--resync")
        _append_log(f"Running bisync with --resync flag (first_run={_needs_resync()}, forced={force_resync})")
    else:
        _append_log("Running regular bisync")

    started_at = datetime.now(timezone.utc)
    _append_log(f"Starting bisync: {local_path} <-> {remote_path}")

    try:
        # Run rclone as subprocess
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

        success = process.returncode == 0

        if success and needs_resync:
            _mark_resync_done()

        result = {
            "success": success,
            "return_code": process.returncode,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "duration_seconds": duration,
            "output": output,
            "resync_used": needs_resync,
        }

        # Log result
        status_msg = "SUCCESS" if success else f"FAILED (code {process.returncode})"
        _append_log(f"Bisync completed: {status_msg} in {duration:.1f}s")

        # Save to history
        history = _load_sync_history()
        history.append({
            "success": success,
            "started_at": started_at.isoformat(),
            "duration_seconds": duration,
            "resync_used": needs_resync,
        })
        _save_sync_history(history)

        return result

    except FileNotFoundError:
        _append_log("ERROR: rclone not found in PATH")
        return {
            "success": False,
            "error": "rclone not found in PATH",
            "started_at": started_at.isoformat(),
            "duration_seconds": 0,
        }
    except Exception as e:
        _append_log(f"ERROR: {e}")
        return {
            "success": False,
            "error": str(e),
            "started_at": started_at.isoformat(),
            "duration_seconds": 0,
        }


def get_sync_status() -> dict:
    """Get the status of the last sync operation.

    Returns:
        Status information including last sync time, success/fail, duration
    """
    history = _load_sync_history()

    if not history:
        return {
            "last_sync": None,
            "status": "never_run",
            "success": None,
            "duration_seconds": None,
            "total_syncs": 0,
            "successful_syncs": 0,
            "failed_syncs": 0,
        }

    last = history[-1]
    successful = sum(1 for h in history if h.get("success"))
    failed = len(history) - successful

    return {
        "last_sync": last.get("started_at"),
        "status": "success" if last.get("success") else "failed",
        "success": last.get("success"),
        "duration_seconds": last.get("duration_seconds"),
        "resync_used": last.get("resync_used"),
        "total_syncs": len(history),
        "successful_syncs": successful,
        "failed_syncs": failed,
    }


def get_sync_logs(lines: int = 100) -> list[str]:
    """Get recent sync log lines.

    Args:
        lines: Number of lines to return (default 100)

    Returns:
        List of log lines
    """
    if not SYNC_LOG_FILE.exists():
        return []

    try:
        all_lines = SYNC_LOG_FILE.read_text().strip().split("\n")
        return all_lines[-lines:] if all_lines else []
    except OSError:
        return []


def check_rclone_config() -> dict:
    """Check if rclone is properly configured.

    Returns:
        Configuration status
    """
    result = {
        "rclone_installed": False,
        "rclone_version": None,
        "remote_configured": bool(settings.RCLONE_REMOTE),
        "bucket_configured": bool(settings.RCLONE_BUCKET),
        "sync_enabled": settings.SYNC_ENABLED,
        "sync_cron": settings.SYNC_CRON,
        "media_path": settings.MEDIA_PATH,
    }

    # Check rclone version
    try:
        output = subprocess.check_output(
            ["rclone", "version"],
            stderr=subprocess.STDOUT,
            timeout=10,
        )
        version_line = output.decode().split("\n")[0]
        result["rclone_installed"] = True
        result["rclone_version"] = version_line
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check if remote is configured (list remotes)
    if result["rclone_installed"] and settings.RCLONE_REMOTE:
        try:
            output = subprocess.check_output(
                ["rclone", "listremotes"],
                stderr=subprocess.STDOUT,
                timeout=10,
            )
            remotes = [r.strip().rstrip(":") for r in output.decode().strip().split("\n") if r.strip()]
            result["remote_exists"] = settings.RCLONE_REMOTE in remotes
            result["available_remotes"] = remotes
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            result["remote_exists"] = False
            result["available_remotes"] = []

    return result
