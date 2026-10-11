"""Utilities for probing, compressing, and clipping video files."""

import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT: float = 30.0
FFPROBE_TIMEOUT: float = 10.0
MAX_COMPRESSION_DURATION: float = 90.0
PREVIEW_CLIP_DURATION: float = 30.0
SAFETY_MARGIN: float = 0.90


async def _run_command(cmd: list[str], timeout: float) -> tuple[int, bytes, bytes]:
    """Run an external command asynchronously with a timeout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode if proc.returncode is not None else 1, stdout, stderr
    except TimeoutError:
        try:
            proc.kill()
            await proc.communicate()
        except Exception:
            pass
        logger.warning(f"Command timed out after {timeout}s: {' '.join(cmd[:2])}")
        return 1, b"", b"timeout"
    except Exception as e:
        logger.warning(f"Error executing command {' '.join(cmd[:2])}: {e}")
        return 1, b"", str(e).encode()


async def probe_duration(video_path: str | Path) -> float | None:
    """Probe the duration of a video file using ffprobe.

    Returns the duration in seconds, or None on failure.
    """
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        logger.warning("ffprobe binary not found in PATH")
        return None

    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    returncode, stdout, _ = await _run_command(cmd, timeout=FFPROBE_TIMEOUT)
    if returncode != 0 or not stdout:
        return None

    try:
        data = json.loads(stdout.decode())
        duration_str = data.get("format", {}).get("duration")
        if duration_str is not None:
            val = float(duration_str)
            if val > 0:
                return val
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        pass

    return None


async def compress_video(
    input_path: str | Path,
    output_path: str | Path,
    target_size_bytes: int,
    duration: float,
) -> bool:
    """Compress a video using ffmpeg to fit within target_size_bytes.

    Returns True if successfully compressed and fits within target_size_bytes.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.warning("ffmpeg binary not found in PATH")
        return False

    if duration <= 0:
        return False

    effective_size = target_size_bytes * SAFETY_MARGIN
    total_bitrate = int((effective_size * 8) / duration)
    audio_bitrate = min(128_000, max(64_000, int(total_bitrate * 0.15)))
    video_bitrate = total_bitrate - audio_bitrate

    if video_bitrate < 150_000:
        logger.info(
            f"Video duration ({duration:.1f}s) requires too low bitrate ({video_bitrate} bps) to compress fully"
        )
        return False

    if video_bitrate >= 1_200_000:
        scale_filter = "scale='min(720,iw)':-2"
    elif video_bitrate >= 600_000:
        scale_filter = "scale='min(540,iw)':-2"
    else:
        scale_filter = "scale='min(480,iw)':-2"

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-b:v",
        str(video_bitrate),
        "-maxrate",
        str(int(video_bitrate * 1.2)),
        "-bufsize",
        str(int(video_bitrate * 2.0)),
        "-vf",
        scale_filter,
        "-c:a",
        "aac",
        "-b:a",
        str(audio_bitrate),
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    returncode, _, stderr = await _run_command(cmd, timeout=FFMPEG_TIMEOUT)
    if returncode != 0:
        logger.warning(
            f"FFmpeg compression failed: {stderr.decode(errors='ignore')[:200]}"
        )
        return False

    try:
        size = os.path.getsize(output_path)
        if 0 < size <= target_size_bytes:
            return True
        logger.warning(
            f"Compressed video size ({size} bytes) exceeded target size ({target_size_bytes} bytes)"
        )
    except OSError:
        pass

    return False


async def clip_video(
    input_path: str | Path,
    output_path: str | Path,
    target_size_bytes: int,
    clip_duration: float,
) -> bool:
    """Clip a video to clip_duration seconds and encode to fit within target_size_bytes.

    Returns True if successfully clipped and fits within target_size_bytes.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.warning("ffmpeg binary not found in PATH")
        return False

    if clip_duration <= 0:
        return False

    effective_size = target_size_bytes * SAFETY_MARGIN
    total_bitrate = int((effective_size * 8) / clip_duration)
    audio_bitrate = min(128_000, max(64_000, int(total_bitrate * 0.15)))
    video_bitrate = max(200_000, total_bitrate - audio_bitrate)

    if video_bitrate >= 1_200_000:
        scale_filter = "scale='min(720,iw)':-2"
    elif video_bitrate >= 600_000:
        scale_filter = "scale='min(540,iw)':-2"
    else:
        scale_filter = "scale='min(480,iw)':-2"

    cmd = [
        ffmpeg_bin,
        "-y",
        "-ss",
        "0",
        "-i",
        str(input_path),
        "-t",
        str(clip_duration),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-b:v",
        str(video_bitrate),
        "-maxrate",
        str(int(video_bitrate * 1.2)),
        "-bufsize",
        str(int(video_bitrate * 2.0)),
        "-vf",
        scale_filter,
        "-c:a",
        "aac",
        "-b:a",
        str(audio_bitrate),
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    returncode, _, stderr = await _run_command(cmd, timeout=FFMPEG_TIMEOUT)
    if returncode != 0:
        logger.warning(
            f"FFmpeg clipping failed: {stderr.decode(errors='ignore')[:200]}"
        )
        return False

    try:
        size = os.path.getsize(output_path)
        if 0 < size <= target_size_bytes:
            return True
        logger.warning(
            f"Clipped video size ({size} bytes) exceeded target size ({target_size_bytes} bytes)"
        )
    except OSError:
        pass

    return False


async def process_video(
    data: bytes,
    max_size: int,
    max_compression_duration: float = MAX_COMPRESSION_DURATION,
    preview_clip_duration: float = PREVIEW_CLIP_DURATION,
) -> tuple[bytes, bool] | None:
    """Process video data to fit within max_size using a hybrid strategy.

    1. Fast path: if video already fits within max_size, return as is.
    2. If duration <= max_compression_duration, attempt full compression.
    3. If duration > max_compression_duration (or full compression failed/overshot),
       clip the first preview_clip_duration seconds.
    4. Fall back to None if all strategies fail.

    Returns:
        tuple[bytes, bool]: (video_bytes, is_clipped) where is_clipped indicates
                            if only a preview clip of the video was generated.
        None: If processing failed or video could not fit.
    """
    if len(data) <= max_size:
        return data, False

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        logger.warning("ffmpeg/ffprobe not available to process oversized video")
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.mp4")
        output_path = os.path.join(tmpdir, "output.mp4")

        try:
            with open(input_path, "wb") as f:
                f.write(data)
        except OSError as e:
            logger.warning(f"Failed to write video data to temp file: {e}")
            return None

        duration = await probe_duration(input_path)
        if duration is None or duration <= 0:
            logger.warning("Could not probe video duration")
            return None

        # Strategy 1: Attempt full compression for videos within duration threshold
        if duration <= max_compression_duration:
            success = await compress_video(
                input_path, output_path, target_size_bytes=max_size, duration=duration
            )
            if success:
                try:
                    with open(output_path, "rb") as f:
                        return f.read(), False
                except OSError as e:
                    logger.warning(f"Failed to read compressed video output: {e}")

        # Strategy 2: Clip preview segment for longer videos or if full compression overshot
        target_clip_len = min(preview_clip_duration, duration)
        success = await clip_video(
            input_path,
            output_path,
            target_size_bytes=max_size,
            clip_duration=target_clip_len,
        )
        if success:
            try:
                with open(output_path, "rb") as f:
                    return f.read(), True
            except OSError as e:
                logger.warning(f"Failed to read clipped video output: {e}")

    return None
