"""
FotMob API wrapper for fetching soccer/football match data.

This package provides a Python interface to FotMob.com's undocumented API
and web scraping for match results, statistics, and details.
"""

from .client import FotMobClient
from .models import (
    BroadcastChannel,
    Highlight,
    League,
    Match,
    MatchDetails,
    MatchEvent,
    PenaltyShootout,
    PlayerStat,
    Team,
    Venue,
)


def resolve_league_name(league_input: str) -> tuple[str | None, int | None]:
    """
    Resolve a league name or alias to canonical name and ID.

    Args:
        league_input: League name, alias, or partial name (case-insensitive)

    Returns:
        Tuple of (canonical_name, league_id) or (None, None) if not found
    """
    from .constants import LEAGUE_ALIASES, LEAGUE_IDS

    # Normalize input
    normalized = league_input.lower().strip().replace("_", " ")

    # Direct match in LEAGUE_IDS
    if normalized.replace(" ", "_") in LEAGUE_IDS:
        canonical = normalized.replace(" ", "_")
        return canonical, LEAGUE_IDS[canonical]

    # Check aliases
    if normalized in LEAGUE_ALIASES:
        canonical = LEAGUE_ALIASES[normalized]
        return canonical, LEAGUE_IDS[canonical]

    return None, None


def format_league_name(league_key: str) -> str:
    """
    Format a league key for display (replace underscores with spaces, title case).

    Args:
        league_key: League key like "world_cup" or "premier_league"

    Returns:
        Formatted name like "World Cup" or "Premier League"
    """
    # Special cases for acronyms
    acronyms = {
        "mls": "MLS",
        "nwsl": "NWSL",
    }

    if league_key in acronyms:
        return acronyms[league_key]

    return league_key.replace("_", " ").title()


__all__ = [
    "FotMobClient",
    "Match",
    "MatchDetails",
    "League",
    "Team",
    "MatchEvent",
    "Venue",
    "BroadcastChannel",
    "Highlight",
    "PenaltyShootout",
    "PlayerStat",
    "resolve_league_name",
    "format_league_name",
]
