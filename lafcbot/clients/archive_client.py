"""Client for archiving pages via archive.ph (archive.is/archive.today) and
fetching their titles.
"""

import logging

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class ArchiveClient:
    """Async client for submitting pages to archive.ph and reading page titles."""

    BASE_URL = "https://archive.ph"

    def __init__(self, session: aiohttp.ClientSession | None = None):
        """Initialize the client.

        Args:
            session: Optional existing aiohttp session. If not provided, a new one will be created.
        """
        self._session = session
        self._owns_session = session is None

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
        """
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

    async def get_page_title(self, url: str) -> str | None:
        """Fetch a page and return its title, or None if it couldn't be determined."""
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
            if soup.title and soup.title.string:
                return soup.title.string.strip()

            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                return og_title["content"].strip()

            return None

        except (aiohttp.ClientError, TimeoutError) as e:
            logger.warning(f"Failed to fetch title for {url!r}: {e}")
            return None
