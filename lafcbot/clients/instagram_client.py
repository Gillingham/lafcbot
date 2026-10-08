"""Client for fetching Instagram post media, including multi-image/video carousels."""

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
    """A single image or video slide of an Instagram post."""

    url: str
    is_video: bool


class InstagramClient:
    """Async client for fetching Instagram carousel post media."""

    def __init__(self, session: aiohttp.ClientSession | None = None):
        """Initialize the client.

        Args:
            session: Optional existing aiohttp session. If not provided, a new one will be created.
        """
        self._session = session
        self._owns_session = session is None
        self._slides_cache: dict[str, list[MediaSlide] | None] = {}

    async def close(self):
        """Close the HTTP session if we own it."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def get_carousel_slides(self, shortcode: str) -> list[MediaSlide] | None:
        """Return the slides of a multi-image/video carousel post.

        Returns None if the post isn't a carousel, or if its data couldn't be
        fetched or parsed - callers should fall back to normal single-image
        embed behavior in that case.
        """
        if shortcode in self._slides_cache:
            return self._slides_cache[shortcode]

        slides = await self._fetch_carousel_slides(shortcode)
        self._slides_cache[shortcode] = slides
        return slides

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

    async def _fetch_carousel_slides(self, shortcode: str) -> list[MediaSlide] | None:
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

        return self._parse_carousel_slides(html, shortcode)

    @staticmethod
    def _parse_carousel_slides(html: str, shortcode: str) -> list[MediaSlide] | None:
        match = CONTEXT_JSON_PATTERN.search(html)
        if not match:
            return None

        try:
            inner_json_text = json.loads('"' + match.group(1) + '"')
            media = json.loads(inner_json_text)["gql_data"]["shortcode_media"]
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse Instagram post data for {shortcode}: {e}")
            return None

        if media.get("__typename") != "GraphSidecar":
            return None

        slides = []
        for edge in media.get("edge_sidecar_to_children", {}).get("edges", []):
            node = edge.get("node", {})
            is_video = node.get("is_video", False)
            url = node.get("video_url") if is_video else node.get("display_url")
            if url:
                slides.append(MediaSlide(url=url, is_video=is_video))

        return slides or None
