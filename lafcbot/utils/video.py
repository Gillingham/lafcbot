"""Utilities for probing, compressing, and clipping video files with dynamic hardware acceleration."""

import asyncio
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT: float = 30.0
FFPROBE_TIMEOUT: float = 10.0
MAX_COMPRESSION_DURATION: float = 90.0
PREVIEW_CLIP_DURATION: float = 30.0
SAFETY_MARGIN: float = 0.90


@dataclass
class EncoderConfig:
    """Configuration and arguments for a specific FFmpeg video encoder."""

    name: str
    extra_input_args: list[str]
    video_codec_args: list[str]
    scale_filter_template: str
    probe_args: list[str]


def get_software_encoder() -> EncoderConfig:
    """Return the universal CPU software encoder configuration (libx264)."""
    return EncoderConfig(
        name="software_libx264",
        extra_input_args=[],
        video_codec_args=[
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "veryfast",
        ],
        scale_filter_template="scale='min({width},iw)':-2",
        probe_args=["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"],
    )


def get_candidate_encoders() -> list[EncoderConfig]:
    """Return candidate encoders in priority order:

    1. NVIDIA (NVENC)
    2. AMD AMF (Advanced Media Framework)
    3. AMD / Intel Linux VA-API (/dev/dri/renderD128)
    4. Intel QuickSync Video (QSV)
    5. Software fallback (libx264)
    """
    return [
        # 1. NVIDIA NVENC (highest preference)
        EncoderConfig(
            name="nvidia_nvenc",
            extra_input_args=[],
            video_codec_args=[
                "-c:v",
                "h264_nvenc",
                "-preset",
                "p4",
                "-pix_fmt",
                "yuv420p",
            ],
            scale_filter_template="scale='min({width},iw)':-2",
            probe_args=["-c:v", "h264_nvenc", "-preset", "p4"],
        ),
        # 2. AMD AMF
        EncoderConfig(
            name="amd_amf",
            extra_input_args=[],
            video_codec_args=[
                "-c:v",
                "h264_amf",
                "-usage",
                "transcoding",
                "-pix_fmt",
                "nv12",
            ],
            scale_filter_template="scale='min({width},iw)':-2",
            probe_args=["-c:v", "h264_amf"],
        ),
        # 3. AMD / Intel Linux VA-API (via /dev/dri/renderD128)
        EncoderConfig(
            name="amd_vaapi",
            extra_input_args=[
                "-init_hw_device",
                "vaapi=va:/dev/dri/renderD128",
                "-filter_hw_device",
                "va",
            ],
            video_codec_args=["-c:v", "h264_vaapi"],
            scale_filter_template="scale='min({width},iw)':-2,format=nv12,hwupload",
            probe_args=[
                "-vf",
                "format=nv12,hwupload",
                "-c:v",
                "h264_vaapi",
            ],
        ),
        # 4. Intel QuickSync Video (QSV)
        EncoderConfig(
            name="intel_qsv",
            extra_input_args=[],
            video_codec_args=[
                "-c:v",
                "h264_qsv",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "nv12",
            ],
            scale_filter_template="scale='min({width},iw)':-2",
            probe_args=["-c:v", "h264_qsv", "-preset", "veryfast", "-pix_fmt", "nv12"],
        ),
        # 5. Universal software fallback
        get_software_encoder(),
    ]


_DETECTED_ENCODER: EncoderConfig | None = None


async def get_best_encoder(force_refresh: bool = False) -> EncoderConfig:
    """Probe hardware encoders in priority order (NVIDIA -> AMD -> Software) and cache the result."""
    global _DETECTED_ENCODER
    if _DETECTED_ENCODER is not None and not force_refresh:
        return _DETECTED_ENCODER

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return get_software_encoder()

    candidates = get_candidate_encoders()
    for candidate in candidates[:-1]:  # Probe hardware candidates
        probe_cmd = [
            ffmpeg_bin,
            "-y",
            *candidate.extra_input_args,
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:d=0.05",
            *candidate.probe_args,
            "-f",
            "null",
            "-",
        ]
        returncode, _, _ = await _run_command(probe_cmd, timeout=3.0)
        if returncode == 0:
            logger.info(
                f"Hardware video acceleration detected and enabled: {candidate.name}"
            )
            _DETECTED_ENCODER = candidate
            return candidate

    logger.info("No functional hardware encoder detected; using software libx264")
    _DETECTED_ENCODER = get_software_encoder()
    return _DETECTED_ENCODER


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


