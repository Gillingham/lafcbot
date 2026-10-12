"""Tests for VxTCog's link-rewriting logic."""

import re
from unittest.mock import AsyncMock

import pytest

from lafcbot.clients.instagram_client import InstagramPost, MediaSlide
from lafcbot.cogs.vxt import VxTCog

URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(twitter\.com|x\.com|instagram\.com|tiktok\.com)(/\S*)?",
    re.IGNORECASE,
)


def _make_cog(post: InstagramPost | None = None) -> VxTCog:
    """Build a VxTCog without running __init__ (which loads config.json and
    a real bot), wiring up just the attributes _replace_domain/_process_content need.
    """
    cog = VxTCog.__new__(VxTCog)
    cog.url_pattern = URL_PATTERN
    cog.instagram_client = AsyncMock()
    cog.instagram_client.get_post = AsyncMock(return_value=post)
    cog.instagram_client.download = AsyncMock(return_value=b"binary-data")
    cog.video_cache = AsyncMock()
    cog.video_cache.get = AsyncMock(return_value=None)
    cog.video_cache.set = AsyncMock()
    return cog


def _make_post(
    slides: list[MediaSlide],
    username: str | None = "a_guy_called_marc",
    avatar_url: str | None = "https://cdn.example.com/avatar.jpg",
    like_count: int | None = 1411,
    comment_count: int | None = 137,
    caption: str | None = "When Indie Met the Dancefloor. 🪩",
) -> InstagramPost:
    return InstagramPost(
        slides=slides,
        username=username,
        avatar_url=avatar_url,
        like_count=like_count,
        comment_count=comment_count,
        caption=caption,
    )


@pytest.mark.asyncio
async def test_disabled_domain_passes_through_unchanged():
    cog = _make_cog()
    content = "check this out https://instagram.com/p/ABC123"

    new_content, files, embeds = await cog._process_content(
        content,
        enabled_domains={"twitter.com", "x.com"},
        filesize_limit=25 * 1024 * 1024,
    )

    assert new_content == content
    assert files == []
    assert embeds == []
    cog.instagram_client.get_post.assert_not_called()


@pytest.mark.asyncio
async def test_single_instagram_post_falls_back_to_plain_link_when_scrape_fails():
    cog = _make_cog(post=None)
    content = "https://instagram.com/p/ABC123"

    new_content, files, embeds = await cog._process_content(
        content,
        enabled_domains={"instagram.com"},
        filesize_limit=25 * 1024 * 1024,
    )

    assert new_content == "https://instagram.com/p/ABC123"
    assert files == []
    assert embeds == []
    cog.instagram_client.get_post.assert_awaited_once_with("ABC123")


@pytest.mark.asyncio
async def test_single_image_post_builds_embed_with_no_extra_files():
    post = _make_post(
        slides=[
            MediaSlide(
                url="https://cdn.example.com/1.jpg",
                thumbnail_url="https://cdn.example.com/1.jpg",
                is_video=False,
            )
        ]
    )
    cog = _make_cog(post=post)
    content = "https://instagram.com/p/ABC123"

    new_content, files, embeds = await cog._process_content(
        content,
        enabled_domains={"instagram.com"},
        filesize_limit=25 * 1024 * 1024,
    )

    assert new_content == f"<{content}>"
    assert files == []
    assert len(embeds) == 1
    embed = embeds[0]
    assert embed.author.name == "@a_guy_called_marc"
    assert embed.author.icon_url == "https://cdn.example.com/avatar.jpg"
    assert embed.description == "When Indie Met the Dancefloor. 🪩"
    assert embed.image.url == "https://cdn.example.com/1.jpg"
    assert embed.footer.text == "❤️ 1,411  💬 137"


