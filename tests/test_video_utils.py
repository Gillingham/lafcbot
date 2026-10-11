"""Tests for video processing and hybrid compression/clipping utilities."""

import os
import shutil
from unittest.mock import AsyncMock, patch

import pytest

from lafcbot.utils.video import (
    clip_video,
    compress_video,
    get_best_encoder,
    get_candidate_encoders,
    probe_duration,
    process_video,
)

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
IN_CI = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"

# Skip ffmpeg-related tests when running in GitHub Actions CI or if binaries are not found
pytestmark = [
    pytest.mark.ffmpeg,
    pytest.mark.skipif(
        IN_CI or not HAS_FFMPEG,
        reason="Skipping ffmpeg tests in GitHub Actions or when ffmpeg/ffprobe is not available",
    ),
]


@pytest.mark.asyncio
async def test_process_video_fast_path():
    """When video already fits within max_size, it returns immediately without processing."""
    data = b"small-video-bytes"
    result = await process_video(data, max_size=1024)
    assert result == (data, False)


@pytest.mark.asyncio
async def test_process_video_returns_none_when_binaries_missing():
    """When ffmpeg or ffprobe is not installed, process_video gracefully returns None."""
    data = b"large-video-data" * 100
    with patch("shutil.which", return_value=None):
        result = await process_video(data, max_size=10)
        assert result is None


@pytest.mark.asyncio
async def test_probe_duration_parsing():
    """probe_duration parses valid JSON duration from ffprobe."""
    with (
        patch("shutil.which", return_value="/usr/bin/ffprobe"),
        patch(
            "lafcbot.utils.video._run_command",
            new=AsyncMock(
                return_value=(
                    0,
                    b'{"format": {"duration": "45.500000"}}',
                    b"",
                )
            ),
        ),
    ):
        duration = await probe_duration("/dummy/path.mp4")
        assert duration == 45.5


@pytest.mark.asyncio
async def test_probe_duration_invalid_json():
    """probe_duration returns None on invalid or empty JSON."""
    with patch(
        "lafcbot.utils.video._run_command",
        new=AsyncMock(return_value=(0, b"not-json", b"")),
    ):
        duration = await probe_duration("/dummy/path.mp4")
        assert duration is None


@pytest.mark.asyncio
async def test_probe_duration_command_error():
    """probe_duration returns None when ffprobe exits with non-zero code."""
    with patch(
        "lafcbot.utils.video._run_command",
        new=AsyncMock(return_value=(1, b"", b"error")),
    ):
        duration = await probe_duration("/dummy/path.mp4")
        assert duration is None


@pytest.mark.asyncio
async def test_compress_video_skips_when_duration_too_long_for_target():
    """compress_video returns False if calculated bitrate would be below threshold."""
    # 1000 bytes over 60 seconds gives ~133 bps, way below 150_000 bps minimum
    success = await compress_video(
        input_path="/dummy/in.mp4",
        output_path="/dummy/out.mp4",
        target_size_bytes=1000,
        duration=60.0,
    )
    assert success is False


@pytest.mark.asyncio
async def test_clip_video_skips_on_invalid_duration():
    """clip_video returns False if clip duration is zero or negative."""
    success = await clip_video(
        input_path="/dummy/in.mp4",
        output_path="/dummy/out.mp4",
        target_size_bytes=1024 * 1024,
        clip_duration=0,
    )
    assert success is False


@pytest.mark.asyncio
async def test_process_video_hybrid_compresses_short_video():
    """Oversized video under 90s is fully compressed without clipping."""
    data = b"x" * 2000
    compressed_bytes = b"compressed-video"

    async def fake_compress(input_path, output_path, target_size_bytes, duration):
        with open(output_path, "wb") as f:
            f.write(compressed_bytes)
        return True

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("lafcbot.utils.video.probe_duration", new=AsyncMock(return_value=30.0)),
        patch("lafcbot.utils.video.compress_video", side_effect=fake_compress),
    ):
        result = await process_video(data, max_size=1000)
        assert result is not None
        out_bytes, is_clipped = result
        assert is_clipped is False
        assert out_bytes == compressed_bytes


@pytest.mark.asyncio
async def test_process_video_hybrid_clips_long_video():
    """Oversized video over 90s is clipped to preview rather than fully compressed."""
    data = b"x" * 2000
    clipped_bytes = b"clipped-preview-video"

    async def fake_clip(input_path, output_path, target_size_bytes, clip_duration):
        with open(output_path, "wb") as f:
            f.write(clipped_bytes)
        return True

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("lafcbot.utils.video.probe_duration", new=AsyncMock(return_value=120.0)),
        patch(
            "lafcbot.utils.video.compress_video", new=AsyncMock(return_value=False)
        ) as mock_compress,
        patch("lafcbot.utils.video.clip_video", side_effect=fake_clip) as mock_clip,
    ):
        result = await process_video(data, max_size=1000)
        assert result is not None
        out_bytes, is_clipped = result
        assert is_clipped is True
        assert out_bytes == clipped_bytes
        # Full compression shouldn't even be called for > 90s duration
        mock_compress.assert_not_called()
        mock_clip.assert_called_once()


