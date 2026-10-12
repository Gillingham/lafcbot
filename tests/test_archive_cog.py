"""Tests for ArchiveCog's link-finding and archive-embed logic."""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from lafcbot.clients.archive_client import PageMetadata
from lafcbot.cogs.archive import ArchiveCog


def _make_cog() -> ArchiveCog:
    """Build an ArchiveCog without running __init__ (which would construct a
    real ArchiveClient), wiring up just the attributes needed for testing.
    """
    cog = ArchiveCog.__new__(ArchiveCog)
    cog.archive_client = AsyncMock()
    return cog


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChannel:
    """Fake channel whose history() yields messages most-recent-first,
    matching discord.py's channel.history() ordering.
    """

    def __init__(self, messages: list[_FakeMessage]):
        self._messages = messages

    def history(self, limit=None, before=None):
        async def _gen():
            for message in self._messages[:limit]:
                yield message

        return _gen()


@pytest.mark.asyncio
async def test_find_last_link_returns_most_recent_url():
    cog = _make_cog()
    channel = _FakeChannel(
        [
            _FakeMessage("check this out https://example.com/newest"),
            _FakeMessage("no link here"),
            _FakeMessage("older link https://example.com/older"),
        ]
    )

    url = await cog._find_last_link(channel, before=MagicMock())

    assert url == "https://example.com/newest"


@pytest.mark.asyncio
async def test_find_last_link_returns_none_when_no_url_present():
    cog = _make_cog()
    channel = _FakeChannel(
        [_FakeMessage("no links at all"), _FakeMessage("still none")]
    )

    url = await cog._find_last_link(channel, before=MagicMock())

    assert url is None


@pytest.mark.asyncio
async def test_archive_command_sends_embed_and_deletes_original():
    cog = _make_cog()
    cog.archive_client.get_archive_url = AsyncMock(
        return_value="https://archive.ph/abc123"
    )
    cog.archive_client.get_page_metadata = AsyncMock(
        return_value=PageMetadata(
            title="Example Page Title",
            description="A description blurb.",
            image_url="https://example.com/image.jpg",
            site_name="Example News",
        )
    )

    ctx = AsyncMock()
    ctx.channel = _FakeChannel([_FakeMessage("https://example.com/article")])
    ctx.message = AsyncMock()

    await cog.archive.callback(cog, ctx)

    ctx.message.delete.assert_awaited_once()
    ctx.send.assert_awaited_once()
    _, kwargs = ctx.send.call_args
    embed = kwargs["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "Example Page Title"
    assert embed.url == "https://archive.ph/abc123"
    assert embed.description == "A description blurb."
    assert embed.image.url == "https://example.com/image.jpg"
    assert embed.author.name == "Example News"


@pytest.mark.asyncio
async def test_archive_command_falls_back_to_url_when_title_missing():
    cog = _make_cog()
    cog.archive_client.get_archive_url = AsyncMock(
        return_value="https://archive.ph/abc123"
    )
    cog.archive_client.get_page_metadata = AsyncMock(return_value=None)

    ctx = AsyncMock()
    ctx.channel = _FakeChannel([_FakeMessage("https://example.com/article")])
    ctx.message = AsyncMock()

    await cog.archive.callback(cog, ctx)

    _, kwargs = ctx.send.call_args
    embed = kwargs["embed"]
    assert embed.title == "https://example.com/article"


@pytest.mark.asyncio
async def test_archive_command_with_no_link_sends_plain_message():
    cog = _make_cog()
    ctx = AsyncMock()
    ctx.channel = _FakeChannel([_FakeMessage("no links here")])
    ctx.message = AsyncMock()

    await cog.archive.callback(cog, ctx)

    ctx.send.assert_awaited_once_with("No recent link found to archive.")
    ctx.message.delete.assert_not_awaited()
    cog.archive_client.get_archive_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_archive_command_with_explicit_link_uses_that_link():
    cog = _make_cog()
    cog.archive_client.get_archive_url = AsyncMock(
        return_value="https://archive.ph/explicit123"
    )
    cog.archive_client.get_page_metadata = AsyncMock(
        return_value=PageMetadata(
            title="Explicit Page Title",
            description=None,
            image_url=None,
            site_name=None,
        )
    )

    ctx = AsyncMock()
    # Channel history has a different, older link - the explicit argument
    # should win and history should never be consulted.
    ctx.channel = _FakeChannel([_FakeMessage("https://example.com/ignored")])
    ctx.message = AsyncMock()

    await cog.archive.callback(
        cog, ctx, link="please archive https://example.com/explicit"
    )

    cog.archive_client.get_archive_url.assert_awaited_once_with(
        "https://example.com/explicit"
    )
    ctx.message.delete.assert_awaited_once()
    _, kwargs = ctx.send.call_args
    embed = kwargs["embed"]
    assert embed.title == "Explicit Page Title"
    assert embed.url == "https://archive.ph/explicit123"


@pytest.mark.asyncio
async def test_archive_command_with_non_link_argument_sends_error():
    cog = _make_cog()
    ctx = AsyncMock()
    ctx.channel = _FakeChannel([_FakeMessage("https://example.com/ignored")])
    ctx.message = AsyncMock()

    await cog.archive.callback(cog, ctx, link="not a link")

    ctx.send.assert_awaited_once_with("That doesn't look like a link.")
    ctx.message.delete.assert_not_awaited()
    cog.archive_client.get_archive_url.assert_not_awaited()