@pytest.mark.asyncio
async def test_single_video_post_skips_embed_and_uses_plain_caption_text():
    post = _make_post(
        slides=[
            MediaSlide(
                url="https://cdn.example.com/vid.mp4",
                thumbnail_url="https://cdn.example.com/thumb.jpg",
                is_video=True,
            )
        ]
    )
    cog = _make_cog(post=post)
    content = "https://instagram.com/reel/XYZ789/"

    new_content, files, embeds = await cog._process_content(
        content,
        enabled_domains={"instagram.com"},
        filesize_limit=25 * 1024 * 1024,
    )

    assert new_content == (
        f"<{content}>\n"
        "**@a_guy_called_marc** · ❤️ 1,411 · 💬 137\n"
        "When Indie Met the Dancefloor. 🪩"
    )
    assert len(files) == 1
    assert files[0].filename == "slide_1.mp4"
    assert embeds == []
    cog.instagram_client.get_post.assert_awaited_once_with("XYZ789")


@pytest.mark.asyncio
async def test_video_post_preserves_surrounding_message_text():
    post = _make_post(
        slides=[
            MediaSlide(
                url="https://cdn.example.com/vid.mp4",
                thumbnail_url="https://cdn.example.com/thumb.jpg",
                is_video=True,
            )
        ]
    )
    cog = _make_cog(post=post)
    url = "https://instagram.com/reel/XYZ789/"
    content = f"text before {url} text after"

    new_content, files, embeds = await cog._process_content(
        content,
        enabled_domains={"instagram.com"},
        filesize_limit=25 * 1024 * 1024,
    )

    assert new_content == (
        f"text before <{url}> text after\n"
        "**@a_guy_called_marc** · ❤️ 1,411 · 💬 137\n"
        "When Indie Met the Dancefloor. 🪩"
    )
    assert len(files) == 1
    assert embeds == []


@pytest.mark.asyncio
async def test_oversized_video_shows_embed_card_with_thumbnail():
    post = _make_post(
        slides=[
            MediaSlide(
                url="https://cdn.example.com/vid.mp4",
                thumbnail_url="https://cdn.example.com/thumb.jpg",
                is_video=True,
            )
        ]
    )
    cog = _make_cog(post=post)
    cog.instagram_client.download = AsyncMock(return_value=None)
    content = "https://instagram.com/reel/XYZ789/"

    new_content, files, embeds = await cog._process_content(
        content,
        enabled_domains={"instagram.com"},
        filesize_limit=25 * 1024 * 1024,
    )

    assert new_content == f"<{content}>"
    assert files == []
    assert len(embeds) == 1
    assert embeds[0].image.url == "https://cdn.example.com/thumb.jpg"


@pytest.mark.asyncio
async def test_reel_with_trailing_query_string_is_handled():
    post = _make_post(
        slides=[
            MediaSlide(
                url="https://cdn.example.com/vid.mp4",
                thumbnail_url="https://cdn.example.com/thumb.jpg",
                is_video=True,
            )
        ]
    )
    cog = _make_cog(post=post)
    content = "https://www.instagram.com/reel/DePe8g3JuEh/?xtok=abc123"

    new_content, files, embeds = await cog._process_content(
        content,
        enabled_domains={"instagram.com"},
        filesize_limit=25 * 1024 * 1024,
    )

    assert new_content.startswith(f"<{content}>")
    assert len(files) == 1
    assert embeds == []
    cog.instagram_client.get_post.assert_awaited_once_with("DePe8g3JuEh")


@pytest.mark.asyncio
async def test_carousel_post_attaches_remaining_slides():
    post = _make_post(
        slides=[
            MediaSlide(
                url="https://cdn.example.com/1.jpg",
                thumbnail_url="https://cdn.example.com/1.jpg",
                is_video=False,
            ),
            MediaSlide(
                url="https://cdn.example.com/2.mp4",
                thumbnail_url="https://cdn.example.com/thumb2.jpg",
                is_video=True,
            ),
            MediaSlide(
                url="https://cdn.example.com/3.jpg",
                thumbnail_url="https://cdn.example.com/3.jpg",
                is_video=False,
            ),
        ]
    )
    cog = _make_cog(post=post)
    content = "https://instagram.com/p/DePKmIWDO2Z"

    new_content, files, embeds = await cog._process_content(
        content,
        enabled_domains={"instagram.com"},
        filesize_limit=25 * 1024 * 1024,
    )

    assert new_content == f"<{content}>"
    assert len(files) == 2
    assert files[0].filename == "slide_2.mp4"
    assert files[1].filename == "slide_3.jpg"
    assert embeds[0].image.url == "https://cdn.example.com/1.jpg"


