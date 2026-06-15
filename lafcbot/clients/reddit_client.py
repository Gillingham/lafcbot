"""Reddit client for fetching goal replay links from r/soccer."""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)


class RedditGoalFetcher:
    """Fetches goal replay links from Reddit's r/soccer with optional BrightData fallback."""

    def __init__(self, cache_path: str | None = None):
        """
        Initialize the Reddit goal fetcher.

        Args:
            cache_path: Path to cache file. Defaults to ~/.lafcbot/reddit_cache.json
        """
        if cache_path is None:
            cache_dir = Path.home() / ".lafcbot"
            cache_dir.mkdir(exist_ok=True)
            cache_path = str(cache_dir / "reddit_cache.json")

        self.cache_path = cache_path
        self.cache = self._load_cache()
        self.session: aiohttp.ClientSession | None = None
        self._last_request_time = 0.0
        self._rate_limit_delay = (
            6.0  # 10 requests per minute = 6 seconds between requests
        )

        # Check if BrightData is configured (optional fallback)
        self.brightdata_enabled = bool(os.getenv("BRIGHTDATA_API_TOKEN"))
        if self.brightdata_enabled:
            logger.info("BrightData fallback enabled (BRIGHTDATA_API_TOKEN found)")
            # Import BrightData SDK only if enabled
            try:
                from brightdata import BrightDataClient

                self.BrightDataClient = BrightDataClient
            except ImportError:
                logger.warning(
                    "BRIGHTDATA_API_TOKEN set but brightdata-sdk not installed. "
                    "Run: pip install brightdata-sdk"
                )
                self.brightdata_enabled = False
        else:
            logger.info("BrightData fallback disabled (BRIGHTDATA_API_TOKEN not set)")

    def _load_cache(self) -> dict:
        """Load cache from disk."""
        try:
            with open(self.cache_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_cache(self):
        """Save cache to disk."""
        try:
            with open(self.cache_path, "w") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save Reddit cache: {e}")

    async def _rate_limit(self):
        """Apply rate limiting between requests (10 req/min)."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._rate_limit_delay:
            await asyncio.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            # Match golazo's HTTP client configuration exactly
            connector = aiohttp.TCPConnector(
                limit=10,  # MaxIdleConns
                limit_per_host=10,  # MaxIdleConnsPerHost
                ttl_dns_cache=300,
            )
            timeout = aiohttp.ClientTimeout(
                total=10
            )  # Match golazo's 10 second timeout

            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    "User-Agent": "golazo:v1.0.0 (by /u/golazo_app)",
                },
            )

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def search_goal(
        self,
        home_team: str,
        away_team: str,
        minute: int,
        match_time: datetime,
        scoring_team: str,
        home_score: int,
        away_score: int,
    ) -> dict | None:
        """
        Search for a goal replay link on Reddit.

        Searches r/soccer with a ±12 hour time window around the match time to filter
        results and avoid finding old matches with similar keywords.

        Args:
            home_team: Home team name
            away_team: Away team name
            minute: Goal minute
            match_time: Match start time (used for ±12 hour time filtering)
            scoring_team: Name of the team that scored
            home_score: Home score after goal
            away_score: Away score after goal

        Returns:
            Dict with 'url', 'title', 'post_url' if found, else None
        """
        # Check cache first
        cache_key = f"{home_team}:{away_team}:{minute}"
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            # Return cached result if found or if not-found marker is recent
            if cached.get("url") or self._is_recent_not_found(cached):
                return cached if cached.get("url") else None

        await self._ensure_session()

        # Try multiple search strategies
        result = None

        # Strategy 1: Both teams + minute
        result = await self._search_strategy(
            f"{home_team} {away_team} {minute}'", match_time
        )

        # Strategy 2: Scoring team + minute + score
        if not result:
            result = await self._search_strategy(
                f"{scoring_team} {minute}' {home_score}-{away_score}", match_time
            )

        # Strategy 3: Both teams + sort by top
        if not result:
            result = await self._search_strategy(
                f"{home_team} {away_team}", match_time, sort="top"
            )

        # Cache the result
        if result:
            self.cache[cache_key] = {
                "url": result["url"],
                "title": result["title"],
                "post_url": result["post_url"],
                "fetched_at": datetime.now().isoformat(),
            }
        else:
            # Cache "not found" to avoid repeated searches
            self.cache[cache_key] = {
                "url": None,
                "fetched_at": datetime.now().isoformat(),
            }

        self._save_cache()
        return result

    def _is_recent_not_found(self, cached: dict) -> bool:
        """Check if a not-found cache entry is still valid (within 24 hours)."""
        if cached.get("url"):
            return False

        fetched_at_str = cached.get("fetched_at")
        if not fetched_at_str:
            return False

        try:
            fetched_at = datetime.fromisoformat(fetched_at_str)
            age = datetime.now() - fetched_at
            return age < timedelta(hours=24)
        except (ValueError, TypeError):
            return False

    async def _search_strategy(
        self, query: str, match_time: datetime, sort: str = "relevance"
    ) -> dict | None:
        """
        Execute a single search strategy with optional BrightData fallback.

        First tries direct Reddit API (free), then falls back to BrightData if:
        - BRIGHTDATA_API_TOKEN is set
        - Direct request returns 403 or fails

        Args:
            query: Search query
            match_time: Match start time for filtering
            sort: Sort order (relevance, top, new)

        Returns:
            Dict with url, title, post_url if found, else None
        """
        import urllib.parse

        # Build search URL
        start_time = int((match_time - timedelta(hours=12)).timestamp())
        end_time = int((match_time + timedelta(hours=12)).timestamp())

        # Properly encode the query parameters
        search_query = f"{query} flair:Media timestamp:{start_time}..{end_time}"
        encoded_query = urllib.parse.quote(search_query)

        url = (
            f"https://www.reddit.com/r/soccer/search.json?"
            f"q={encoded_query}"
            f"&restrict_sr=on&sort={sort}&limit=15"
        )

        logger.info(f"Searching Reddit with URL: {url}")

        # Try 1: Direct Reddit API (always try this first)
        result = await self._try_direct_reddit(url, query)
        if result is not None:
            return result

        # Try 2: BrightData fallback (only if token is configured)
        if self.brightdata_enabled:
            logger.info(f"Trying BrightData fallback for query: {query}")
            return await self._try_brightdata(url, query, match_time)
        else:
            logger.debug(
                f"BrightData not configured, no fallback available for query: {query}"
            )
            return None

    async def _try_direct_reddit(self, url: str, query: str) -> dict | None:
        """
        Try direct Reddit API request.

        Args:
            url: Full Reddit search URL
            query: Search query (for logging)

        Returns:
            Dict with url, title, post_url if found, else None
        """
        await self._rate_limit()

        try:
            if not self.session or self.session.closed:
                await self._ensure_session()

            async with self.session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    logger.debug(f"Direct Reddit API succeeded for query: {query}")
                    data = await response.json()
                    return self._parse_reddit_response(data)
                elif response.status == 403:
                    logger.warning(
                        f"Direct Reddit API returned 403 (Forbidden) for query: {query}"
                    )
                    return None
                else:
                    logger.warning(
                        f"Reddit search returned status {response.status} for query: {query}"
                    )
                    return None

        except TimeoutError:
            logger.warning(f"Reddit search timed out for query: {query}")
            return None
        except Exception as e:
            logger.debug(f"Direct Reddit API failed for query '{query}': {e}")
            return None

    async def _try_brightdata(
        self, url: str, query: str, match_time: datetime
    ) -> dict | None:
        """
        Try BrightData Reddit scraper as fallback.

        Uses BrightData's dedicated Reddit scraper instead of generic scraping.

        Args:
            url: Full Reddit search URL (for reference, not used directly)
            query: Search query
            match_time: Match start time for filtering results

        Returns:
            Dict with url, title, post_url if found, else None
        """
        try:
            async with self.BrightDataClient() as client:
                # Use BrightData's Reddit scraper with keyword search on r/soccer
                # Add "r/soccer" to the query to limit to that subreddit
                search_query = f"r/soccer {query}"

                # Determine time filter based on how recent the match is
                now = datetime.now()
                match_age = now - match_time

                if match_age < timedelta(hours=1):
                    date_filter = "Past hour"
                elif match_age < timedelta(hours=24):
                    date_filter = "Past 24 hours"
                elif match_age < timedelta(days=7):
                    date_filter = "Past week"
                elif match_age < timedelta(days=30):
                    date_filter = "Past month"
                else:
                    date_filter = "Past year"

                logger.info(
                    f"Using BrightData Reddit scraper with query: {search_query}, time filter: {date_filter}"
                )

                result = await client.scrape.reddit.posts_by_keyword(
                    keyword=search_query,
                    date=date_filter,
                    sort_by="Relevance",
                    num_of_posts=15,  # Limit to 15 posts like the API
                    timeout=60,
                )

                logger.debug(f"BrightData result object: {result}")
                logger.debug(f"BrightData result.data type: {type(result.data)}")
                logger.debug(
                    f"BrightData result.error: {getattr(result, 'error', 'N/A')}"
                )

                data = result.data

                if not data:
                    logger.warning(f"BrightData returned no data for query: {query}")
                    return None

                # BrightData Reddit scraper returns a list of post objects
                if isinstance(data, list):
                    logger.info(
                        f"BrightData succeeded for query: {query}, got {len(data)} posts"
                    )

                    # Define time window (±12 hours from match time, same as direct API)
                    start_time = match_time - timedelta(hours=12)
                    end_time = match_time + timedelta(hours=12)

                    # Search through the posts for one with Media flair and within time window
                    for post in data:
                        if not isinstance(post, dict):
                            continue

                        # Check if this is a Media post
                        flair = post.get("flair_text", post.get("link_flair_text", ""))
                        if flair != "Media":
                            continue

                        # Filter by post time if available
                        # BrightData may include 'created_utc' or 'created' timestamp
                        post_time = post.get("created_utc", post.get("created"))
                        if post_time:
                            # Convert to datetime if it's a timestamp
                            if isinstance(post_time, (int, float)):
                                post_datetime = datetime.fromtimestamp(post_time)
                            elif isinstance(post_time, str):
                                try:
                                    post_datetime = datetime.fromisoformat(
                                        post_time.replace("Z", "+00:00")
                                    )
                                except ValueError:
                                    post_datetime = None
                            else:
                                post_datetime = None

                            # Skip posts outside the time window
                            if post_datetime and (
                                post_datetime < start_time or post_datetime > end_time
                            ):
                                logger.debug(
                                    f"Skipping post outside time window: {post.get('title', 'N/A')}"
                                )
                                continue

                        # Get the video/media URL
                        media_url = post.get("url", "")
                        permalink = post.get("permalink", "")
                        title = post.get("title", "")

                        # Build full post URL if we only have permalink
                        if permalink and not permalink.startswith("http"):
                            post_url = f"https://www.reddit.com{permalink}"
                        else:
                            post_url = permalink

                        # Try to get Reddit video URL if available
                        if "secure_media" in post and post["secure_media"]:
                            reddit_video = post["secure_media"].get("reddit_video", {})
                            fallback_url = reddit_video.get("fallback_url")
                            if fallback_url:
                                media_url = fallback_url

                        if media_url and title:
                            logger.info(f"Found Reddit clip via BrightData: {title}")
                            return {
                                "url": media_url,
                                "title": title,
                                "post_url": post_url,
                            }

                    logger.warning(
                        f"BrightData returned {len(data)} posts but none with Media flair"
                    )
                    return None
                else:
                    logger.warning(
                        f"BrightData returned unexpected data type: {type(data)}"
                    )
                    return None

        except Exception as e:
            logger.error(f"BrightData Reddit scraper failed for query '{query}': {e}")
            import traceback

            logger.error(traceback.format_exc())
            return None

    def _parse_reddit_response(self, data: dict) -> dict | None:
        """
        Parse Reddit API response (works for both direct and BrightData).

        Args:
            data: JSON response from Reddit API

        Returns:
            Dict with url, title, post_url if found, else None
        """
        posts = data.get("data", {}).get("children", [])

        for post in posts:
            post_data = post.get("data", {})

            # Only consider Media flair posts
            if post_data.get("link_flair_text") != "Media":
                continue

            # Get the video/media URL
            media_url = post_data.get("url", "")
            post_url = "https://www.reddit.com" + post_data.get("permalink", "")
            title = post_data.get("title", "")

            # Try to get Reddit video fallback URL if available
            secure_media = post_data.get("secure_media")
            if secure_media and isinstance(secure_media, dict):
                reddit_video = secure_media.get("reddit_video")
                if reddit_video and isinstance(reddit_video, dict):
                    fallback_url = reddit_video.get("fallback_url")
                    if fallback_url:
                        media_url = fallback_url

            if media_url and title:
                logger.info(f"Found Reddit clip: {title}")
                return {
                    "url": media_url,
                    "title": title,
                    "post_url": post_url,
                }

        return None

    async def fetch_multiple_goals(
        self, goals: list[dict], timeout: float = 5.0
    ) -> dict[str, dict | None]:
        """
        Fetch Reddit clips for multiple goals with timeout.

        Args:
            goals: List of goal dicts with keys: home_team, away_team, minute,
                   match_time, scoring_team, home_score, away_score
            timeout: Timeout per goal search in seconds

        Returns:
            Dict mapping "match_id:minute" to result dict or None
        """
        results = {}

        for goal in goals:
            cache_key = f"{goal['home_team']}:{goal['away_team']}:{goal['minute']}"

            try:
                result = await asyncio.wait_for(
                    self.search_goal(
                        home_team=goal["home_team"],
                        away_team=goal["away_team"],
                        minute=goal["minute"],
                        match_time=goal["match_time"],
                        scoring_team=goal["scoring_team"],
                        home_score=goal["home_score"],
                        away_score=goal["away_score"],
                    ),
                    timeout=timeout,
                )
                results[cache_key] = result
            except TimeoutError:
                logger.warning(f"Reddit search timed out for goal at {goal['minute']}'")
                results[cache_key] = None
            except Exception as e:
                logger.error(f"Failed to fetch Reddit clip: {e}")
                results[cache_key] = None

            # Small delay between goals to respect rate limits
            await asyncio.sleep(1.0)

        return results
