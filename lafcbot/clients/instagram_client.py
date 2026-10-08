"""Client for fetching Instagram post media and metadata."""

import json
import logging
import re
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

EMBED_URL = "https://www.instagram.com/p/{shortcode}/embed/captioned/"

# Instagram only server-renders the full post JSON (including carousel/sidecar
# data) for crawler user agents; browser UAs get back an unrendered SPA shell.
CRAWLER_USER_AGENT = "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"

# The embed page buries the post's GraphQL data as a JSON-escaped string
# value (itself JSON) inside a <script> blob under this key.
CONTEXT_JSON_PATTERN = re.compile(r'"contextJSON":"((?:[^"\\]|\\.)*)"')


@dataclass
class MediaSlide:
    """A single image or video slide of an Instagram post.

    `url` is the actual media to download (the playable video, or the image
    itself). `thumbnail_url` is always a static image, suitable for use as a
    Discord embed's preview image even when the slide is a video.
    """

    url: str
    thumbnail_url: str
    is_video: bool


@dataclass
class InstagramPost:
    """An Instagram post - single image/video or multi-slide carousel - and
    its display metadata.
    """

    slides: list[MediaSlide]
    username: str | None
    avatar_url: str | None
    like_count: int | None
    comment_count: int | None
    caption: str | None


class InstagramClient:
    """Async client for fetching Instagram post media and metadata."""

    def __init__(self, session: aiohttp.ClientSession | None = None):
        """Initialize the client.

        Args:
            session: Optional existing aiohttp session. If not provided, a new one will be created.
        """
        self._session = session
        self._owns_session = session is None
        self._post_cache: dict[str, InstagramPost | None] = {}

    async def close(self):
        """Close the HTTP session if we own it."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def get_post(self, shortcode: str) -> InstagramPost | None:
        """Return an Instagram post's media slides and display metadata.

        Returns None if the post's data couldn't be fetched or parsed -
        callers should fall back to the plain kkinstagram link in that case.
        """
        if shortcode in self._post_cache:
            return self._post_cache[shortcode]

        post = await self._fetch_post(shortcode)
        self._post_cache[shortcode] = post
        return post

    async def download(self, url: str) -> bytes | None:
        """Download raw bytes from an Instagram CDN URL, or None on failure."""
        if self._session is None:
            self._session = aiohttp.ClientSession()

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with self._session.get(url, timeout=timeout) as response:
                if response.status != 200:
                    logger.warning(f"Instagram CDN fetch returned {response.status}")
                    return None
                return await response.read()
        except (aiohttp.ClientError, TimeoutError) as e:
            logger.warning(f"Failed to download Instagram media: {e}")
            return None

    async def _fetch_post(self, shortcode: str) -> InstagramPost | None:
        if self._session is None:
            self._session = aiohttp.ClientSession()

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self._session.get(
                EMBED_URL.format(shortcode=shortcode),
                headers={"User-Agent": CRAWLER_USER_AGENT},
                timeout=timeout,
            ) as response:
                if response.status != 200:
                    logger.warning(
                        f"Instagram embed fetch for {shortcode} returned {response.status}"
                    )
                    return None
                html = await response.text()
        except (aiohttp.ClientError, TimeoutError) as e:
            logger.warning(f"Failed to fetch Instagram embed for {shortcode}: {e}")
            return None

        return self._parse_post(html, shortcode)

    @staticmethod
    def _parse_post(html: str, shortcode: str) -> InstagramPost | None:
        match = CONTEXT_JSON_PATTERN.search(html)
        if not match:
            return None

        try:
            inner_json_text = json.loads('"' + match.group(1) + '"')
            media = json.loads(inner_json_text)["gql_data"]["shortcode_media"]
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse Instagram post data for {shortcode}: {e}")
            return None

        sidecar_edges = media.get("edge_sidecar_to_children", {}).get("edges", [])
        if sidecar_edges:
            slides = [
                slide
                for slide in (
                    InstagramClient._slide_from_node(edge.get("node", {}))
                    for edge in sidecar_edges
                )
                if slide is not None
            ]
        else:
            slides = [
                s for s in [InstagramClient._slide_from_node(media)] if s is not None
            ]

        if not slides:
            return None

        caption_edges = media.get("edge_media_to_caption", {}).get("edges", [])
        caption = caption_edges[0]["node"]["text"] if caption_edges else None
        owner = media.get("owner", {})

        return InstagramPost(
            slides=slides,
            username=owner.get("username"),
            avatar_url=owner.get("profile_pic_url"),
            like_count=media.get("edge_liked_by", {}).get("count"),
            comment_count=media.get("edge_media_to_comment", {}).get("count"),
            caption=caption,
        )

    @staticmethod
    def _slide_from_node(node: dict) -> MediaSlide | None:
        is_video = node.get("is_video", False)
        display_url = node.get("display_url")
        video_url = node.get("video_url") if is_video else None
        url = video_url or display_url
        thumbnail_url = display_url or video_url
        if url is None or thumbnail_url is None:
            return None
        return MediaSlide(url=url, thumbnail_url=thumbnail_url, is_video=is_video)