@pytest.mark.asyncio
async def test_carousel_over_limit_notes_overflow_and_caps_attachments():
    post = _make_post(
        slides=[
            MediaSlide(
                url=f"https://cdn.example.com/{i}.jpg",
                thumbnail_url=f"https://cdn.example.com/{i}.jpg",
                is_video=False,
            )
            for i in range(12)
        ]
    )
    cog = _make_cog(post=post)
    content = "https://instagram.com/p/DePKmIWDO2Z"

    new_content, files, embeds = await cog._process_content(
        content,
        enabled_domains={"instagram.com"},
        filesize_limit=25 * 1024 * 1024,
    )

    assert len(files) == 9
    assert new_content == f"<{content}> (showing 10/12 slides)"


@pytest.mark.asyncio
async def test_missing_metadata_omits_author_and_falls_back_footer():
    post = _make_post(
        slides=[MediaSlide(url="x", thumbnail_url="x", is_video=False)],
        username=None,
        avatar_url=None,
        like_count=None,
        comment_count=None,
        caption=None,
    )
    cog = _make_cog(post=post)
    content = "https://instagram.com/p/DePKmIWDO2Z"

    _, _, embeds = await cog._process_content(
        content,
        enabled_domains={"instagram.com"},
        filesize_limit=25 * 1024 * 1024,
    )

    embed = embeds[0]
    assert embed.author is None
    assert embed.description is None
    assert embed.footer.text == "Instagram"


@pytest.mark.asyncio
async def test_other_domains_unaffected_by_instagram_logic():
    cog = _make_cog()
    content = "https://x.com/someuser/status/123 and https://tiktok.com/@user/video/456"

    new_content, files, embeds = await cog._process_content(
        content,
        enabled_domains={"twitter.com", "x.com", "tiktok.com"},
        filesize_limit=25 * 1024 * 1024,
    )

    assert new_content == (
        "https://fxtwitter.com/someuser/status/123 and https://tnktok.com/@user/video/456"
    )
    assert files == []
    assert embeds == []
    cog.instagram_client.get_post.assert_not_called()


@pytest.mark.asyncio
async def test_oversized_video_compressed_attaches_full_video():
    """When an oversized video is compressed to fit, the full video is attached without preview notice."""
    from unittest.mock import patch

    post = _make_post(
        slides=[
            MediaSlide(
                url="https://cdn.example.com/large.mp4",
                thumbnail_url="https://cdn.example.com/thumb.jpg",
                is_video=True,
            )
        ]
    )
    cog = _make_cog(post=post)
    cog.instagram_client.download = AsyncMock(return_value=b"large-raw-video")

    with patch(
        "lafcbot.cogs.vxt.process_video",
        new=AsyncMock(return_value=(b"compressed-video", False)),
    ):
        content = "https://instagram.com/reel/XYZ789/"
        new_content, files, embeds = await cog._process_content(
            content,
            enabled_domains={"instagram.com"},
            filesize_limit=10 * 1024 * 1024,
        )

        assert len(files) == 1
        assert files[0].filename == "slide_1.mp4"
        assert embeds == []
        assert "preview" not in new_content
        assert "@a_guy_called_marc" in new_content


