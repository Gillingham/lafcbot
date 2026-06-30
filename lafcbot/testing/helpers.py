"""Helper functions for testing soccer/world-cup functionality.

This module provides convenient functions for loading test matches and
simulating live match progression.
"""

from collections.abc import Iterator
from pathlib import Path

from lafcbot.clients.fotmob.models import MatchDetails

from .fotmob_simulator import FotMobSimulator


def get_test_data_dir() -> Path:
    """Get the test_data directory path.

    Returns:
        Path to test_data/ directory
    """
    # Assume we're in lafcbot/testing/ and test_data is at repo root
    current_file = Path(__file__)
    repo_root = current_file.parent.parent.parent
    return repo_root / "test_data"


def load_test_match(match_id: int) -> FotMobSimulator:
    """Load a test match by ID.

    Args:
        match_id: Match ID (must have corresponding match_{id}_dump.json in test_data/)

    Returns:
        FotMobSimulator loaded with the match data

    Raises:
        FileNotFoundError: If match file doesn't exist
    """
    test_data_dir = get_test_data_dir()
    match_file = test_data_dir / f"match_{match_id}_dump.json"

    if not match_file.exists():
        raise FileNotFoundError(
            f"Match file not found: {match_file}\n"
            f"Available matches: {list_available_matches()}"
        )

    return FotMobSimulator(match_file)


def list_available_matches() -> list[int]:
    """List all available test match IDs.

    Returns:
        Sorted list of match IDs available in test_data/
    """
    test_data_dir = get_test_data_dir()

    if not test_data_dir.exists():
        return []

    match_ids = []
    for file in test_data_dir.glob("match_*_dump.json"):
        # Extract ID from filename: match_4653706_dump.json -> 4653706
        try:
            match_id = int(file.stem.split("_")[1])
            match_ids.append(match_id)
        except (IndexError, ValueError):
            continue

    return sorted(match_ids)


def simulate_live_progression(simulator: FotMobSimulator) -> Iterator[MatchDetails]:
    """Yield match states at key moments during a live match.

    Yields MatchDetails objects at: kickoff, each goal, halftime, each card,
    full time, and any other significant events.

    Args:
        simulator: FotMobSimulator to progress through

    Yields:
        MatchDetails at each key moment
    """
    # Get all key moments from the simulator
    key_minutes = simulator.get_key_moments()

    # Add kickoff if not present
    if 0 not in key_minutes:
        key_minutes = [0] + key_minutes

    # Yield match state at each key minute
    for minute in key_minutes:
        yield simulator.get_match_at_minute(minute)


def extract_event_sequence(details: MatchDetails) -> list[dict]:
    """Extract event sequence as simple dictionaries for assertion.

    Useful for verifying event detection/classification in tests.

    Args:
        details: MatchDetails to extract events from

    Returns:
        List of dicts with event metadata (id, type, minute, player, etc.)
    """
    events = []
    for event in details.events:
        event_dict = {
            "id": event.id,
            "type": event.type,
            "minute": event.minute,
        }

        if event.added_time:
            event_dict["added_time"] = event.added_time

        if event.player_name:
            event_dict["player"] = event.player_name

        if event.team_id:
            event_dict["team_id"] = event.team_id

        if event.type.lower() == "goal":
            event_dict["own_goal"] = event.own_goal
            if event.assist_name:
                event_dict["assist"] = event.assist_name

        if event.type.lower() == "card" or event.card_color:
            event_dict["card_color"] = event.card_color

        events.append(event_dict)

    return events


def find_penalty_shootout_matches() -> list[int]:
    """Find test matches that went to penalty shootouts.

    Returns:
        List of match IDs for matches with penalty shootouts
    """
    penalty_matches = []

    for match_id in list_available_matches():
        try:
            sim = load_test_match(match_id)
            full_match = sim.get_full_match()

            if full_match.penalties or full_match.penalty_kicks:
                penalty_matches.append(match_id)
        except Exception:
            # Skip matches that fail to load
            continue

    return penalty_matches


def find_var_matches() -> list[int]:
    """Find test matches with VAR events.

    Returns:
        List of match IDs for matches with VAR decisions
    """
    var_matches = []

    for match_id in list_available_matches():
        try:
            sim = load_test_match(match_id)
            full_match = sim.get_full_match()

            # Check if any event is a VAR event
            for event in full_match.events:
                if "var" in event.type.lower() or event.var_decision:
                    var_matches.append(match_id)
                    break
        except Exception:
            # Skip matches that fail to load
            continue

    return var_matches
