"""Mock FotMobClient for integration testing.

This module provides a MockFotMobClient that wraps FotMobSimulator and provides
async methods compatible with the real FotMobClient interface. This allows
testing live monitoring logic without actual HTTP requests.
"""

from lafcbot.clients.fotmob.models import Match, MatchDetails

from .fotmob_simulator import FotMobSimulator


class MockFotMobClient:
    """Mock FotMobClient for integration testing.

    Wraps a FotMobSimulator and provides async methods that return match data
    at the current simulated time. Allows tests to control time progression.

    Usage:
        sim = FotMobSimulator("/path/to/match.json")
        mock_client = MockFotMobClient(sim)

        # Set simulated time
        mock_client.set_minute(0)
        details = await mock_client.get_match_details_authenticated(match_id)

        # Advance time
        mock_client.advance_time(30)
        details = await mock_client.get_match_details_authenticated(match_id)
    """

    def __init__(self, simulator: FotMobSimulator):
        """Initialize mock client with simulator.

        Args:
            simulator: FotMobSimulator to use as data source
        """
        self.simulator = simulator
        self.current_minute = 0

    def set_minute(self, minute: int):
        """Set the current simulated minute.

        Args:
            minute: Match minute to simulate (0-120+)
        """
        self.current_minute = minute

    def advance_time(self, minutes: int):
        """Advance simulated time by N minutes.

        Args:
            minutes: Number of minutes to advance
        """
        self.current_minute += minutes

    async def get_match_details_authenticated(
        self, match_id: int, force_refresh: bool = False
    ) -> MatchDetails | None:
        """Get match details at current simulated time.

        Args:
            match_id: Match ID (must match simulator's match)
            force_refresh: Ignored (for compatibility with real client)

        Returns:
            MatchDetails at current_minute, or None if match_id doesn't match
        """
        if match_id != self.simulator.match_id:
            return None

        return self.simulator.get_match_at_minute(self.current_minute)

    async def get_match_details(
        self,
        match_id: int | None = None,
        page_slug: str | None = None,
        force_refresh: bool = False,
    ) -> MatchDetails | None:
        """Get match details at current simulated time.

        Args:
            match_id: Match ID (must match simulator's match)
            page_slug: Ignored (for compatibility with real client)
            force_refresh: Ignored (for compatibility with real client)

        Returns:
            MatchDetails at current_minute, or None if match_id doesn't match
        """
        if match_id and match_id != self.simulator.match_id:
            return None

        return self.simulator.get_match_at_minute(self.current_minute)

    async def get_live_world_cup_matches(self) -> list[Match]:
        """Get list of live matches (simulated).

        Returns:
            List with one match if current_minute indicates live status, else empty
        """
        details = self.simulator.get_match_at_minute(self.current_minute)

        if details.match.is_live:
            # Return the Match object from details
            return [details.match]
        else:
            return []

    async def get_league_matches(self, league_id: int) -> list[Match]:
        """Get all league matches (simulated).

        Returns:
            List with one match (the simulator's match)
        """
        details = self.simulator.get_match_at_minute(self.current_minute)

        # Return the Match object from details
        return [details.match]
