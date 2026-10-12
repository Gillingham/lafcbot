"""Tests for ArchiveClient."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lafcbot.clients.archive_client import ArchiveClient


def _mock_response(status: int = 200, text: str = "", headers: dict | None = None):
    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value=text)
    response.headers = headers or {}
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock()
    return response


def _mock_session(submit_location: str = "/abc123"):
    session = AsyncMock()
    session.get = MagicMock(return_value=_mock_response(text="<html></html>"))
    session.post = MagicMock(
        return_value=_mock_response(headers={"Location": submit_location})
    )
    return session


@pytest.mark.asyncio
async def test_get_archive_url_caches_result():
    session = _mock_session()
    client = ArchiveClient(session=session)

    first = await client.get_archive_url("https://example.com/article")
    second = await client.get_archive_url("https://example.com/article")

    assert first == second == "https://archive.ph/abc123"
    assert session.post.call_count == 1


@pytest.mark.asyncio
async def test_get_archive_url_resubmits_for_different_urls():
    session = _mock_session()
    client = ArchiveClient(session=session)

    await client.get_archive_url("https://example.com/one")
    await client.get_archive_url("https://example.com/two")

    assert session.post.call_count == 2


@pytest.mark.asyncio
async def test_get_page_metadata_parses_open_graph_tags():
    html = """
    <html><head>
      <meta property="og:title" content="A Great Article" />
      <meta property="og:description" content="The blurb." />
      <meta property="og:image" content="https://example.com/image.jpg" />
      <meta property="og:site_name" content="Example News" />
    </head></html>
    """
    session = AsyncMock()
    session.get = MagicMock(return_value=_mock_response(text=html))
    client = ArchiveClient(session=session)

    metadata = await client.get_page_metadata("https://example.com/article")

    assert metadata is not None
    assert metadata.title == "A Great Article"
    assert metadata.description == "The blurb."
    assert metadata.image_url == "https://example.com/image.jpg"
    assert metadata.site_name == "Example News"


@pytest.mark.asyncio
async def test_get_page_metadata_falls_back_to_title_tag():
    html = "<html><head><title>Fallback Title</title></head></html>"
    session = AsyncMock()
    session.get = MagicMock(return_value=_mock_response(text=html))
    client = ArchiveClient(session=session)

    metadata = await client.get_page_metadata("https://example.com/article")

    assert metadata is not None
    assert metadata.title == "Fallback Title"
    assert metadata.description is None
    assert metadata.image_url is None


@pytest.mark.asyncio
async def test_get_page_metadata_none_on_http_error():
    session = AsyncMock()
    session.get = MagicMock(return_value=_mock_response(status=404))
    client = ArchiveClient(session=session)

    assert await client.get_page_metadata("https://example.com/article") is None
