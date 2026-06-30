"""FotMob match data simulator for testing.

This module provides a FotMobSimulator class that loads real match JSON from
test_data/ and allows time-based filtering to simulate live match progression.

The simulator reuses FotMobClient's actual parsing logic to ensure tests
exercise the same code paths as production.
"""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from lafcbot.clients.fotmob.client import FotMobClient
from lafcbot.clients.fotmob.models import MatchDetails


class FotMobSimulator:
    """Simulates FotMob match data for testing.

    Loads real match JSON and provides time-based filtering to test
    formatters, detectors, and live monitoring logic.

    Usage:
        sim = FotMobSimulator("/path/to/test_data/match_4653706_dump.json")

        # Get full match (finished state)
        full = sim.get_full_match()

        # Get match at halftime
        halftime = sim.get_match_at_minute(45)

        # Get match after first 3 events
        early = sim.get_match_at_event_index(3)
    """

    def __init__(self, match_json_path: str | Path):
        """Initialize simulator with match JSON file.

        Args:
            match_json_path: Path to match JSON dump from test_data/
        """
        self.json_path = Path(match_json_path)

        # Load and parse JSON using FotMobClient's parser
        with open(self.json_path) as f:
            self.match_data = json.load(f)

        # Use FotMobClient's actual parser to parse the match
        # This ensures we're testing with the same parsing logic as production
        client = FotMobClient()
        self.full_details = client._parse_match_details_from_api(self.match_data)

        # Extract match ID for reference
        self.match_id = self.full_details.match.id

    def get_full_match(self) -> MatchDetails:
        """Get complete match details (finished state).

        Returns:
            MatchDetails with all events and final state
        """
        return deepcopy(self.full_details)

    def get_match_at_minute(self, minute: int) -> MatchDetails:
        """Get match state at a specific minute.

        Filters events to only include those at or before the specified minute.
        Adjusts match status (upcoming → live → finished) based on minute.
        Updates scores to reflect only goals scored by this minute.

        Args:
            minute: Match minute (0-120+)

        Returns:
            MatchDetails with events filtered to <= minute
        """
        details = deepcopy(self.full_details)

        # Filter events to only those at or before the specified minute
        filtered_events = []
        for event in details.events:
            event_minute = event.minute
            if event.added_time:
                event_minute += event.added_time / 100.0  # 45+2 becomes 45.02

            if event_minute <= minute:
                filtered_events.append(event)

        details.events = filtered_events

        # Determine match status based on minute
        if minute < 1:
            status = "upcoming"
            match_time_display = None
        elif minute >= 90 and details.match.is_finished:
            # Original match is finished and we're past 90' - keep finished status
            status = "finished"
            match_time_display = "FT"
        elif 44 <= minute < 46:
            status = "live"
            match_time_display = "HT"
        else:
            status = "live"
            match_time_display = f"{minute}'"

        # Update match object with new status
        details.match = replace(
            details.match, status=status, match_time_display=match_time_display
        )

        # Calculate scores based on filtered events
        home_score = 0
        away_score = 0
        for event in filtered_events:
            if event.type.lower() == "goal" and not event.own_goal:
                # Determine which team scored (event.team_id matches one of the teams)
                if event.team_id == details.match.home_team.id:
                    home_score += 1
                elif event.team_id == details.match.away_team.id:
                    away_score += 1
            elif event.type.lower() == "goal" and event.own_goal:
                # Own goal - opposite team gets the point
                if event.team_id == details.match.home_team.id:
                    away_score += 1
                elif event.team_id == details.match.away_team.id:
                    home_score += 1

        # Update scores
        details.match = replace(
            details.match, home_score=home_score, away_score=away_score
        )

        # For pre-match state, clear penalty info
        if status == "upcoming":
            details.penalties = None
            details.penalty_kicks = None

        # For live state before penalties, clear penalty info
        if status == "live" and minute < 120:
            details.penalties = None
            details.penalty_kicks = None

        return details

    def get_match_at_event_index(self, event_index: int) -> MatchDetails:
        """Get match state after a specific number of events.

        Args:
            event_index: Number of events to include (0-based index)

        Returns:
            MatchDetails with first N events only
        """
        details = deepcopy(self.full_details)

        # Take only the first N events
        details.events = details.events[:event_index]

        # If we have events, use the last event's minute to determine status
        if details.events:
            last_event = details.events[-1]
            last_minute = last_event.minute
            return self.get_match_at_minute(last_minute)
        else:
            # No events - return pre-match state
            return self.get_match_at_minute(0)

    def get_key_moments(self) -> list[int]:
        """Get list of key minute markers in the match.

        Returns:
            List of minutes where significant events occurred (goals, HT, FT, etc.)
        """
        moments = set()

        for event in self.full_details.events:
            # Add event minute
            moments.add(event.minute)

            # Add standard moments if not already present
            if event.minute >= 45:
                moments.add(45)  # Halftime
            if event.minute >= 90:
                moments.add(90)  # Full time

        return sorted(moments)