def _build_ffmpeg_args(
    ffmpeg_bin: str,
    encoder: EncoderConfig,
    input_path: str | Path,
    output_path: str | Path,
    video_bitrate: int,
    audio_bitrate: int,
    scale_width: int,
    duration_limit: float | None = None,
) -> list[str]:
    """Construct FFmpeg command arguments for the specified encoder."""
    scale_filter = encoder.scale_filter_template.format(width=scale_width)
    cmd = [ffmpeg_bin, "-y"]
    cmd.extend(encoder.extra_input_args)
    if duration_limit is not None:
        cmd.extend(["-ss", "0"])
    cmd.extend(["-i", str(input_path)])
    if duration_limit is not None:
        cmd.extend(["-t", str(duration_limit)])
    cmd.extend(encoder.video_codec_args)
    cmd.extend(
        [
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
    )
    return cmd


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

    Dynamically uses hardware acceleration if available (preferring NVIDIA, then AMD),
    with automatic fallback to software libx264.

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

    scale_width = (
        720
        if video_bitrate >= 1_200_000
        else (540 if video_bitrate >= 600_000 else 480)
    )

    encoder = await get_best_encoder()
    cmd = _build_ffmpeg_args(
        ffmpeg_bin=ffmpeg_bin,
        encoder=encoder,
        input_path=input_path,
        output_path=output_path,
        video_bitrate=video_bitrate,
        audio_bitrate=audio_bitrate,
        scale_width=scale_width,
    )

    returncode, _, stderr = await _run_command(cmd, timeout=FFMPEG_TIMEOUT)

    # If a hardware encoder was used and failed, retry with software fallback
    if returncode != 0 and encoder.name != "software_libx264":
        logger.warning(
            f"Hardware encoder ({encoder.name}) failed (code {returncode}); falling back to software libx264"
        )
        software_encoder = get_software_encoder()
        fallback_cmd = _build_ffmpeg_args(
            ffmpeg_bin=ffmpeg_bin,
            encoder=software_encoder,
            input_path=input_path,
            output_path=output_path,
            video_bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
            scale_width=scale_width,
        )
        returncode, _, stderr = await _run_command(fallback_cmd, timeout=FFMPEG_TIMEOUT)

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

    Dynamically uses hardware acceleration if available (preferring NVIDIA, then AMD),
    with automatic fallback to software libx264.

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

    scale_width = (
        720
        if video_bitrate >= 1_200_000
        else (540 if video_bitrate >= 600_000 else 480)
    )

    encoder = await get_best_encoder()
    cmd = _build_ffmpeg_args(
        ffmpeg_bin=ffmpeg_bin,
        encoder=encoder,
        input_path=input_path,
        output_path=output_path,
        video_bitrate=video_bitrate,
        audio_bitrate=audio_bitrate,
        scale_width=scale_width,
        duration_limit=clip_duration,
    )

    returncode, _, stderr = await _run_command(cmd, timeout=FFMPEG_TIMEOUT)

    # If a hardware encoder was used and failed, retry with software fallback
    if returncode != 0 and encoder.name != "software_libx264":
        logger.warning(
            f"Hardware encoder ({encoder.name}) failed (code {returncode}); falling back to software libx264"
        )
        software_encoder = get_software_encoder()
        fallback_cmd = _build_ffmpeg_args(
            ffmpeg_bin=ffmpeg_bin,
            encoder=software_encoder,
            input_path=input_path,
            output_path=output_path,
            video_bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
            scale_width=scale_width,
            duration_limit=clip_duration,
        )
        returncode, _, stderr = await _run_command(fallback_cmd, timeout=FFMPEG_TIMEOUT)

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
