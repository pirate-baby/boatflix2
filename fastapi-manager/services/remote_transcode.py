"""Remote transcode service for offloading transcoding to a more powerful machine via SSH.

This service handles:
1. Transferring video files to remote machine
2. Executing ffmpeg transcoding remotely
3. Transferring transcoded files back
4. Maintaining the same interface as local transcoding
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional
import shutil

from config import settings

logger = logging.getLogger(__name__)


class RemoteTranscodeError(Exception):
    """Exception raised for remote transcode errors."""
    pass


async def _run_ssh_command(
    command: str,
    capture_output: bool = True,
) -> tuple[int, str, str]:
    """Execute a command on the remote host via SSH.

    Args:
        command: Command to execute on remote host
        capture_output: Whether to capture stdout/stderr

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    ssh_args = [
        "ssh",
        "-p", str(settings.REMOTE_TRANSCODE_PORT),
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
    ]

    if settings.REMOTE_TRANSCODE_SSH_KEY:
        ssh_args.extend(["-i", settings.REMOTE_TRANSCODE_SSH_KEY])

    ssh_target = f"{settings.REMOTE_TRANSCODE_USER}@{settings.REMOTE_TRANSCODE_HOST}"
    ssh_args.append(ssh_target)
    ssh_args.append(command)

    logger.debug(f"SSH command: {' '.join(ssh_args)}")

    if capture_output:
        process = await asyncio.create_subprocess_exec(
            *ssh_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return (
            process.returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
    else:
        process = await asyncio.create_subprocess_exec(*ssh_args)
        await process.wait()
        return (process.returncode, "", "")


async def _transfer_file_to_remote(
    local_path: Path,
    remote_path: str,
    show_progress: bool = True,
) -> bool:
    """Transfer a file to the remote host using rsync over SSH.

    Args:
        local_path: Local file path
        remote_path: Remote file path
        show_progress: Whether to show progress

    Returns:
        True if successful, False otherwise
    """
    ssh_target = f"{settings.REMOTE_TRANSCODE_USER}@{settings.REMOTE_TRANSCODE_HOST}"

    rsync_args = [
        "rsync",
        "-avz",
        "--partial",
        "-e", f"ssh -p {settings.REMOTE_TRANSCODE_PORT} -o StrictHostKeyChecking=no",
    ]

    if settings.REMOTE_TRANSCODE_SSH_KEY:
        rsync_args[5] = f"ssh -p {settings.REMOTE_TRANSCODE_PORT} -i {settings.REMOTE_TRANSCODE_SSH_KEY} -o StrictHostKeyChecking=no"

    if show_progress:
        rsync_args.append("--progress")

    rsync_args.extend([
        str(local_path),
        f"{ssh_target}:{remote_path}",
    ])

    logger.info(f"Transferring {local_path.name} to remote host...")
    logger.debug(f"rsync command: {' '.join(rsync_args)}")

    process = await asyncio.create_subprocess_exec(
        *rsync_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        logger.error(f"rsync failed: {stderr.decode('utf-8', errors='replace')}")
        return False

    logger.info(f"Transfer complete: {local_path.name}")
    return True


async def _transfer_file_from_remote(
    remote_path: str,
    local_path: Path,
    show_progress: bool = True,
) -> bool:
    """Transfer a file from the remote host using rsync over SSH.

    Args:
        remote_path: Remote file path
        local_path: Local file path
        show_progress: Whether to show progress

    Returns:
        True if successful, False otherwise
    """
    ssh_target = f"{settings.REMOTE_TRANSCODE_USER}@{settings.REMOTE_TRANSCODE_HOST}"

    rsync_args = [
        "rsync",
        "-avz",
        "--partial",
        "-e", f"ssh -p {settings.REMOTE_TRANSCODE_PORT} -o StrictHostKeyChecking=no",
    ]

    if settings.REMOTE_TRANSCODE_SSH_KEY:
        rsync_args[5] = f"ssh -p {settings.REMOTE_TRANSCODE_PORT} -i {settings.REMOTE_TRANSCODE_SSH_KEY} -o StrictHostKeyChecking=no"

    if show_progress:
        rsync_args.append("--progress")

    rsync_args.extend([
        f"{ssh_target}:{remote_path}",
        str(local_path),
    ])

    logger.info(f"Transferring {Path(remote_path).name} from remote host...")
    logger.debug(f"rsync command: {' '.join(rsync_args)}")

    process = await asyncio.create_subprocess_exec(
        *rsync_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        logger.error(f"rsync failed: {stderr.decode('utf-8', errors='replace')}")
        return False

    logger.info(f"Transfer complete: {Path(remote_path).name}")
    return True


async def check_remote_host() -> dict:
    """Check if remote host is accessible and has required tools.

    Returns:
        Dict with status information
    """
    if not settings.REMOTE_TRANSCODE_ENABLED:
        return {
            "enabled": False,
            "error": "Remote transcoding not enabled in configuration",
        }

    if not settings.REMOTE_TRANSCODE_HOST or not settings.REMOTE_TRANSCODE_USER:
        return {
            "enabled": True,
            "accessible": False,
            "error": "Remote host or user not configured",
        }

    # Test SSH connectivity
    returncode, stdout, stderr = await _run_ssh_command("echo 'test'")
    if returncode != 0:
        return {
            "enabled": True,
            "accessible": False,
            "error": f"Cannot connect via SSH: {stderr}",
        }

    # Check for ffmpeg
    returncode, stdout, stderr = await _run_ssh_command("which ffmpeg")
    ffmpeg_available = returncode == 0
    ffmpeg_path = stdout.strip() if ffmpeg_available else None

    # Check for ffprobe
    returncode, stdout, stderr = await _run_ssh_command("which ffprobe")
    ffprobe_available = returncode == 0

    # Check for VideoToolbox support (macOS)
    hardware_encoders = []
    if ffmpeg_available:
        returncode, stdout, stderr = await _run_ssh_command(
            f"{ffmpeg_path} -hide_banner -encoders 2>/dev/null | grep h264"
        )
        if "h264_videotoolbox" in stdout:
            hardware_encoders.append("videotoolbox")
        if "h264_nvenc" in stdout:
            hardware_encoders.append("nvenc")
        if "h264_vaapi" in stdout:
            hardware_encoders.append("vaapi")

    # Create work directory
    returncode, stdout, stderr = await _run_ssh_command(
        f"mkdir -p {settings.REMOTE_TRANSCODE_WORK_DIR}"
    )

    return {
        "enabled": True,
        "accessible": True,
        "host": settings.REMOTE_TRANSCODE_HOST,
        "user": settings.REMOTE_TRANSCODE_USER,
        "port": settings.REMOTE_TRANSCODE_PORT,
        "work_dir": settings.REMOTE_TRANSCODE_WORK_DIR,
        "ffmpeg_available": ffmpeg_available,
        "ffmpeg_path": ffmpeg_path,
        "ffprobe_available": ffprobe_available,
        "hardware_encoders": hardware_encoders,
    }


async def remote_transcode_video(
    video_path: Path,
    output_path: Path,
    crf: int = 18,
    preset: str = "medium",
    audio_bitrate: str = "192k",
    hardware_accel: Optional[str] = None,
    progress_callback: Optional[callable] = None,
) -> dict:
    """Transcode a video using the remote host.

    This function:
    1. Transfers the source video to remote host
    2. Executes ffmpeg transcoding on remote host
    3. Transfers the transcoded video back
    4. Cleans up remote files

    Args:
        video_path: Local path to input video
        output_path: Local path for output video
        crf: Constant Rate Factor for quality
        preset: Encoding preset
        audio_bitrate: Audio bitrate
        hardware_accel: Hardware acceleration method (auto-detected if None)
        progress_callback: Optional callback for progress updates

    Returns:
        Dict with transcoding result
    """
    if not settings.REMOTE_TRANSCODE_ENABLED:
        return {
            "success": False,
            "error": "Remote transcoding not enabled",
        }

    # Check remote host
    host_check = await check_remote_host()
    if not host_check.get("accessible"):
        return {
            "success": False,
            "error": f"Remote host not accessible: {host_check.get('error')}",
        }

    if not host_check.get("ffmpeg_available"):
        return {
            "success": False,
            "error": "ffmpeg not available on remote host",
        }

    # Auto-detect hardware acceleration if not specified
    if hardware_accel is None:
        available_encoders = host_check.get("hardware_encoders", [])
        if "videotoolbox" in available_encoders:
            hardware_accel = "videotoolbox"
            logger.info("Using VideoToolbox hardware acceleration on remote host")
        elif "nvenc" in available_encoders:
            hardware_accel = "nvenc"
            logger.info("Using NVENC hardware acceleration on remote host")

    # Generate remote paths
    remote_input = f"{settings.REMOTE_TRANSCODE_WORK_DIR}/{video_path.name}"
    remote_output = f"{settings.REMOTE_TRANSCODE_WORK_DIR}/transcoded_{output_path.name}"

    try:
        # Step 1: Transfer input file to remote
        if progress_callback:
            progress_callback("Transferring source file to remote host...")

        if not await _transfer_file_to_remote(video_path, remote_input):
            return {
                "success": False,
                "error": "Failed to transfer input file to remote host",
            }

        # Step 2: Build and execute ffmpeg command on remote
        if progress_callback:
            progress_callback("Transcoding on remote host...")

        ffmpeg_cmd = ["ffmpeg", "-y", "-hide_banner"]

        # Hardware acceleration
        if hardware_accel == "videotoolbox":
            ffmpeg_cmd.extend(["-hwaccel", "videotoolbox"])
        elif hardware_accel == "nvenc":
            ffmpeg_cmd.extend(["-hwaccel", "cuda"])
        elif hardware_accel == "vaapi":
            ffmpeg_cmd.extend(["-hwaccel", "vaapi", "-hwaccel_output_format", "vaapi"])

        ffmpeg_cmd.extend(["-i", remote_input])

        # Video encoding
        if hardware_accel == "videotoolbox":
            ffmpeg_cmd.extend([
                "-c:v", "h264_videotoolbox",
                "-profile:v", "high",
                "-level:v", "4.1",
                "-b:v", "8M",
            ])
        elif hardware_accel == "nvenc":
            ffmpeg_cmd.extend([
                "-c:v", "h264_nvenc",
                "-profile:v", "high",
                "-level:v", "4.1",
                "-cq", str(crf),
                "-preset", "p4",
            ])
        else:
            # Software encoding
            ffmpeg_cmd.extend([
                "-c:v", "libx264",
                "-profile:v", "high",
                "-level:v", "4.1",
                "-crf", str(crf),
                "-preset", preset,
                "-pix_fmt", "yuv420p",
            ])

        # Audio encoding
        ffmpeg_cmd.extend([
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            "-ac", "2",
        ])

        # Output options
        ffmpeg_cmd.extend([
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-f", "mp4",
            "-movflags", "+faststart",
            remote_output,
        ])

        # Execute ffmpeg on remote
        ffmpeg_cmd_str = " ".join(ffmpeg_cmd)
        logger.info(f"Remote ffmpeg command: {ffmpeg_cmd_str}")

        returncode, stdout, stderr = await _run_ssh_command(ffmpeg_cmd_str)

        if returncode != 0:
            logger.error(f"Remote ffmpeg failed: {stderr}")
            # Cleanup remote files
            await _run_ssh_command(f"rm -f {remote_input} {remote_output}")
            return {
                "success": False,
                "error": f"Remote transcode failed with code {returncode}",
                "output": stderr[-2000:] if len(stderr) > 2000 else stderr,
            }

        # Step 3: Transfer output file back
        if progress_callback:
            progress_callback("Transferring transcoded file back...")

        if not await _transfer_file_from_remote(remote_output, output_path):
            # Cleanup remote files
            await _run_ssh_command(f"rm -f {remote_input} {remote_output}")
            return {
                "success": False,
                "error": "Failed to transfer output file from remote host",
            }

        # Step 4: Cleanup remote files
        logger.info("Cleaning up remote files...")
        await _run_ssh_command(f"rm -f {remote_input} {remote_output}")

        # Get file sizes
        input_size = video_path.stat().st_size
        output_size = output_path.stat().st_size

        return {
            "success": True,
            "remote_transcode": True,
            "input_file": str(video_path),
            "output_file": str(output_path),
            "input_size_mb": round(input_size / 1024 / 1024, 2),
            "output_size_mb": round(output_size / 1024 / 1024, 2),
            "hardware_accel": hardware_accel,
        }

    except Exception as e:
        logger.exception("Remote transcode error")
        # Cleanup remote files
        try:
            await _run_ssh_command(f"rm -f {remote_input} {remote_output}")
        except:
            pass
        return {
            "success": False,
            "error": f"Remote transcode exception: {str(e)}",
        }
