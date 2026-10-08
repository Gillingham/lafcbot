"""Tests for VxTCog's link-rewriting logic."""

import re
from unittest.mock import AsyncMock

import pytest

from lafcbot.clients.instagram_client import MediaSlide
from lafcbot.cogs.vxt import VxTCog

URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(twitter\.com|x\.com|instagram\.com|tiktok\.com)(/\S*)?",
    re.IGNORECASE,
)


def _make_cog(carousel_slides: list[MediaSlide] | None = None) -> VxTCog:
    """Build a VxTCog without running __init__ (which loads config.json and
    a real bot), wiring up just the attributes _replace_domain/_process_content need.
    """
    cog = VxTCog.__new__(VxTCog)
    cog.url_pattern = URL_PATTERN
    cog.instagram_client = AsyncMock()
    cog.instagram_client.get_carousel_slides = AsyncMock(return_value=carousel_slides)
    cog.instagram_client.download = AsyncMock(return_value=b"binary-data")
    return cog


@pytest.mark.asyncio
async def test_disabled_domain_passes_through_unchanged():
    cog = _make_cog()
    content = "check this out https://instagram.com/p/ABC123"

    new_content, files = await cog._process_content(
        content, enabled_domains={"twitter.com", "x.com"}
    )

    assert new_content == content
    assert files == []
    cog.instagram_client.get_carousel_slides.assert_not_called()


@pytest.mark.asyncio
async def test_single_instagram_post_rewrites_to_p():
    cog = _make_cog(carousel_slides=None)
    content = "https://instagram.com/p/ABC123"

    new_content, files = await cog._process_content(
        content, enabled_domains={"instagram.com"}
    )

    assert new_content == "https://kkinstagram.com/p/ABC123"
    assert files == []
    cog.instagram_client.get_carousel_slides.assert_awaited_once_with("ABC123")


@pytest.mark.asyncio
async def test_carousel_instagram_post_keeps_link_and_attaches_slides():
    slides = [
        MediaSlide(url="https://cdn.example.com/1.jpg", is_video=False),
        MediaSlide(url="https://cdn.example.com/2.mp4", is_video=True),
    ]
    cog = _make_cog(carousel_slides=slides)
    content = "https://instagram.com/p/DePKmIWDO2Z"

    new_content, files = await cog._process_content(
        content, enabled_domains={"instagram.com"}
    )

    assert new_content == content
    assert len(files) == 2
    assert files[0].filename == "slide_1.jpg"
    assert files[1].filename == "slide_2.mp4"


@pytest.mark.asyncio
async def test_carousel_over_limit_notes_overflow_and_caps_attachments():
    slides = [
        MediaSlide(url=f"https://cdn.example.com/{i}.jpg", is_video=False)
        for i in range(12)
    ]
    cog = _make_cog(carousel_slides=slides)
    content = "https://instagram.com/p/DePKmIWDO2Z"

    new_content, files = await cog._process_content(
        content, enabled_domains={"instagram.com"}
    )

    assert len(files) == 10
    assert new_content == f"{content} (showing 10/12 slides)"


@pytest.mark.asyncio
async def test_instagram_reel_is_unaffected_by_carousel_check():
    cog = _make_cog(carousel_slides=[MediaSlide(url="x", is_video=False)])
    content = "https://instagram.com/reel/XYZ789/"

    new_content, files = await cog._process_content(
        content, enabled_domains={"instagram.com"}
    )

    assert new_content == "https://kkinstagram.com/reel/XYZ789/"
    assert files == []
    cog.instagram_client.get_carousel_slides.assert_not_called()


@pytest.mark.asyncio
async def test_other_domains_unaffected_by_carousel_logic():
    cog = _make_cog()
    content = "https://x.com/someuser/status/123 and https://tiktok.com/@user/video/456"

    new_content, files = await cog._process_content(
        content, enabled_domains={"twitter.com", "x.com", "tiktok.com"}
    )

    assert new_content == (
        "https://fxtwitter.com/someuser/status/123 and https://tnktok.com/@user/video/456"
    )
    assert files == []
    cog.instagram_client.get_carousel_slides.assert_not_called()
