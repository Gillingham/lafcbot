"""FotMob API client for fetching match and league data."""

import asyncio
import logging
from datetime import date, datetime

import aiohttp

from .constants import BASE_URL, HEADERS, MAX_RETRIES, REQUEST_DELAY, RETRY_DELAY
from .models import (
    BroadcastChannel,
    Highlight,
    Match,
    MatchDetails,
    MatchEvent,
    PenaltyShootout,
    Team,
    Venue,
)
from .parser import extract_broadcast_channels, extract_page_props

logger = logging.getLogger(__name__)


class FotMobClient:
    """
    Async client for fetching soccer match data from FotMob.

    This client implements both API endpoint access and HTML scraping
    with automatic fallback when Cloudflare protection blocks API access.
    """

    def __init__(self, session: aiohttp.ClientSession | None = None):
        """
        Initialize the FotMob client.

        Args:
            session: Optional aiohttp session. If not provided, a new one
                    will be created and managed by this client.
        """
        self._session = session
        self._owns_session = session is None
        self._last_request_time = 0.0
        self._page_slugs: dict[int, str] = {}
        self._match_details_cache: dict[int, tuple[float, MatchDetails]] = {}

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

    async def _fetch_api_endpoint(self, endpoint: str) -> dict | None:
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

    async def _fetch_page_html(self, page_path: str) -> str | None:
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
            html = await self._fetch_page_html(page_slug)
            if html:
                page_props = extract_page_props(html)
                if page_props:
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
                        logger.error(
                            f"Failed to parse match details from page_slug: {e}"
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
                html = await self._fetch_page_html(path)
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
                        logger.error(
                            f"Failed to parse match details from page {path}: {e}"
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
                data = await self._fetch_api_endpoint(endpoint)
                if data:
                    logger.debug(f"FotMob API returned data for endpoint: {endpoint}")
                    break
                else:
                    logger.debug(f"No data from FotMob API endpoint: {endpoint}")

            if data:
                try:
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
        html = await self._fetch_page_html(f"/leagues/{league_id}")
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
            # Extract assist for goals
            assist_name = None
            if event_data.get("type") == "Goal":
                # Assist can be in multiple places
                assist_data = event_data.get("assist")
                if assist_data:
                    if isinstance(assist_data, dict):
                        assist_name = assist_data.get("name")
                    elif isinstance(assist_data, str):
                        assist_name = assist_data

            # Normalize type and handle special event fields.
            raw_type = event_data.get("type", "unknown")

            # Prefer explicit `card`/`Card` fields for card color. Do NOT
            # treat generic `eventType` as a card color unless the main type
            # indicates a card to avoid misclassifying substitutions.
            card_field = event_data.get("card") or event_data.get("Card")
            card_color_val = None
            if card_field:
                try:
                    card_color_val = str(card_field).lower()
                except Exception:
                    card_color_val = None

            # Handle substitutions represented via `swap` array or explicit type
            swap = event_data.get("swap") or event_data.get("Swap")
            is_substitution = False
            if swap and isinstance(swap, list) and len(swap) >= 2:
                is_substitution = True

            if card_color_val:
                event_type = "card"
                desc_parts = []
                if event_data.get("text"):
                    desc_parts.append(event_data.get("text"))
                desc_parts.append(str(card_field))
                description = " ".join(desc_parts)
            elif is_substitution or str(raw_type).lower() in ("substitution", "sub"):
                event_type = "substitution"
                description = event_data.get("text")
                # If swap array exists, prefer mapping player_out/ player_in
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
            else:
                event_type = raw_type
                description = event_data.get("text")

            # Own goal flag might appear under different keys
            own_goal_flag = event_data.get("isOwnGoal")
            if own_goal_flag is None:
                own_goal_flag = event_data.get("ownGoal", False)

            # Extract half type for Half events (HT or FT)
            half_type_val = None
            if str(raw_type).lower() == "half":
                half_type_val = event_data.get("halfStrShort")  # "HT" or "FT"

            # Map player fields; if swap provided use those values
            if is_substitution and swap and isinstance(swap, list) and len(swap) >= 2:
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
                except Exception:
                    player_in = None
                    player_out = None
            else:
                player_in = None
                player_out = None

            events.append(
                MatchEvent(
                    id=event_data.get("eventId", event_data.get("id", 0)),
                    type=event_type,
                    minute=event_data.get("time", 0),
                    team_id=event_data.get("teamId", 0),
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
        extra_time = general.get("extraTime", False) or general.get(
            "hasExtraTime", False
        )

        # Parse penalty shootout
        penalties = None
        penalty_data = data.get("content", {}).get("shootoutDetails")
        if penalty_data and isinstance(penalty_data, dict):
            home_pen_score = penalty_data.get("homeScore")
            away_pen_score = penalty_data.get("awayScore")
            if home_pen_score is not None and away_pen_score is not None:
                penalties = PenaltyShootout(
                    home_score=home_pen_score, away_score=away_pen_score
                )

        return MatchDetails(
            match=match,
            events=events,
            stats=stats,
            lineups=lineups,
            broadcast_channels=None,
            highlight=highlight,
            extra_time=extra_time,
            penalties=penalties,
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
