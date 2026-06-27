import asyncio
import logging
from contextlib import asynccontextmanager

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

logger = logging.getLogger(__name__)


class BrowserManager:
    """Singleton manager for Playwright browser lifecycle."""

    _instance: "BrowserManager | None" = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._initialized = False

    @classmethod
    async def get_instance(cls) -> "BrowserManager":
        """Get or create the singleton instance."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    async def initialize(self) -> None:
        """Launch headless Chromium with minimal resources."""
        if self._initialized:
            return

        try:
            logger.info("Initializing Playwright browser...")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )
            self._initialized = True
            logger.info("Playwright browser initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Playwright browser: {e}", exc_info=True)
            raise

    @asynccontextmanager
    async def get_page(self):
        """Yield isolated page in new context."""
        if not self._initialized:
            await self.initialize()

        if not self._browser:
            raise RuntimeError("Browser not initialized")

        context: BrowserContext | None = None
        page: Page | None = None

        try:
            context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = await context.new_page()
            yield page
        finally:
            if page:
                await page.close()
            if context:
                await context.close()

    async def close(self) -> None:
        """Close browser and Playwright."""
        if not self._initialized:
            return

        try:
            logger.info("Closing Playwright browser...")
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            self._initialized = False
            logger.info("Playwright browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing Playwright browser: {e}", exc_info=True)

    async def restart(self) -> None:
        """Restart the browser (useful for recovery from crashes)."""
        logger.warning("Restarting Playwright browser...")
        await self.close()
        await self.initialize()
