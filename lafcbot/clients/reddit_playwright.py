import logging
from datetime import datetime
from urllib.parse import quote_plus

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

from .browser_manager import BrowserManager

logger = logging.getLogger(__name__)


class RedditPlaywrightSearcher:
    """Search Reddit using Playwright headless browser automation."""

    def __init__(self):
        self.browser_manager: BrowserManager | None = None

    async def _ensure_browser(self):
        """Ensure browser manager is initialized."""
        if self.browser_manager is None:
            self.browser_manager = await BrowserManager.get_instance()

    async def search(
        self,
        query: str,
        match_time: datetime,
        sort: str = "new",
        timeout: float = 10.0,
    ) -> dict | None:
        """
        Search Reddit for a goal replay clip.

        Args:
            query: Search query (e.g., "Arsenal Chelsea")
            match_time: Time of the match for timestamp filtering
            sort: Sort order ("new", "relevance", "top")
            timeout: Total timeout in seconds

        Returns:
            dict with {url, title, post_url} or None if not found
        """
        await self._ensure_browser()

        url = self._build_search_url(query, match_time, sort)
        logger.info(f"Searching Reddit via Playwright: {url}")

        try:
            async with self.browser_manager.get_page() as page:
                page.set_default_timeout(timeout * 1000)

                await page.goto(url, wait_until="domcontentloaded")

                posts = await self._extract_search_results(page)

                for post in posts:
                    post_url = post.get("url")
                    title = post.get("title", "")
                    flair = post.get("flair", "")

                    if not post_url:
                        continue

                    if "media" in flair.lower():
                        logger.info(f"Found Media post: {title}")
                        video_url = await self._extract_video_url(
                            page, post_url, timeout
                        )

                        if video_url:
                            return {
                                "url": video_url,
                                "title": title,
                                "post_url": post_url,
                            }
                        else:
                            return {
                                "url": post_url,
                                "title": title,
                                "post_url": post_url,
                            }

                logger.info(f"No Media posts found for query: {query}")
                return None

        except PlaywrightTimeout:
            logger.warning(f"Playwright search timed out: {query}")
            return None
        except Exception as e:
            logger.error(f"Playwright search failed: {e}", exc_info=True)
            return None

    def _build_search_url(self, query: str, match_time: datetime, sort: str) -> str:
        """Build old.reddit.com search URL with filters."""
        encoded_query = quote_plus(query)

        return (
            f"https://old.reddit.com/r/soccer/search?"
            f"q={encoded_query}&"
            f"restrict_sr=on&"
            f"sort={sort}&"
            f"t=all&"
            f"feature=legacy_search"
        )

    async def _extract_search_results(self, page: Page) -> list[dict]:
        """Extract search results using JavaScript evaluation."""
        try:
            results = await page.evaluate("""
                () => {
                    const posts = [];
                    const things = document.querySelectorAll('.thing.link');

                    things.forEach(thing => {
                        const titleEl = thing.querySelector('a.title');
                        const flairEl = thing.querySelector('.linkflairlabel');
                        const permalink = thing.getAttribute('data-permalink');

                        if (titleEl && permalink) {
                            posts.push({
                                title: titleEl.textContent.trim(),
                                url: 'https://old.reddit.com' + permalink,
                                flair: flairEl ? flairEl.textContent.trim() : ''
                            });
                        }
                    });

                    return posts;
                }
            """)
            return results or []
        except Exception as e:
            logger.error(f"Failed to extract search results: {e}", exc_info=True)
            return []

    async def _extract_video_url(
        self, page: Page, post_url: str, timeout: float
    ) -> str | None:
        """
        Extract video URL from Reddit post page.

        Tries multiple strategies in priority order:
        1. Native Reddit video: <video src>
        2. v.redd.it DASH video: <video><source src*="DASH">
        3. External embeds: <iframe src> (Streamable, etc.)
        4. External links: data-url attribute
        """
        try:
            if any(
                domain in post_url.lower()
                for domain in ["streamable.com", "clippituser.tv", "dubz.co"]
            ):
                logger.info(
                    f"Post URL is external video site, using directly: {post_url}"
                )
                return post_url

            await page.goto(post_url, wait_until="domcontentloaded")

            video_url = await page.evaluate("""
                () => {
                    const video = document.querySelector('video');
                    if (video && video.src) {
                        return video.src;
                    }

                    if (video) {
                        const source = video.querySelector('source[src*="DASH"]');
                        if (source && source.src) {
                            return source.src;
                        }
                    }

                    const iframe = document.querySelector('.expando iframe');
                    if (iframe && iframe.src) {
                        return iframe.src;
                    }

                    const thing = document.querySelector('.thing.link');
                    if (thing) {
                        const dataUrl = thing.getAttribute('data-url');
                        if (dataUrl && (dataUrl.includes('streamable') ||
                                       dataUrl.includes('clippituser') ||
                                       dataUrl.includes('dubz'))) {
                            return dataUrl;
                        }
                    }

                    return null;
                }
            """)

            if video_url:
                logger.info(f"Extracted video URL: {video_url}")
                return video_url
            else:
                logger.warning(f"No video found on post page: {post_url}")
                return None

        except PlaywrightTimeout:
            logger.warning(f"Timeout extracting video from: {post_url}")
            return None
        except Exception as e:
            logger.error(f"Failed to extract video URL: {e}", exc_info=True)
            return None
