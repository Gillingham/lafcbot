"""Data models for FotMob match and league data."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Team:
    """Represents a soccer team."""

    id: int
    name: str
    logo_url: str | None = None


@dataclass
class MatchEvent:
    """Represents a match event (goal, card, substitution, etc.)."""

    id: int  # Unique event ID for deduplication
    type: str  # "goal", "card", "substitution", etc.
    minute: int
    team_id: int
    player_name: str | None = None
    assist_name: str | None = None  # Assist player for goals
    description: str | None = None
    own_goal: bool = False  # Whether this is an own goal
    card_color: str | None = None  # "yellow" or "red" when applicable
    half_type: str | None = None  # "HT" for half-time, "FT" for full-time


@dataclass
class Venue:
    """Represents a stadium/venue."""

    name: str
    city: str | None = None
    country: str | None = None
    capacity: int | None = None


@dataclass
class Match:
    """Represents basic match information."""

    id: int
    home_team: Team
    away_team: Team
    home_score: int | None
    away_score: int | None
    status: str  # "finished", "live", "upcoming", etc.
    start_time: datetime | None = None
    league_id: int | None = None
    league_name: str | None = None
    page_slug: str | None = None  # URL slug for match page
    venue: Venue | None = None
    match_time_display: str | None = None  # Display string like "45'+2" or "HT"

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
class Highlight:
    """Represents match highlight video information."""

    url: str
    title: str | None = None


@dataclass
class PenaltyShootout:
    """Represents penalty shootout information."""

    home_score: int
    away_score: int


@dataclass
class MatchDetails:
    """Represents detailed match information including events and stats."""

    match: Match
    events: list[MatchEvent]
    stats: dict
    lineups: dict | None = None
    broadcast_channels: list[BroadcastChannel] | None = None
    highlight: Highlight | None = None  # Official match highlights
    extra_time: bool = False  # Whether match went to extra time
    penalties: PenaltyShootout | None = None  # Penalty shootout result


@dataclass
class League:
    """Represents a soccer league."""

    id: int
    name: str
    matches: list[Match]
    standings: dict | None = None
