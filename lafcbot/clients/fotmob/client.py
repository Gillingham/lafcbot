"""FotMob API client for fetching match and league data."""

import asyncio
import hashlib
import json
import logging
import os
import time
from base64 import b64encode
from datetime import date, datetime

import aiohttp

from .constants import (
    BASE_URL,
    CONNECTION_KEEPALIVE_TIMEOUT,
    CONNECTION_POOL_PER_HOST,
    CONNECTION_POOL_SIZE,
    HEADERS,
    MAX_RETRIES,
    REQUEST_DELAY,
    RETRY_DELAY,
)
from .models import (
    BroadcastChannel,
    Highlight,
    Match,
    MatchDetails,
    MatchEvent,
    PenaltyKick,
    PenaltyShootout,
    PlayerStat,
    Team,
    Venue,
)
from .parser import extract_broadcast_channels, extract_page_props

logger = logging.getLogger(__name__)

# FotMob's authentication secret - "Three Lions (Football's Coming Home)" lyrics
FOTMOB_SECRET = """[Spoken Intro: Alan Hansen & Trevor Brooking]
I think it's bad news for the English game
We're not creative enough, and we're not positive enough

[Refrain: Ian Broudie & Jimmy Hill]
It's coming home, it's coming home, it's coming
Football's coming home (We'll go on getting bad results)
It's coming home, it's coming home, it's coming
Football's coming home
It's coming home, it's coming home, it's coming
Football's coming home
It's coming home, it's coming home, it's coming
Football's coming home

[Verse 1: Frank Skinner]
Everyone seems to know the score, they've seen it all before
They just know, they're so sure
That England's gonna throw it away, gonna blow it away
But I know they can play, 'cause I remember

[Chorus: All]
Three lions on a shirt
Jules Rimet still gleaming
Thirty years of hurt
Never stopped me dreaming

[Verse 2: David Baddiel]
So many jokes, so many sneers
But all those "Oh, so near"s wear you down through the years
But I still see that tackle by Moore and when Lineker scored
Bobby belting the ball, and Nobby dancing

[Chorus: All]
Three lions on a shirt
Jules Rimet still gleaming
Thirty years of hurt
Never stopped me dreaming

[Bridge]
England have done it, in the last minute of extra time!
What a save, Gordon Banks!
Good old England, England that couldn't play football!
England have got it in the bag!
I know that was then, but it could be again

[Refrain: Ian Broudie]
It's coming home, it's coming
Football's coming home
It's coming home, it's coming home, it's coming
Football's coming home
(England have done it!)
It's coming home, it's coming home, it's coming
Football's coming home
It's coming home, it's coming home, it's coming
Football's coming home
[Chorus: All]
(It's coming home) Three lions on a shirt
(It's coming home, it's coming) Jules Rimet still gleaming
(Football's coming home
It's coming home) Thirty years of hurt
(It's coming home, it's coming) Never stopped me dreaming
(Football's coming home
It's coming home) Three lions on a shirt
(It's coming home, it's coming) Jules Rimet still gleaming
(Football's coming home
It's coming home) Thirty years of hurt
(It's coming home, it's coming) Never stopped me dreaming
(Football's coming home
It's coming home) Three lions on a shirt
(It's coming home, it's coming) Jules Rimet still gleaming
(Football's coming home
It's coming home) Thirty years of hurt
(It's coming home, it's coming) Never stopped me dreaming
(Football's coming home)"""


def generate_xmas_token(api_path: str) -> str:
    """
    Generate FotMob's x-mas authentication token.

    This token is required for the authenticated /api/data/* endpoints
    and may provide fresher data with better cache-busting.

    Args:
        api_path: The API path (e.g., "/api/data/matchDetails?matchId=123")

    Returns:
        Base64-encoded authentication token
    """
    # Current timestamp in milliseconds
    timestamp_code = int(time.time() * 1000)

    # Build body structure
    body = {
        "url": api_path,
        "code": timestamp_code,
        "foo": "production:33324f727a7a2706a154eab6f683920b1df36aee",
    }

    # Create JSON string (compact format, no spaces)
    body_json = json.dumps(body, separators=(",", ":"))

    # Calculate MD5 signature: MD5(json_body + secret_lyrics)
    combined = body_json + FOTMOB_SECRET
    md5_hash = hashlib.md5(combined.encode()).hexdigest().upper()

    # Build final token structure
    token_data = {
        "body": body,
        "signature": md5_hash,
    }

    # Encode as base64
    token_json = json.dumps(token_data, separators=(",", ":"))
    token = b64encode(token_json.encode()).decode()

    return token