@pytest.mark.asyncio
async def test_process_video_hybrid_clips_when_compression_fails():
    """When full compression fails on <= 90s video, clipping is attempted as fallback."""
    data = b"x" * 2000
    clipped_bytes = b"clipped-fallback-video"

    async def fake_clip(input_path, output_path, target_size_bytes, clip_duration):
        with open(output_path, "wb") as f:
            f.write(clipped_bytes)
        return True

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("lafcbot.utils.video.probe_duration", new=AsyncMock(return_value=60.0)),
        patch(
            "lafcbot.utils.video.compress_video", new=AsyncMock(return_value=False)
        ) as mock_compress,
        patch("lafcbot.utils.video.clip_video", side_effect=fake_clip) as mock_clip,
    ):
        result = await process_video(data, max_size=1000)
        assert result is not None
        out_bytes, is_clipped = result
        assert is_clipped is True
        assert out_bytes == clipped_bytes
        mock_compress.assert_called_once()
        mock_clip.assert_called_once()


@pytest.mark.asyncio
async def test_process_video_returns_none_when_both_fail():
    """When both full compression and clipping fail, process_video returns None."""
    data = b"x" * 2000

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("lafcbot.utils.video.probe_duration", new=AsyncMock(return_value=60.0)),
        patch("lafcbot.utils.video.compress_video", new=AsyncMock(return_value=False)),
        patch("lafcbot.utils.video.clip_video", new=AsyncMock(return_value=False)),
    ):
        result = await process_video(data, max_size=1000)
        assert result is None


@pytest.mark.asyncio
async def test_get_best_encoder_prefers_nvidia():
    """When NVIDIA NVENC probe succeeds, nvidia_nvenc is selected first."""
    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "lafcbot.utils.video._run_command",
            new=AsyncMock(return_value=(0, b"", b"")),
        ) as mock_run,
    ):
        encoder = await get_best_encoder(force_refresh=True)
        assert encoder.name == "nvidia_nvenc"
        mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_best_encoder_selects_amd_when_nvidia_unavailable():
    """When NVIDIA fails and AMD VAAPI succeeds, amd_vaapi is selected."""
    # Candidate order: 1. nvidia_nvenc (fails), 2. amd_amf (fails), 3. amd_vaapi (succeeds)
    side_effects = [
        (1, b"", b"nvenc failed"),
        (1, b"", b"amf failed"),
        (0, b"", b""),
    ]
    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "lafcbot.utils.video._run_command",
            new=AsyncMock(side_effect=side_effects),
        ),
    ):
        encoder = await get_best_encoder(force_refresh=True)
        assert encoder.name == "amd_vaapi"


@pytest.mark.asyncio
async def test_get_best_encoder_selects_vulkan_when_vaapi_unavailable():
    """When NVIDIA, AMF, and VA-API fail and Vulkan Video succeeds, vulkan is selected."""
    side_effects = [
        (1, b"", b"nvenc failed"),
        (1, b"", b"amf failed"),
        (1, b"", b"vaapi failed"),
        (0, b"", b""),
    ]
    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "lafcbot.utils.video._run_command",
            new=AsyncMock(side_effect=side_effects),
        ),
    ):
        encoder = await get_best_encoder(force_refresh=True)
        assert encoder.name == "vulkan"


@pytest.mark.asyncio
async def test_get_best_encoder_selects_intel_qsv_when_nvidia_and_amd_unavailable():
    """When NVIDIA and AMD (AMF, VAAPI, Vulkan) fail and Intel QSV succeeds, intel_qsv is selected."""
    side_effects = [
        (1, b"", b"nvenc failed"),
        (1, b"", b"amf failed"),
        (1, b"", b"vaapi failed"),
        (1, b"", b"vulkan failed"),
        (0, b"", b""),
    ]
    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "lafcbot.utils.video._run_command",
            new=AsyncMock(side_effect=side_effects),
        ),
    ):
        encoder = await get_best_encoder(force_refresh=True)
        assert encoder.name == "intel_qsv"


@pytest.mark.asyncio
async def test_get_best_encoder_falls_back_to_software():
    """When all hardware encoders fail, software_libx264 is selected."""
    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "lafcbot.utils.video._run_command",
            new=AsyncMock(return_value=(1, b"", b"hw failed")),
        ),
    ):
        encoder = await get_best_encoder(force_refresh=True)
        assert encoder.name == "software_libx264"


@pytest.mark.asyncio
async def test_compress_video_falls_back_to_software_when_hardware_fails(tmp_path):
    """If the chosen hardware encoder fails at runtime, compress_video retries with software libx264."""
    in_file = tmp_path / "in.mp4"
    out_file = tmp_path / "out.mp4"
    in_file.write_bytes(b"raw")

    nvenc_config = get_candidate_encoders()[0]
    assert nvenc_config.name == "nvidia_nvenc"

    call_count = 0

    async def fake_run(cmd, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call is with hardware encoder -> fails
            assert "h264_nvenc" in cmd
            return 1, b"", b"gpu error"
        # Second call is software fallback -> succeeds and writes output file
        assert "libx264" in cmd
        out_file.write_bytes(b"fallback-compressed-data")
        return 0, b"", b""

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "lafcbot.utils.video.get_best_encoder",
            new=AsyncMock(return_value=nvenc_config),
        ),
        patch("lafcbot.utils.video._run_command", side_effect=fake_run),
    ):
        success = await compress_video(
            input_path=in_file,
            output_path=out_file,
            target_size_bytes=10 * 1024 * 1024,
            duration=15.0,
        )
        assert success is True
        assert call_count == 2
