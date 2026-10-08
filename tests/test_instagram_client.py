"""Tests for InstagramClient."""

import json
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from lafcbot.clients.instagram_client import InstagramClient


def _embed_html(context: dict) -> str:
    """Build a minimal embed-page HTML blob with the given gql_data payload."""
    inner_json = json.dumps({"gql_data": context})
    escaped = json.dumps(inner_json)  # JSON-encode the JSON string itself
    return f'<html><script>window.x = {{"contextJSON":{escaped}}}</script></html>'


SIDECAR_CONTEXT = {
    "shortcode_media": {
        "__typename": "GraphSidecar",
        "edge_sidecar_to_children": {
            "edges": [
                {
                    "node": {
                        "is_video": False,
                        "display_url": "https://cdn.example.com/img1.jpg",
                    }
                },
                {
                    "node": {
                        "is_video": True,
                        "display_url": "https://cdn.example.com/thumb2.jpg",
                        "video_url": "https://cdn.example.com/vid2.mp4",
                    }
                },
            ]
        },
    }
}

SINGLE_POST_CONTEXT = {
    "shortcode_media": {
        "__typename": "GraphImage",
        "display_url": "https://cdn.example.com/single.jpg",
    }
}

CAROUSEL_HTML = _embed_html(SIDECAR_CONTEXT)
SINGLE_POST_HTML = _embed_html(SINGLE_POST_CONTEXT)
NO_CONTEXT_HTML = "<html><head></head></html>"


def _mock_session(
    status: int = 200, text: str = "", raise_error: Exception | None = None
):
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.text = AsyncMock(return_value=text)
    mock_response.read = AsyncMock(return_value=b"binary-data")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock()

    mock_session = AsyncMock()
    if raise_error is not None:
        mock_session.get = MagicMock(side_effect=raise_error)
    else:
        mock_session.get = MagicMock(return_value=mock_response)
    return mock_session


@pytest.mark.asyncio
async def test_get_carousel_slides_parses_sidecar():
    session = _mock_session(text=CAROUSEL_HTML)
    client = InstagramClient(session=session)

    slides = await client.get_carousel_slides("DePKmIWDO2Z")

    assert slides is not None
    assert len(slides) == 2
    assert slides[0].url == "https://cdn.example.com/img1.jpg"
    assert slides[0].is_video is False
    assert slides[1].url == "https://cdn.example.com/vid2.mp4"
    assert slides[1].is_video is True


@pytest.mark.asyncio
async def test_get_carousel_slides_none_for_single_post():
    session = _mock_session(text=SINGLE_POST_HTML)
    client = InstagramClient(session=session)

    assert await client.get_carousel_slides("ABC123") is None


@pytest.mark.asyncio
async def test_get_carousel_slides_none_when_no_context_json():
    session = _mock_session(text=NO_CONTEXT_HTML)
    client = InstagramClient(session=session)

    assert await client.get_carousel_slides("ABC123") is None


@pytest.mark.asyncio
async def test_get_carousel_slides_none_on_http_error():
    session = _mock_session(status=404)
    client = InstagramClient(session=session)

    assert await client.get_carousel_slides("ABC123") is None


@pytest.mark.asyncio
async def test_get_carousel_slides_none_on_client_error():
    session = _mock_session(raise_error=aiohttp.ClientError("boom"))
    client = InstagramClient(session=session)

    assert await client.get_carousel_slides("ABC123") is None


@pytest.mark.asyncio
async def test_get_carousel_slides_caches_result():
    session = _mock_session(text=CAROUSEL_HTML)
    client = InstagramClient(session=session)

    await client.get_carousel_slides("DePKmIWDO2Z")
    await client.get_carousel_slides("DePKmIWDO2Z")

    assert session.get.call_count == 1


@pytest.mark.asyncio
async def test_download_returns_bytes():
    session = _mock_session(status=200)
    client = InstagramClient(session=session)

    data = await client.download("https://cdn.example.com/img1.jpg")

    assert data == b"binary-data"


@pytest.mark.asyncio
async def test_download_returns_none_on_http_error():
    session = _mock_session(status=500)
    client = InstagramClient(session=session)

    assert await client.download("https://cdn.example.com/img1.jpg") is None
