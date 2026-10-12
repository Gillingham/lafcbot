"""Client for archiving pages via archive.ph (archive.is/archive.today) and
fetching their metadata.
"""

import logging
from collections import OrderedDict
from dataclasses import dataclass

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# functools.lru_cache can't be used directly on an async method - it would
# cache the coroutine object itself, and awaiting the same coroutine twice
# raises. This bounded OrderedDict gives the same eviction behavior for the
# resolved archive.ph URLs instead.
ARCHIVE_URL_CACHE_SIZE = 256


@dataclass
class PageMetadata:
    """Open Graph metadata scraped from a page, for building a rich embed."""

    title: str | None
    description: str | None
    image_url: str | None
    site_name: str | None


class ArchiveClient:
    """Async client for submitting pages to archive.ph and reading page metadata."""

    BASE_URL = "https://archive.ph"

    def __init__(self, session: aiohttp.ClientSession | None = None):
        """Initialize the client.

        Args:
            session: Optional existing aiohttp session. If not provided, a new one will be created.
        """
        self._session = session
        self._owns_session = session is None
        self._archive_url_cache: OrderedDict[str, str] = OrderedDict()

    async def __aenter__(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close the HTTP session if we own it."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def get_archive_url(self, url: str) -> str:
        """Submit a page to archive.ph and return its archived link.

        Falls back to the `/newest/` lookup link (which archive.ph resolves
        client-side) if submission fails for any reason, so this always
        returns a usable archive.ph link.

        Results are cached per URL so repeated `!archive` calls on the same
        link don't resubmit it to archive.ph.
        """
        cached = self._archive_url_cache.get(url)
        if cached is not None:
            self._archive_url_cache.move_to_end(url)
            return cached

        result = await self._submit_for_archive_url(url)

        self._archive_url_cache[url] = result
        self._archive_url_cache.move_to_end(url)
        if len(self._archive_url_cache) > ARCHIVE_URL_CACHE_SIZE:
            self._archive_url_cache.popitem(last=False)

        return result

    async def _submit_for_archive_url(self, url: str) -> str:
        if not self._session:
            self._session = aiohttp.ClientSession()

        fallback = f"{self.BASE_URL}/newest/{url}"

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            headers = {"User-Agent": BROWSER_USER_AGENT}

            async with self._session.get(
                f"{self.BASE_URL}/", headers=headers, timeout=timeout
            ) as response:
                if response.status != 200:
                    logger.warning(
                        f"archive.ph homepage returned status {response.status}"
                    )
                    return fallback
                html = await response.text()

            soup = BeautifulSoup(html, "lxml")
            submitid_input = soup.find("input", {"name": "submitid"})
            submitid = submitid_input.get("value") if submitid_input else None

            data = {"url": url}
            if submitid:
                data["submitid"] = submitid

            async with self._session.post(
                f"{self.BASE_URL}/submit/",
                data=data,
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
            ) as response:
                location = response.headers.get("Location")
                if location:
                    if location.startswith("http"):
                        return location
                    return f"{self.BASE_URL}{location}"

                logger.warning(
                    f"archive.ph submit returned status {response.status} with no Location"
                )
                return fallback

        except (aiohttp.ClientError, TimeoutError) as e:
            logger.warning(f"archive.ph submission failed for {url!r}: {e}")
            return fallback

    async def get_page_metadata(self, url: str) -> PageMetadata | None:
        """Fetch a page and return its title/description/image/site name
        (preferring Open Graph tags), or None if the page couldn't be fetched.
        """
        if not self._session:
            self._session = aiohttp.ClientSession()

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            headers = {"User-Agent": BROWSER_USER_AGENT}

            async with self._session.get(
                url, headers=headers, timeout=timeout
            ) as response:
                if response.status != 200:
                    logger.warning(f"{url!r} returned status {response.status}")
                    return None
                html = await response.text()

            soup = BeautifulSoup(html, "lxml")

            title = None
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()
            elif soup.title and soup.title.string:
                title = soup.title.string.strip()

            description = None
            og_description = soup.find("meta", property="og:description")
            if og_description and og_description.get("content"):
                description = og_description["content"].strip()
            else:
                meta_description = soup.find("meta", attrs={"name": "description"})
                if meta_description and meta_description.get("content"):
                    description = meta_description["content"].strip()

            image_url = None
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                image_url = og_image["content"].strip()

            site_name = None
            og_site_name = soup.find("meta", property="og:site_name")
            if og_site_name and og_site_name.get("content"):
                site_name = og_site_name["content"].strip()

            return PageMetadata(
                title=title,
                description=description,
                image_url=image_url,
                site_name=site_name,
            )

        except (aiohttp.ClientError, TimeoutError) as e:
            logger.warning(f"Failed to fetch metadata for {url!r}: {e}")
            return None
