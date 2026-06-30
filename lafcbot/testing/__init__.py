"""Testing utilities for lafcbot.

This package provides tools for testing soccer/world-cup functionality without
duplicating implementation code. Key components:

- FotMobSimulator: Load and replay real match data from test_data/
- MockFotMobClient: Async wrapper for integration testing
- Discord mocks: Mock bot/channel/message objects for notification testing
- Helper functions: load_test_match(), simulate_live_progression(), etc.

Usage:
    from lafcbot.testing import load_test_match

    sim = load_test_match(4653706)  # Load a penalty shootout match
    details = sim.get_full_match()  # Get complete match state

    # Test formatter with real data
    formatter = WorldCupFormatter(timezone=ZoneInfo("UTC"))
    result = formatter.format_penalty_shootout_cards(...)
"""

from lafcbot.testing.fotmob_simulator import FotMobSimulator
from lafcbot.testing.helpers import (
    list_available_matches,
    load_test_match,
    simulate_live_progression,
)

__all__ = [
    "FotMobSimulator",
    "load_test_match",
    "list_available_matches",
    "simulate_live_progression",
]