class FotMobClient:
    """
    Async client for fetching soccer match data from FotMob.

    This client implements both API endpoint access and HTML scraping
    with automatic fallback when Cloudflare protection blocks API access.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        match_output_path: str | None = None,
    ):
        """
        Initialize the FotMob client.

        Args:
            session: Optional aiohttp session. If not provided, a new one
                    will be created and managed by this client.
            match_output_path: Optional directory path to write match JSON dumps.
                             If None, no dumps are written.
        """
        self._session = session
        self._owns_session = session is None
        self._last_request_time = 0.0
        self._page_slugs: dict[int, str] = {}
        self._match_details_cache: dict[int, tuple[float, MatchDetails]] = {}
        self._etag_cache: dict[int, str] = {}  # For HTTP caching with authenticated API
        self._match_output_path = match_output_path

    async def __aenter__(self):
        if self._session is None:
            # Configure connection pooling (matching golazo's settings)
            connector = aiohttp.TCPConnector(
                limit=CONNECTION_POOL_SIZE,  # Total connection pool size
                limit_per_host=CONNECTION_POOL_PER_HOST,  # Per-host limit
                ttl_dns_cache=300,  # DNS cache for 5 minutes
                keepalive_timeout=CONNECTION_KEEPALIVE_TIMEOUT,  # Keep connections alive
            )
            self._session = aiohttp.ClientSession(
                headers=HEADERS,
                connector=connector,
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close the HTTP session if owned by this client."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def _rate_limit(self):
        """Apply rate limiting between requests."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < REQUEST_DELAY:
            await asyncio.sleep(REQUEST_DELAY - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _request_with_retry(
        self, url: str, method: str = "GET", headers: dict | None = None, **kwargs
    ) -> bytes | None:
        """
        Make an HTTP request with exponential backoff retry logic.

        Args:
            url: The URL to request
            method: HTTP method (default: GET)
            **kwargs: Additional arguments to pass to the request

        Returns:
            The response body as bytes, or None if all retries failed
        """
        if self._session is None:
            # Configure connection pooling
            connector = aiohttp.TCPConnector(
                limit=CONNECTION_POOL_SIZE,
                limit_per_host=CONNECTION_POOL_PER_HOST,
                ttl_dns_cache=300,
                keepalive_timeout=CONNECTION_KEEPALIVE_TIMEOUT,
            )
            self._session = aiohttp.ClientSession(
                headers=HEADERS,
                connector=connector,
            )
            self._owns_session = True

        request_headers = HEADERS.copy()
        if headers:
            request_headers.update(headers)

        await self._rate_limit()

        for attempt in range(MAX_RETRIES):
            try:
                async with self._session.request(
                    method, url, headers=request_headers, **kwargs
                ) as response:
                    if response.status == 200:
                        return await response.read()
                    elif response.status == 403:
                        logger.warning(
                            f"Got 403 for {url}, may need to use scraping fallback"
                        )
                        return None
                    else:
                        logger.warning(
                            f"Request to {url} returned status {response.status}"
                        )
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            except Exception as e:
                logger.error(f"Request to {url} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))

        return None

    async def _fetch_api_endpoint(
        self, endpoint: str, cache_bust: bool = False
    ) -> dict | None:
        """
        Fetch data from a FotMob API endpoint.

        Args:
            endpoint: API endpoint path (e.g., "/api/matchDetails?matchId=123")
            cache_bust: Whether to add cache-busting headers and parameters.

        Returns:
            Parsed JSON response, or None if request failed
        """
        url = f"{BASE_URL}{endpoint}"
        headers = None
        if cache_bust:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}_cb={int(time.time())}"
            headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}

        response_body = await self._request_with_retry(url, headers=headers)

        if response_body:
            try:
                import json

                return json.loads(response_body.decode("utf-8"))
            except Exception as e:
                logger.error(f"Failed to parse JSON from {url}: {e}")

        return None

    async def _fetch_page_html(
        self, page_path: str, cache_bust: bool = False
    ) -> str | None:
        """
        Fetch HTML from a FotMob page.

        Args:
            page_path: Page path (e.g., "/leagues/130")
            cache_bust: Whether to add cache-busting headers and parameters.

        Returns:
            Raw HTML content, or None if request failed
        """
        url = f"{BASE_URL}{page_path}"
        headers = None
        if cache_bust:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}_cb={int(time.time())}"
            headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}

        response_body = await self._request_with_retry(url, headers=headers)

        if response_body:
            try:
                return response_body.decode("utf-8")
            except Exception as e:
                logger.error(f"Failed to decode HTML from {url}: {e}")

        return None

    async def get_matches_by_date(
        self, target_date: str | None = None, league_ids: list[int] | None = None
    ) -> list[Match]:
        """
        Get matches for a specific date and leagues.

        Args:
            target_date: Date in YYYY-MM-DD format (default: today)
            league_ids: List of league IDs to filter (default: all leagues)

        Returns:
            List of Match objects
        """
        if target_date is None:
            target_date = date.today().isoformat()

        if league_ids is None:
            league_ids = [130]  # Default to MLS

        league_ids_str = ",".join(str(lid) for lid in league_ids)
        endpoint = f"/api/leagues?leagueIds={league_ids_str}&tab=fixtures,results&date={target_date}"

        data = await self._fetch_api_endpoint(endpoint)
        if data is None:
            logger.warning(
                "API endpoint failed for matches by date, attempting page scraping"
            )
            return []

        return self._parse_matches_from_api(data)

    async def get_match_details_authenticated(
        self,
        match_id: int,
        force_refresh: bool = False,
    ) -> MatchDetails | None:
        """
        Get detailed match information using FotMob's authenticated API endpoint.

        This uses the same endpoint as FotMob's web frontend with x-mas authentication,
        which may provide fresher data and better cache-busting than the legacy endpoints.

        Args:
            match_id: Match ID
            force_refresh: If True, bypass internal cache (still sends ETag for HTTP caching)

        Returns:
            MatchDetails object, or None if fetch failed
        """
        if not force_refresh and match_id in self._match_details_cache:
            timestamp, details = self._match_details_cache[match_id]
            if asyncio.get_event_loop().time() - timestamp < 30:
                logger.debug(f"Returning cached details for match {match_id}")
                return details

        # Build authenticated API path
        api_path = f"/api/data/matchDetails?matchId={match_id}"
        url = f"{BASE_URL}{api_path}"

        # Generate authentication token
        xmas_token = generate_xmas_token(api_path)

        # Build headers with authentication
        headers = HEADERS.copy()
        headers["x-mas"] = xmas_token
        headers["Referer"] = f"{BASE_URL}/matches/{match_id}"

        # Add ETag for HTTP caching (304 Not Modified responses)
        if match_id in self._etag_cache:
            headers["If-None-Match"] = self._etag_cache[match_id]

        await self._rate_limit()

        try:
            if self._session is None:
                # Configure connection pooling
                connector = aiohttp.TCPConnector(
                    limit=CONNECTION_POOL_SIZE,
                    limit_per_host=CONNECTION_POOL_PER_HOST,
                    ttl_dns_cache=300,
                    keepalive_timeout=CONNECTION_KEEPALIVE_TIMEOUT,
                )
                self._session = aiohttp.ClientSession(
                    headers=HEADERS,
                    connector=connector,
                )
                self._owns_session = True

            async with self._session.get(url, headers=headers) as response:
                # Handle 304 Not Modified - data unchanged since last request
                if response.status == 304:
                    logger.debug(
                        f"Match {match_id} not modified (304), using cached data"
                    )
                    if match_id in self._match_details_cache:
                        return self._match_details_cache[match_id][1]
                    # No cached data but got 304? Fall back to regular method
                    logger.warning(f"Got 304 for match {match_id} but no cached data")
                    return await self.get_match_details(
                        match_id=match_id, force_refresh=True
                    )

                if response.status == 200:
                    # Store ETag for next request
                    if "ETag" in response.headers:
                        self._etag_cache[match_id] = response.headers["ETag"]
                        logger.debug(f"Stored ETag for match {match_id}")

                    data = await response.json()

                    # Parse match details
                    details = self._parse_match_details_from_api(data)

                    if details and match_id:
                        # Update cache
                        self._match_details_cache[match_id] = (
                            asyncio.get_event_loop().time(),
                            details,
                        )

                    return details
                elif response.status == 403 or response.status == 401:
                    logger.warning(
                        f"Authentication failed for match {match_id} (status {response.status}), "
                        "falling back to unauthenticated method"
                    )
                    return await self.get_match_details(
                        match_id=match_id, force_refresh=force_refresh
                    )
                else:
                    logger.warning(
                        f"Authenticated request to {url} returned status {response.status}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Authenticated request to {url} failed: {e}")
            # Fall back to unauthenticated method on error
            logger.info(f"Falling back to unauthenticated method for match {match_id}")
            return await self.get_match_details(
                match_id=match_id, force_refresh=force_refresh
            )

    async def get_match_details(
        self,
        match_id: int | None = None,
        page_slug: str | None = None,
        force_refresh: bool = False,
    ) -> MatchDetails | None:
        """
        Get detailed information about a specific match.

        Args:
            match_id: Match ID (for API endpoint method)
            page_slug: Page slug like "/matches/team1-vs-team2/abc123" (for scraping method)
            force_refresh: If True, bypass the internal cache.

        Returns:
            MatchDetails object, or None if fetch failed
        """
        if not force_refresh and match_id in self._match_details_cache:
            timestamp, details = self._match_details_cache[match_id]
            if asyncio.get_event_loop().time() - timestamp < 30:
                logger.debug(f"Returning cached details for match {match_id}")
                return details

        # Prefer scraping the HTML page slug first, then fallback to
        # trying known match page URL patterns, and finally try API endpoints.
        if page_slug is None and match_id is not None:
            page_slug = self._page_slugs.get(match_id)

        if page_slug is not None:
            html = await self._fetch_page_html(page_slug, cache_bust=force_refresh)
            if html:
                page_props = extract_page_props(html)
                if page_props:
                    # Dump JSON for analysis if match_id and output path provided
                    if match_id and self._match_output_path:
                        os.makedirs(self._match_output_path, exist_ok=True)
                        dump_path = os.path.join(
                            self._match_output_path, f"match_{match_id}_dump.json"
                        )
                        try:
                            with open(dump_path, "w") as f:
                                json.dump(page_props, f, indent=2)
                        except Exception as e:
                            logger.error(f"Failed to dump match JSON: {e}")
                    broadcast_channels_data = extract_broadcast_channels(html)
                    try:
                        details = self._parse_match_details_from_page(
                            page_props, broadcast_channels_data
                        )
                        if details and match_id:
                            self._match_details_cache[match_id] = (
                                asyncio.get_event_loop().time(),
                                details,
                            )
                        return details
                    except Exception as e:
                        import traceback

                        logger.error(
                            f"Failed to parse match details from page_slug: {e}\n{traceback.format_exc()}"
                        )

        # If we have a match_id, try common match page paths first when no page slug is available
        if match_id is not None:
            possible_paths = [
                f"/matches/{match_id}",
                f"/match/{match_id}",
                f"/m/{match_id}",
                f"/matches/{match_id}/",
            ]
            for path in possible_paths:
                html = await self._fetch_page_html(path, cache_bust=force_refresh)
                if not html:
                    logger.debug(f"No HTML at fallback path: {path}")
                    continue

                page_props = extract_page_props(html)
                if page_props:
                    broadcast_channels_data = extract_broadcast_channels(html)
                    try:
                        logger.debug(f"Extracted page props from fallback path: {path}")
                        # Store the successful path for future use to avoid discovery loop
                        if match_id:
                            self._page_slugs[match_id] = path
                        details = self._parse_match_details_from_page(
                            page_props, broadcast_channels_data
                        )
                        if details and match_id:
                            self._match_details_cache[match_id] = (
                                asyncio.get_event_loop().time(),
                                details,
                            )
                        return details
                    except Exception as e:
                        import traceback

                        logger.error(
                            f"Failed to parse match details from page {path}: {e}\n{traceback.format_exc()}"
                        )

        # Last resort: try API endpoints (legacy behavior)
        if match_id is not None:
            api_endpoints = [
                f"/api/matchDetails?matchId={match_id}",
                f"/api/match?matchId={match_id}",
                f"/api/match?match_id={match_id}",
                f"/api/matchDetails?match_id={match_id}",
            ]

            data = None
            for endpoint in api_endpoints:
                data = await self._fetch_api_endpoint(
                    endpoint, cache_bust=force_refresh
                )
                if data:
                    logger.debug(f"FotMob API returned data for endpoint: {endpoint}")
                    break
                else:
                    logger.debug(f"No data from FotMob API endpoint: {endpoint}")

            if data:
                try:
                    # Dump JSON for analysis if output path provided
                    if self._match_output_path:
                        os.makedirs(self._match_output_path, exist_ok=True)
                        dump_path = os.path.join(
                            self._match_output_path, f"match_{match_id}_dump.json"
                        )
                        try:
                            with open(dump_path, "w") as f:
                                json.dump(data, f, indent=2)
                        except Exception as e:
                            logger.error(f"Failed to dump match JSON: {e}")
                    details = self._parse_match_details_from_api(data)
                    if details and match_id:
                        self._match_details_cache[match_id] = (
                            asyncio.get_event_loop().time(),
                            details,
                        )
                    return details
                except Exception as e:
                    logger.error(
                        f"Failed to parse match details from API for {match_id}: {e}"
                    )

        return None

    async def get_league_matches(self, league_id: int) -> list[Match]:
        """
        Get all matches for a specific league.

        Args:
            league_id: The league ID (e.g., 130 for MLS)

        Returns:
            List of Match objects
        """
        html = await self._fetch_page_html(f"/leagues/{league_id}", cache_bust=True)
        if html:
            page_props = extract_page_props(html)
            if page_props:
                return self._parse_matches_from_league_page(page_props)

        return []

    async def get_league_standings(self, league_id: int) -> dict | None:
        """
        Get league standings/table.

        Args:
            league_id: The league ID

        Returns:
            Dictionary with standings data, or None if fetch failed
        """
        # Try authenticated endpoint first (like matchDetails)
        api_path = f"/api/leagues?id={league_id}&tab=table"
        url = f"{BASE_URL}{api_path}"

        # Generate authentication token
        xmas_token = generate_xmas_token(api_path)

        # Build headers with authentication
        headers = HEADERS.copy()
        headers["x-mas"] = xmas_token
        headers["Referer"] = f"{BASE_URL}/leagues/{league_id}"

        await self._rate_limit()

        try:
            if self._session is None:
                connector = aiohttp.TCPConnector(
                    limit=CONNECTION_POOL_SIZE,
                    limit_per_host=CONNECTION_POOL_PER_HOST,
                    ttl_dns_cache=300,
                    keepalive_timeout=CONNECTION_KEEPALIVE_TIMEOUT,
                )
                self._session = aiohttp.ClientSession(connector=connector)

            async with self._session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        return data.get("table", {})
                elif response.status != 404:
                    logger.warning(
                        f"Request to {url} returned status {response.status}"
                    )
        except Exception as e:
            logger.error(f"Error fetching authenticated standings: {e}")

        # Fallback to page scraping
        logger.debug(f"Falling back to page scraping for league {league_id} standings")
        html = await self._fetch_page_html(f"/leagues/{league_id}")
        if html:
            page_props = extract_page_props(html)
            if page_props:
                return page_props.get("table", {})

        return None

    async def get_live_world_cup_matches(self) -> list[Match]:
        """
        Get all currently live World Cup matches.

        Returns:
            List of live Match objects for World Cup (league ID 77)
        """
        # World Cup league ID
        world_cup_id = 77

        # Get all World Cup matches
        all_matches = await self.get_league_matches(world_cup_id)

        # Filter for only live matches
        live_matches = [m for m in all_matches if m.is_live]

        return live_matches

    def _parse_matches_from_api(self, data: dict) -> list[Match]:
        """Parse matches from API response."""
        matches = []

        leagues = data.get("leagues", [])
        for league_data in leagues:
            league_id = league_data.get("id")
            league_name = league_data.get("name")

            for match_data in league_data.get("matches", []):
                try:
                    match = self._parse_match_from_dict(
                        match_data, league_id, league_name
                    )
                    matches.append(match)
                except Exception as e:
                    logger.error(f"Failed to parse match: {e}")

        return matches

    def _parse_match_from_dict(
        self,
        data: dict,
        league_id: int | None = None,
        league_name: str | None = None,
    ) -> Match:
        """Parse a single match from a dictionary."""
        home_team = Team(
            id=data.get("home", {}).get("id", 0),
            name=data.get("home", {}).get("name", "Unknown"),
            logo_url=data.get("home", {}).get("imageUrl"),
        )

        away_team = Team(
            id=data.get("away", {}).get("id", 0),
            name=data.get("away", {}).get("name", "Unknown"),
            logo_url=data.get("away", {}).get("imageUrl"),
        )

        status_obj = data.get("status", {})

        # Extract match time display (e.g., "45'+2", "88'", "FT")
        match_time_display = None

        # First, check for live time (actual minute) which is most reliable for live matches
        if "liveTime" in status_obj and isinstance(status_obj["liveTime"], dict):
            live_time = status_obj["liveTime"]
            minute = live_time.get("short")
            if minute:
                match_time_display = minute

        # Determine match state from reason field
        if "reason" in status_obj and isinstance(status_obj["reason"], dict):
            short_status = status_obj["reason"].get("short", "")

            # Determine match state
            if short_status.lower() in ("ft", "fulltime", "finished"):
                status = "finished"
                if not match_time_display:
                    match_time_display = "FT"
            elif short_status.lower() in ("ht", "halftime"):
                status = "live"
                # Only use "HT" if we don't have an actual minute
                if not match_time_display:
                    match_time_display = "HT"
            elif short_status:
                status = "live"
            else:
                status = "upcoming"
        # Fallback to finished/started boolean flags
        elif status_obj.get("finished"):
            status = "finished"
            if not match_time_display:
                match_time_display = "FT"
        elif status_obj.get("started"):
            status = "live"
        else:
            status = "upcoming"

        # Try multiple fields for start time
        start_time_str = status_obj.get("utcTime") or status_obj.get("startTimeUtc")
        start_time = None
        if start_time_str:
            try:
                start_time = datetime.fromisoformat(
                    start_time_str.replace("Z", "+00:00")
                )
            except Exception:
                pass

        # Parse scores - try individual fields first, then scoreStr
        home_score = data.get("home", {}).get("score")
        away_score = data.get("away", {}).get("score")

        if home_score is None and away_score is None:
            score_str = status_obj.get("scoreStr", "")
            if score_str and "-" in score_str:
                try:
                    parts = score_str.split("-")
                    home_score = int(parts[0].strip())
                    away_score = int(parts[1].strip())
                except (ValueError, IndexError):
                    pass

        match = Match(
            id=int(data.get("id", 0)),
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            status=status,
            start_time=start_time,
            league_id=league_id,
            league_name=league_name,
            page_slug=data.get("pageUrl"),
            match_time_display=match_time_display,
        )
        if match.page_slug:
            self._page_slugs[match.id] = match.page_slug
        return match

    def _parse_match_details_from_api(self, data: dict) -> MatchDetails:
        """Parse match details from API response or page props."""
        general = data.get("general", {})

        home_team = Team(
            id=general.get("homeTeam", {}).get("id", 0),
            name=general.get("homeTeam", {}).get("name", "Unknown"),
        )

        away_team = Team(
            id=general.get("awayTeam", {}).get("id", 0),
            name=general.get("awayTeam", {}).get("name", "Unknown"),
        )

        status = (
            "finished"
            if general.get("finished")
            else "live"
            if general.get("started")
            else "upcoming"
        )

        # Parse start time from matchTimeUTCDate
        start_time = None
        start_time_str = general.get("matchTimeUTCDate")
        if start_time_str:
            try:
                start_time = datetime.fromisoformat(
                    start_time_str.replace("Z", "+00:00")
                )
            except Exception:
                pass

        # Parse venue from infoBox
        venue = None
        info_box = data.get("content", {}).get("matchFacts", {}).get("infoBox", {})
        stadium_data = info_box.get("Stadium", {})
        if stadium_data and isinstance(stadium_data, dict):
            venue = Venue(
                name=stadium_data.get("name", "Unknown"),
                city=stadium_data.get("city"),
                country=stadium_data.get("country"),
                capacity=stadium_data.get("capacity"),
            )

        # Parse scores from general section or header
        home_score = None
        away_score = None

        # Try general section first
        if "homeTeam" in general and "score" in general.get("homeTeam", {}):
            home_score = general["homeTeam"]["score"]
        if "awayTeam" in general and "score" in general.get("awayTeam", {}):
            away_score = general["awayTeam"]["score"]

        # Try header section as fallback
        if home_score is None or away_score is None:
            header = data.get("header", {})
            teams_data = header.get("teams", [])
            if len(teams_data) >= 2:
                home_score = teams_data[0].get("score")
                away_score = teams_data[1].get("score")

        # Parse match time display for live matches
        match_time_display = None
        if status == "live":
            # Try to get from header status
            header = data.get("header", {})
            status_obj = header.get("status", {})
            if isinstance(status_obj, dict):
                match_time_display = status_obj.get("liveTime", {}).get("short")
                if not match_time_display:
                    reason = status_obj.get("reason", {})
                    if isinstance(reason, dict):
                        match_time_display = reason.get("short")

        match = Match(
            id=int(general.get("matchId", 0)),
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            status=status,
            start_time=start_time,
            league_id=general.get("parentLeagueId"),
            league_name=general.get("leagueName"),
            page_slug=None,
            venue=venue,
            match_time_display=match_time_display,
        )

        events = []
        events_obj = data.get("content", {}).get("matchFacts", {}).get("events") or {}
        for event_data in events_obj.get("events") or []:
            # Extract assist for goals
            assist_name = None
            if event_data.get("type") == "Goal":
                assist_data = event_data.get("assist")
                if assist_data:
                    if isinstance(assist_data, dict):
                        assist_name = assist_data.get("name")
                    elif isinstance(assist_data, str):
                        assist_name = assist_data

            # Normalize type and handle special event fields.
            raw_type = event_data.get("type", "unknown")
            raw_type_lower = str(raw_type).lower()
            description = event_data.get("text")
            half_type_val = None
            player_in = None
            player_out = None

            card_field = event_data.get("card")
            card_color_val = None
            if card_field:
                try:
                    card_color_val = str(card_field).lower()
                except Exception:
                    card_color_val = None

            swap = event_data.get("swap")
            is_substitution = (
                swap and isinstance(swap, list) and len(swap) >= 2
            ) or raw_type_lower in ("substitution", "sub")

            if card_color_val:
                event_type = "card"
                desc_parts = []
                if description:
                    desc_parts.append(description)
                desc_parts.append(str(card_field))
                description = " ".join(desc_parts)
            elif is_substitution:
                event_type = "substitution"
                if swap and isinstance(swap, list) and len(swap) >= 2:
                    try:
                        player_in = (
                            swap[0].get("name")
                            if isinstance(swap[0], dict)
                            else str(swap[0])
                        )
                        player_out = (
                            swap[1].get("name")
                            if isinstance(swap[1], dict)
                            else str(swap[1])
                        )
                        if player_in and player_out:
                            description = f"{player_in} on for {player_out}"
                    except Exception:
                        pass
            elif raw_type_lower in ("half", "ht", "ft", "periodend"):
                event_type = "half"
                half_type_val = event_data.get("halfStrShort") or (
                    "HT"
                    if raw_type_lower == "ht"
                    else "FT"
                    if raw_type_lower == "ft"
                    else None
                )
            else:
                event_type = raw_type

            own_goal_flag = event_data.get("ownGoal", False)

            # Determine team_id - if teamId is null/0, use isHome to infer it
            team_id = event_data.get("teamId")
            if not team_id or team_id == 0:
                # Use isHome field to determine team
                is_home = event_data.get("isHome")
                if is_home is True:
                    team_id = home_team.id
                elif is_home is False:
                    team_id = away_team.id
                else:
                    team_id = 0  # Fallback if isHome is also missing

            events.append(
                MatchEvent(
                    id=event_data.get("eventId", event_data.get("id", 0)),
                    type=event_type,
                    minute=event_data.get("time", 0),
                    added_time=event_data.get("overloadTime"),
                    team_id=team_id,
                    player_name=(
                        player_out
                        if player_out
                        else (
                            event_data.get("player", {}).get("name")
                            if isinstance(event_data.get("player"), dict)
                            else event_data.get("player")
                        )
                    ),
                    assist_name=(player_in if player_in else assist_name),
                    description=description,
                    own_goal=own_goal_flag or False,
                    card_color=card_color_val,
                    half_type=half_type_val,
                    var_decision=event_data.get("VAR") if event_type == "VAR" else None,
                    goal_description_key=event_data.get("goalDescriptionKey"),
                    shotmap_event=event_data.get("shotmapEvent"),
                )
            )

        stats = data.get("content", {}).get("stats", {})
        lineups = data.get("content", {}).get("lineup", {})

        # Parse highlight video
        highlight = None
        highlight_data = data.get("content", {}).get("highlightVideo")
        if highlight_data and isinstance(highlight_data, dict):
            highlight_url = highlight_data.get("url")
            if highlight_url:
                highlight = Highlight(
                    url=highlight_url, title=highlight_data.get("title")
                )

        # Check for extra time
        # FotMob sets extraTime/hasExtraTime only after extra time completes.
        # During extra time, check if firstExtraHalfStarted is set in header.status.halfs
        extra_time = general.get("extraTime", False) or general.get(
            "hasExtraTime", False
        )

        # Also check if currently in extra time (live match with firstExtraHalfStarted set)
        if not extra_time and status == "live":
            header = data.get("header", {})
            status_obj = header.get("status", {})
            if isinstance(status_obj, dict):
                halfs = status_obj.get("halfs", {})
                if isinstance(halfs, dict):
                    first_extra = halfs.get("firstExtraHalfStarted", "")
                    if first_extra:
                        extra_time = True

        # Parse individual penalty kicks from penaltyShootoutEvents
        penalty_kicks = []
        penalties = None
        events_obj = data.get("content", {}).get("matchFacts", {}).get("events") or {}
        pen_events = events_obj.get("penaltyShootoutEvents") or []
        for pen_event in pen_events:
            if not isinstance(pen_event, dict):
                continue

            event_id = pen_event.get("eventId")
            if not event_id:
                continue

            player = pen_event.get("player", {})
            player_name = player.get("name") if isinstance(player, dict) else None
            if not player_name:
                player_name = pen_event.get("nameStr", "Unknown")

            pen_score = pen_event.get("penShootoutScore")
            if not pen_score or not isinstance(pen_score, list) or len(pen_score) < 2:
                continue

            # Determine if scored or missed
            event_type = pen_event.get("type", "")
            scored = event_type == "Goal"

            penalty_kicks.append(
                PenaltyKick(
                    id=event_id,
                    player_name=player_name,
                    team_id=pen_event.get("player", {}).get("id", 0)
                    if isinstance(pen_event.get("player"), dict)
                    else 0,
                    is_home=pen_event.get("isHome", False),
                    scored=scored,
                    home_shootout_score=pen_score[0],
                    away_shootout_score=pen_score[1],
                )
            )

        # Get final penalty score from the last penalty kick
        if penalty_kicks:
            last_pk = penalty_kicks[-1]
            penalties = PenaltyShootout(
                home_score=last_pk.home_shootout_score,
                away_score=last_pk.away_shootout_score,
            )

        # If penalties are complete (we have a final shootout score), mark match as finished
        # This handles cases where FotMob hasn't updated general.finished yet
        if penalties and status == "live":
            # Check if one team has won the shootout (scores are different)
            if penalties.home_score != penalties.away_score:
                match.status = "finished"

        return MatchDetails(
            match=match,
            events=events,
            stats=stats,
            lineups=lineups,
            broadcast_channels=None,
            highlight=highlight,
            extra_time=extra_time,
            penalties=penalties,
            penalty_kicks=penalty_kicks if penalty_kicks else None,
        )

    def _parse_match_details_from_page(
        self, page_props: dict, broadcast_channels_data: list | None = None
    ) -> MatchDetails | None:
        """Parse match details from scraped page props."""
        details = self._parse_match_details_from_api(page_props)

        # Add broadcast channels if available
        if details and broadcast_channels_data:
            channels = [
                BroadcastChannel(
                    channel_name=ch.get("channelName", ""),
                    country_name=ch.get("countryName", ""),
                )
                for ch in broadcast_channels_data
            ]
            details.broadcast_channels = channels

        return details

    def _parse_matches_from_league_page(self, page_props: dict) -> list[Match]:
        """Parse matches from a league page's props."""
        matches = []

        fixtures = page_props.get("fixtures", {}).get("allMatches", [])
        league_id = page_props.get("details", {}).get("id")
        league_name = page_props.get("details", {}).get("name")

        for match_data in fixtures:
            try:
                match = self._parse_match_from_dict(match_data, league_id, league_name)
                if match.page_slug:
                    self._page_slugs[match.id] = match.page_slug
                matches.append(match)
            except Exception as e:
                logger.error(f"Failed to parse match from league page: {e}")

        return matches

    async def get_league_stats(
        self, league_id: int, stat_type: str = "goals"
    ) -> list[PlayerStat]:
        """
        Get top player statistics for a league.

        Args:
            league_id: The league ID (e.g., 77 for World Cup, 130 for MLS)
            stat_type: "goals" or "assists"

        Returns:
            List of PlayerStat objects sorted by stat_value descending (top 5)
        """
        # Map stat type to FotMob API file names
        stat_file_map = {"goals": "goals.json", "assists": "goal_assist.json"}

        stat_file = stat_file_map.get(stat_type)
        if not stat_file:
            logger.error(f"Invalid stat type: {stat_type}")
            return []

        # Fetch league stats page to get season ID
        html = await self._fetch_page_html(f"/leagues/{league_id}/overview")
        if not html:
            logger.warning(f"Failed to fetch league page for league {league_id}")
            return []

        page_props = extract_page_props(html)
        if not page_props:
            logger.warning(f"Failed to extract page props for league {league_id}")
            return []

        # Navigate to stats.players array
        stats_data = page_props.get("stats", {})
        players_data = stats_data.get("players", [])

        if not players_data:
            logger.info(f"No stats available for league {league_id}")
            return []

        # Find the stat object matching our stat type
        stat_header_map = {"goals": "Top scorer", "assists": "Assists"}
        target_header = stat_header_map.get(stat_type)

        stat_obj = None
        for player_stat in players_data:
            if player_stat.get("header") == target_header:
                stat_obj = player_stat
                break

        if not stat_obj:
            logger.warning(
                f"Stat type '{stat_type}' not found in league {league_id} stats"
            )
            return []

        # Try to get full stats from data API
        fetch_all_url = stat_obj.get("fetchAllUrl")
        if fetch_all_url:
            try:
                # Fetch from data API with gzip support
                headers = {"Accept-Encoding": "gzip, deflate"}
                response_body = await self._request_with_retry(
                    fetch_all_url, headers=headers
                )

                if response_body:
                    import json

                    data = json.loads(response_body.decode("utf-8"))
                    top_lists = data.get("TopLists", [])

                    if top_lists and len(top_lists) > 0:
                        stat_list = top_lists[0].get("StatList", [])

                        # Convert to PlayerStat objects (take top 5)
                        results = []
                        for i, item in enumerate(stat_list[:10]):
                            results.append(
                                PlayerStat(
                                    player_name=item.get("ParticipantName", "Unknown"),
                                    team_name=item.get("TeamName"),
                                    stat_value=int(item.get("StatValue", 0)),
                                    rank=item.get("Rank", i + 1),
                                )
                            )

                        return results
            except Exception as e:
                logger.error(f"Failed to fetch from data API: {e}")
                # Fall through to topThree fallback

        # Fallback to topThree from page props
        top_three = stat_obj.get("topThree", [])
        if top_three:
            results = []
            for i, item in enumerate(top_three):
                results.append(
                    PlayerStat(
                        player_name=item.get("name", "Unknown"),
                        team_name=item.get("teamName"),
                        stat_value=int(item.get("value", 0)),
                        rank=item.get("rank", i + 1),
                    )
                )
            return results

        return []
