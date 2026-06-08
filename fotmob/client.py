"""FotMob API client for fetching match and league data."""

import asyncio
import logging
from datetime import date, datetime
from typing import Optional

import aiohttp

from .constants import BASE_URL, HEADERS, MAX_RETRIES, REQUEST_DELAY, RETRY_DELAY
from .models import BroadcastChannel, Match, MatchDetails, MatchEvent, Team, Venue
from .parser import extract_broadcast_channels, extract_page_props

logger = logging.getLogger(__name__)


class FotMobClient:
    """
    Async client for fetching soccer match data from FotMob.

    This client implements both API endpoint access and HTML scraping
    with automatic fallback when Cloudflare protection blocks API access.
    """

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """
        Initialize the FotMob client.

        Args:
            session: Optional aiohttp session. If not provided, a new one
                    will be created and managed by this client.
        """
        self._session = session
        self._owns_session = session is None
        self._last_request_time = 0.0

    async def __aenter__(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(headers=HEADERS)
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
        self, url: str, method: str = "GET", **kwargs
    ) -> Optional[bytes]:
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
            self._session = aiohttp.ClientSession(headers=HEADERS)
            self._owns_session = True

        await self._rate_limit()

        for attempt in range(MAX_RETRIES):
            try:
                async with self._session.request(method, url, **kwargs) as response:
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

    async def _fetch_api_endpoint(self, endpoint: str) -> Optional[dict]:
        """
        Fetch data from a FotMob API endpoint.

        Args:
            endpoint: API endpoint path (e.g., "/api/matchDetails?matchId=123")

        Returns:
            Parsed JSON response, or None if request failed
        """
        url = f"{BASE_URL}{endpoint}"
        response_body = await self._request_with_retry(url)

        if response_body:
            try:
                import json

                return json.loads(response_body.decode("utf-8"))
            except Exception as e:
                logger.error(f"Failed to parse JSON from {url}: {e}")

        return None

    async def _fetch_page_html(self, page_path: str) -> Optional[str]:
        """
        Fetch HTML from a FotMob page.

        Args:
            page_path: Page path (e.g., "/leagues/130")

        Returns:
            Raw HTML content, or None if request failed
        """
        url = f"{BASE_URL}{page_path}"
        response_body = await self._request_with_retry(url)

        if response_body:
            try:
                return response_body.decode("utf-8")
            except Exception as e:
                logger.error(f"Failed to decode HTML from {url}: {e}")

        return None

    async def get_matches_by_date(
        self, target_date: Optional[str] = None, league_ids: Optional[list[int]] = None
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

    async def get_match_details(
        self, match_id: Optional[int] = None, page_slug: Optional[str] = None
    ) -> Optional[MatchDetails]:
        """
        Get detailed information about a specific match.

        Args:
            match_id: Match ID (for API endpoint method)
            page_slug: Page slug like "/matches/team1-vs-team2/abc123" (for scraping method)

        Returns:
            MatchDetails object, or None if fetch failed
        """
        if match_id is not None:
            endpoint = f"/api/matchDetails?matchId={match_id}"
            data = await self._fetch_api_endpoint(endpoint)

            if data:
                return self._parse_match_details_from_api(data)
            else:
                logger.warning(
                    f"API endpoint failed for match {match_id}, trying page scraping"
                )

        if page_slug is not None:
            html = await self._fetch_page_html(page_slug)
            if html:
                page_props = extract_page_props(html)
                if page_props:
                    # Also extract broadcast channels from HTML
                    broadcast_channels_data = extract_broadcast_channels(html)
                    return self._parse_match_details_from_page(
                        page_props, broadcast_channels_data
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
        html = await self._fetch_page_html(f"/leagues/{league_id}")
        if html:
            page_props = extract_page_props(html)
            if page_props:
                return self._parse_matches_from_league_page(page_props)

        return []

    async def get_league_standings(self, league_id: int) -> Optional[dict]:
        """
        Get league standings/table.

        Args:
            league_id: The league ID

        Returns:
            Dictionary with standings data, or None if fetch failed
        """
        endpoint = f"/api/leagues?leagueId={league_id}"
        data = await self._fetch_api_endpoint(endpoint)

        if data:
            return data.get("table", {})

        html = await self._fetch_page_html(f"/leagues/{league_id}")
        if html:
            page_props = extract_page_props(html)
            if page_props:
                return page_props.get("table", {})

        return None

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
        league_id: Optional[int] = None,
        league_name: Optional[str] = None,
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
        status = (
            status_obj.get("finished")
            and "finished"
            or status_obj.get("started")
            and "live"
            or "upcoming"
        )

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

        return Match(
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
        )

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

        match = Match(
            id=int(general.get("matchId", 0)),
            home_team=home_team,
            away_team=away_team,
            home_score=None,  # Score not in general section
            away_score=None,
            status=status,
            start_time=start_time,
            league_id=general.get("parentLeagueId"),
            league_name=general.get("leagueName"),
            page_slug=None,
            venue=venue,
        )

        events = []
        for event_data in (
            data.get("content", {})
            .get("matchFacts", {})
            .get("events", {})
            .get("events", [])
        ):
            events.append(
                MatchEvent(
                    type=event_data.get("type", "unknown"),
                    minute=event_data.get("time", 0),
                    team_id=event_data.get("teamId", 0),
                    player_name=event_data.get("player", {}).get("name"),
                    description=event_data.get("text"),
                )
            )

        stats = data.get("content", {}).get("stats", {})
        lineups = data.get("content", {}).get("lineup", {})

        return MatchDetails(
            match=match,
            events=events,
            stats=stats,
            lineups=lineups,
            broadcast_channels=None,
        )

    def _parse_match_details_from_page(
        self, page_props: dict, broadcast_channels_data: list = None
    ) -> Optional[MatchDetails]:
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
                matches.append(match)
            except Exception as e:
                logger.error(f"Failed to parse match from league page: {e}")

        return matches
