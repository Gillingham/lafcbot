"""Data models for FotMob match and league data."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Team:
    """Represents a soccer team."""

    id: int
    name: str
    logo_url: Optional[str] = None


@dataclass
class MatchEvent:
    """Represents a match event (goal, card, substitution, etc.)."""

    type: str  # "goal", "card", "substitution", etc.
    minute: int
    team_id: int
    player_name: Optional[str] = None
    description: Optional[str] = None


@dataclass
class Venue:
    """Represents a stadium/venue."""

    name: str
    city: Optional[str] = None
    country: Optional[str] = None
    capacity: Optional[int] = None


@dataclass
class Match:
    """Represents basic match information."""

    id: int
    home_team: Team
    away_team: Team
    home_score: Optional[int]
    away_score: Optional[int]
    status: str  # "finished", "live", "upcoming", etc.
    start_time: Optional[datetime] = None
    league_id: Optional[int] = None
    league_name: Optional[str] = None
    page_slug: Optional[str] = None  # URL slug for match page
    venue: Optional[Venue] = None

    @property
    def is_live(self) -> bool:
        return self.status.lower() in ("live", "in_play", "halftime")

    @property
    def is_finished(self) -> bool:
        return self.status.lower() in ("finished", "ft", "fulltime")


@dataclass
class BroadcastChannel:
    """Represents a TV broadcast channel."""

    channel_name: str
    country_name: str


@dataclass
class MatchDetails:
    """Represents detailed match information including events and stats."""

    match: Match
    events: list[MatchEvent]
    stats: dict
    lineups: Optional[dict] = None
    broadcast_channels: Optional[list[BroadcastChannel]] = None


@dataclass
class League:
    """Represents a soccer league."""

    id: int
    name: str
    matches: list[Match]
    standings: Optional[dict] = None
