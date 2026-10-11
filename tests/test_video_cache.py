"""Tests for VideoCache on-disk LRU transcode cache."""

import time

import pytest

from lafcbot.utils.video_cache import VideoCache


@pytest.mark.asyncio
async def test_cache_set_and_get_exact_match(tmp_path):
    """Setting a video and retrieving it returns the exact bytes and metadata."""
    cache = VideoCache(cache_dir=tmp_path)
    data = b"transcoded-mp4-data"

    await cache.set(
        shortcode="POST123",
        slide_index=1,
        max_size=10_000_000,
        data=data,
        is_clipped=False,
    )

    cached = await cache.get(shortcode="POST123", slide_index=1, max_size=10_000_000)
    assert cached is not None
    cached_data, is_clipped = cached
    assert cached_data == data
    assert is_clipped is False


@pytest.mark.asyncio
async def test_cache_miss_returns_none(tmp_path):
    """Non-existent cache entries return None."""
    cache = VideoCache(cache_dir=tmp_path)
    assert (
        await cache.get(shortcode="NONEXIST", slide_index=1, max_size=10_000_000)
        is None
    )


@pytest.mark.asyncio
async def test_cache_reuses_unclipped_video_for_larger_limit(tmp_path):
    """An unclipped full video encoded for 10MB can be served to a 25MB request."""
    cache = VideoCache(cache_dir=tmp_path)
    data = b"small-full-video"

    await cache.set(
        shortcode="REEL456",
        slide_index=1,
        max_size=10_000_000,
        data=data,
        is_clipped=False,
    )

    # Request with 25MB limit should find the 10MB full unclipped video
    cached = await cache.get(shortcode="REEL456", slide_index=1, max_size=25_000_000)
    assert cached is not None
    cached_data, is_clipped = cached
    assert cached_data == data
    assert is_clipped is False


@pytest.mark.asyncio
async def test_cache_does_not_reuse_oversized_entry_for_smaller_limit(tmp_path):
    """A 20MB video must not be served to a 10MB request."""
    cache = VideoCache(cache_dir=tmp_path)
    data = b"x" * 2000

    await cache.set(
        shortcode="REEL789",
        slide_index=1,
        max_size=25_000_000,
        data=data,
        is_clipped=False,
    )

    # Request with 1000 bytes max limit should NOT return the 2000-byte video
    cached = await cache.get(shortcode="REEL789", slide_index=1, max_size=1000)
    assert cached is None


@pytest.mark.asyncio
async def test_cache_prunes_oldest_files_when_limit_exceeded(tmp_path):
    """Cache prunes oldest items based on mtime when total size exceeds max_bytes."""
    # Max bytes is 250 bytes
    cache = VideoCache(cache_dir=tmp_path, max_bytes=250)

    # Store file 1 (100 bytes)
    await cache.set(
        shortcode="OLD1",
        slide_index=1,
        max_size=1000,
        data=b"a" * 100,
        is_clipped=False,
    )

    time.sleep(0.05)

    # Store file 2 (100 bytes)
    await cache.set(
        shortcode="MED2",
        slide_index=1,
        max_size=1000,
        data=b"b" * 100,
        is_clipped=False,
    )

    time.sleep(0.05)

    # Store file 3 (100 bytes) -> total now 300 > 250, so OLD1 should be pruned
    await cache.set(
        shortcode="NEW3",
        slide_index=1,
        max_size=1000,
        data=b"c" * 100,
        is_clipped=False,
    )

    assert await cache.get(shortcode="OLD1", slide_index=1, max_size=1000) is None
    assert await cache.get(shortcode="MED2", slide_index=1, max_size=1000) is not None
    assert await cache.get(shortcode="NEW3", slide_index=1, max_size=1000) is not None


@pytest.mark.asyncio
async def test_cache_clear(tmp_path):
    """clear() removes all entries from the cache directory."""
    cache = VideoCache(cache_dir=tmp_path)
    await cache.set(
        shortcode="FILE1",
        slide_index=1,
        max_size=1000,
        data=b"test",
        is_clipped=False,
    )
    await cache.clear()

    assert await cache.get(shortcode="FILE1", slide_index=1, max_size=1000) is None


@pytest.mark.asyncio
async def test_cache_handles_corrupted_meta(tmp_path):
    """Cache handles corrupted JSON metadata by returning None."""
    cache = VideoCache(cache_dir=tmp_path)
    video_path = tmp_path / "CORRUPT_1_1000.mp4"
    meta_path = tmp_path / "CORRUPT_1_1000.json"

    video_path.write_bytes(b"some-data")
    meta_path.write_text("not-valid-json", encoding="utf-8")

    assert await cache.get(shortcode="CORRUPT", slide_index=1, max_size=1000) is None