@pytest.mark.asyncio
async def test_oversized_video_clipped_attaches_preview_with_notice():
    """When an oversized video is clipped, the preview video is attached with preview notice."""
    from unittest.mock import patch

    post = _make_post(
        slides=[
            MediaSlide(
                url="https://cdn.example.com/long.mp4",
                thumbnail_url="https://cdn.example.com/thumb.jpg",
                is_video=True,
            )
        ]
    )
    cog = _make_cog(post=post)
    cog.instagram_client.download = AsyncMock(return_value=b"long-raw-video")

    with patch(
        "lafcbot.cogs.vxt.process_video",
        new=AsyncMock(return_value=(b"clipped-preview-video", True)),
    ):
        content = "https://instagram.com/reel/XYZ789/"
        new_content, files, embeds = await cog._process_content(
            content,
            enabled_domains={"instagram.com"},
            filesize_limit=10 * 1024 * 1024,
        )

        assert len(files) == 1
        assert files[0].filename == "slide_1.mp4"
        assert embeds == []
        assert "*(preview - full video exceeds Discord file size limit)*" in new_content


@pytest.mark.asyncio
async def test_oversized_video_processing_failure_falls_back_to_embed():
    """When video compression/clipping fails, VxTCog falls back to the embed card with thumbnail."""
    from unittest.mock import patch

    post = _make_post(
        slides=[
            MediaSlide(
                url="https://cdn.example.com/unfixable.mp4",
                thumbnail_url="https://cdn.example.com/thumb.jpg",
                is_video=True,
            )
        ]
    )
    cog = _make_cog(post=post)
    cog.instagram_client.download = AsyncMock(return_value=b"unfixable-video")

    with patch("lafcbot.cogs.vxt.process_video", new=AsyncMock(return_value=None)):
        content = "https://instagram.com/reel/XYZ789/"
        new_content, files, embeds = await cog._process_content(
            content,
            enabled_domains={"instagram.com"},
            filesize_limit=10 * 1024 * 1024,
        )

        assert files == []
        assert len(embeds) == 1
        assert embeds[0].image.url == "https://cdn.example.com/thumb.jpg"


@pytest.mark.asyncio
async def test_relinked_video_served_from_cache_without_download_or_encode():
    """When a video is already cached, it is served from cache without downloading or re-encoding."""
    from unittest.mock import patch

    post = _make_post(
        slides=[
            MediaSlide(
                url="https://cdn.example.com/cached.mp4",
                thumbnail_url="https://cdn.example.com/thumb.jpg",
                is_video=True,
            )
        ]
    )
    cog = _make_cog(post=post)
    cog.video_cache.get = AsyncMock(return_value=(b"cached-transcode-data", False))

    with patch("lafcbot.cogs.vxt.process_video") as mock_process:
        content = "https://instagram.com/reel/CACHED123/"
        new_content, files, embeds = await cog._process_content(
            content,
            enabled_domains={"instagram.com"},
            filesize_limit=10 * 1024 * 1024,
        )

        assert len(files) == 1
        assert files[0].filename == "slide_1.mp4"
        assert embeds == []
        cog.video_cache.get.assert_awaited_once_with(
            shortcode="CACHED123", slide_index=1, max_size=10 * 1024 * 1024
        )
        cog.instagram_client.download.assert_not_called()
        mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_cache_miss_stores_transcoded_result():
    """When a video is not in cache, the processed video is stored into cache."""
    from unittest.mock import patch

    post = _make_post(
        slides=[
            MediaSlide(
                url="https://cdn.example.com/uncached.mp4",
                thumbnail_url="https://cdn.example.com/thumb.jpg",
                is_video=True,
            )
        ]
    )
    cog = _make_cog(post=post)
    cog.video_cache.get = AsyncMock(return_value=None)
    cog.instagram_client.download = AsyncMock(return_value=b"raw-bytes")

    with patch(
        "lafcbot.cogs.vxt.process_video",
        new=AsyncMock(return_value=(b"new-encoded-bytes", True)),
    ):
        content = "https://instagram.com/reel/NEW123/"
        new_content, files, embeds = await cog._process_content(
            content,
            enabled_domains={"instagram.com"},
            filesize_limit=10 * 1024 * 1024,
        )

        assert len(files) == 1
        cog.video_cache.set.assert_awaited_once_with(
            shortcode="NEW123",
            slide_index=1,
            max_size=10 * 1024 * 1024,
            data=b"new-encoded-bytes",
            is_clipped=True,
        )
