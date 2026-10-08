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
        "owner": {
            "username": "a_guy_called_marc",
            "profile_pic_url": "https://cdn.example.com/avatar.jpg",
        },
        "edge_liked_by": {"count": 1411},
        "edge_media_to_comment": {"count": 137},
        "edge_media_to_caption": {
            "edges": [{"node": {"text": "When Indie Met the Dancefloor. 🪩"}}]
        },
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

SINGLE_IMAGE_CONTEXT = {
    "shortcode_media": {
        "__typename": "GraphImage",
        "is_video": False,
        "display_url": "https://cdn.example.com/single.jpg",
        "owner": {"username": "soloposter", "profile_pic_url": None},
        "edge_liked_by": {"count": 42},
        "edge_media_to_comment": {"count": 3},
        "edge_media_to_caption": {"edges": []},
    }
}

SINGLE_VIDEO_CONTEXT = {
    "shortcode_media": {
        "__typename": "GraphVideo",
        "is_video": True,
        "display_url": "https://cdn.example.com/thumb.jpg",
        "video_url": "https://cdn.example.com/vid.mp4",
        "owner": {"username": "videoposter", "profile_pic_url": None},
        "edge_liked_by": {"count": 10},
        "edge_media_to_comment": {"count": 1},
        "edge_media_to_caption": {"edges": []},
    }
}

CAROUSEL_HTML = _embed_html(SIDECAR_CONTEXT)
SINGLE_IMAGE_HTML = _embed_html(SINGLE_IMAGE_CONTEXT)
SINGLE_VIDEO_HTML = _embed_html(SINGLE_VIDEO_CONTEXT)
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
async def test_get_post_parses_carousel_and_metadata():
    session = _mock_session(text=CAROUSEL_HTML)
    client = InstagramClient(session=session)

    post = await client.get_post("DePKmIWDO2Z")

    assert post is not None
    assert len(post.slides) == 2
    assert post.slides[0].url == "https://cdn.example.com/img1.jpg"
    assert post.slides[0].thumbnail_url == "https://cdn.example.com/img1.jpg"
    assert post.slides[0].is_video is False
    assert post.slides[1].url == "https://cdn.example.com/vid2.mp4"
    assert post.slides[1].thumbnail_url == "https://cdn.example.com/thumb2.jpg"
    assert post.slides[1].is_video is True
    assert post.username == "a_guy_called_marc"
    assert post.avatar_url == "https://cdn.example.com/avatar.jpg"
    assert post.like_count == 1411
    assert post.comment_count == 137
    assert post.caption == "When Indie Met the Dancefloor. 🪩"


@pytest.mark.asyncio
async def test_get_post_parses_single_image():
    session = _mock_session(text=SINGLE_IMAGE_HTML)
    client = InstagramClient(session=session)

    post = await client.get_post("ABC123")

    assert post is not None
    assert len(post.slides) == 1
    assert post.slides[0].url == "https://cdn.example.com/single.jpg"
    assert post.slides[0].thumbnail_url == "https://cdn.example.com/single.jpg"
    assert post.slides[0].is_video is False
    assert post.username == "soloposter"


@pytest.mark.asyncio
async def test_get_post_parses_single_video():
    session = _mock_session(text=SINGLE_VIDEO_HTML)
    client = InstagramClient(session=session)

    post = await client.get_post("XYZ789")

    assert post is not None
    assert len(post.slides) == 1
    assert post.slides[0].url == "https://cdn.example.com/vid.mp4"
    assert post.slides[0].thumbnail_url == "https://cdn.example.com/thumb.jpg"
    assert post.slides[0].is_video is True


@pytest.mark.asyncio
async def test_get_post_none_when_no_context_json():
    session = _mock_session(text=NO_CONTEXT_HTML)
    client = InstagramClient(session=session)

    assert await client.get_post("ABC123") is None


@pytest.mark.asyncio
async def test_get_post_none_on_http_error():
    session = _mock_session(status=404)
    client = InstagramClient(session=session)

    assert await client.get_post("ABC123") is None


@pytest.mark.asyncio
async def test_get_post_none_on_client_error():
    session = _mock_session(raise_error=aiohttp.ClientError("boom"))
    client = InstagramClient(session=session)

    assert await client.get_post("ABC123") is None


@pytest.mark.asyncio
async def test_get_post_caches_result():
    session = _mock_session(text=CAROUSEL_HTML)
    client = InstagramClient(session=session)

    await client.get_post("DePKmIWDO2Z")
    await client.get_post("DePKmIWDO2Z")

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
