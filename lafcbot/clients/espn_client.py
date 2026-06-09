"""ESPN API client for fetching sports scores."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class Game:
    """Single game data."""

    away_team: str
    away_score: str
    home_team: str
    home_score: str
    status: str
    is_scheduled: bool
    scheduled_time: Optional[datetime] = None


class ESPNClient:
    """Async client for fetching sports scores from ESPN."""

    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"

    SPORT_PATHS = {
        "nba": "basketball/nba",
        "mlb": "baseball/mlb",
        "nhl": "hockey/nhl",
        "nfl": "football/nfl",
        "f1": "racing/f1",
    }

    def __init__(self):
        """Initialize the ESPN client."""
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def get_scoreboard(self, sport: str) -> tuple[str, list[Game]]:
        """
        Get scoreboard for a sport.

        Args:
            sport: Sport key (e.g., 'nba', 'mlb', 'nhl', 'nfl', 'f1')

        Returns:
            Tuple of (league_full_name, list of Game objects)
            Returns (None, []) if request failed
        """
        if sport not in self.SPORT_PATHS:
            logger.warning(f"Unknown sport: {sport}")
            return (None, [])

        if not self._session:
            self._session = aiohttp.ClientSession()

        sport_path = self.SPORT_PATHS[sport]
        url = f"{self.BASE_URL}/{sport_path}/scoreboard"

        try:
            async with self._session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"ESPN request returned status {response.status}")
                    return (None, [])

                data = await response.json()
                return self._parse_scoreboard(data)

        except aiohttp.ClientError as e:
            logger.error(f"ESPN request failed: {e}")
            return (None, [])
        except Exception as e:
            logger.error(f"Unexpected error fetching scores: {e}")
            return (None, [])

    def _parse_scoreboard(self, data: dict) -> tuple[str, list[Game]]:
        """Parse scoreboard data from ESPN API."""
        try:
            # Extract league name
            league_name = None
            if "leagues" in data and len(data["leagues"]) > 0:
                league_name = data["leagues"][0].get("name")
            elif "league" in data:
                league_name = data["league"].get("name")

            # Extract events (games)
            events = data.get("events", [])
            games = []

            for event in events:
                game = self._parse_game(event)
                if game:
                    games.append(game)

            return (league_name, games)

        except Exception as e:
            logger.error(f"Failed to parse scoreboard data: {e}")
            return (None, [])

    def _parse_game(self, event: dict) -> Optional[Game]:
        """Parse a single game from event data."""
        try:
            competition = event.get("competitions", [{}])[0]
            competitors = competition.get("competitors", [])

            if len(competitors) < 2:
                return None

            # Find home and away teams
            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c for c in competitors if c.get("homeAway") == "away"), None)

            if not home or not away:
                return None

            # Extract team abbreviations and scores
            away_team = away.get("team", {}).get("abbreviation", "???")
            away_score = away.get("score", "0")
            home_team = home.get("team", {}).get("abbreviation", "???")
            home_score = home.get("score", "0")

            # Extract and format status
            status_obj = competition.get("status", {})
            status_type = status_obj.get("type", {})
            state = status_type.get("state", "")

            # Check if game is scheduled (not in progress or finished)
            is_scheduled = state not in ("in", "post")
            scheduled_time = None

            if is_scheduled:
                # Extract scheduled datetime from status
                date_str = competition.get("date")
                if date_str:
                    try:
                        scheduled_time = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00")
                        )
                    except Exception as e:
                        logger.warning(f"Failed to parse scheduled time: {e}")

            status = self._format_status(status_obj)

            return Game(
                away_team=away_team,
                away_score=away_score,
                home_team=home_team,
                home_score=home_score,
                status=status,
                is_scheduled=is_scheduled,
                scheduled_time=scheduled_time,
            )

        except Exception as e:
            logger.error(f"Failed to parse game: {e}")
            return None

    def _format_status(self, status: dict) -> str:
        """Format game status string."""
        try:
            status_type = status.get("type", {})
            short_detail = status_type.get("shortDetail", "")

            # Check if game is in progress
            state = status_type.get("state", "")
            if state == "in":
                # For live games, use the short detail which includes clock and period
                # Example: "8:28 - 3rd", "Bot 10th", "Top 3rd"
                return short_detail
            elif state == "post":
                # For finished games
                return "Final"
            else:
                # For scheduled games, use the short detail (date/time)
                # Example: "6/9 - 8:00 PM EDT"
                return short_detail

        except Exception as e:
            logger.error(f"Failed to format status: {e}")
            return "Unknown"
