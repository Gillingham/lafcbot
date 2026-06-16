"""Discord message formatters package.

All formatters follow a consistent pattern:
- Constructor accepts dependencies (timezone, API clients, etc.)
- Methods return formatted strings ready for Discord
- Async methods handle API calls internally
- Dependency injection enables easy mocking in tests
"""

from lafcbot.formatters.base import BaseFormatter
from lafcbot.formatters.latepass import LatePassFormatter
from lafcbot.formatters.misc import MiscFormatter
from lafcbot.formatters.soccer import SoccerFormatter
from lafcbot.formatters.sports import SportsFormatter
from lafcbot.formatters.weather import WeatherFormatter
from lafcbot.formatters.world_cup import FormattedMatch, WorldCupFormatter

__all__ = [
    "BaseFormatter",
    "WorldCupFormatter",
    "FormattedMatch",
    "SoccerFormatter",
    "LatePassFormatter",
    "SportsFormatter",
    "WeatherFormatter",
    "MiscFormatter",
]
