"""Base formatter with shared utilities for all formatters."""

from zoneinfo import ZoneInfo


class BaseFormatter:
    """Base class with common formatting utilities."""

    def __init__(self, timezone: ZoneInfo | None = None):
        """
        Initialize formatter with timezone.

        Args:
            timezone: ZoneInfo for localizing times. Defaults to America/Los_Angeles.
        """
        self.timezone = timezone or ZoneInfo("America/Los_Angeles")

    def truncate_for_discord(self, message: str, limit: int = 2000) -> str:
        """
        Truncate message to Discord's character limit.

        Args:
            message: Message to truncate
            limit: Character limit (default 2000 for Discord)

        Returns:
            Truncated message with "..." if over limit
        """
        if len(message) <= limit:
            return message
        return message[: limit - 3] + "..."

    def format_score(self, home_score: int | None, away_score: int | None) -> str:
        """
        Format match score.

        Args:
            home_score: Home team score or None
            away_score: Away team score or None

        Returns:
            Formatted score (e.g., '2-1' or 'vs' if scores unavailable)
        """
        if home_score is not None and away_score is not None:
            return f"{home_score}-{away_score}"
        return "vs"

    def format_table_row(self, columns: list[str], widths: list[int]) -> str:
        """
        Format a table row with fixed-width columns.

        Args:
            columns: Column values
            widths: Width for each column

        Returns:
            Formatted row string
        """
        return " ".join(
            col.ljust(width) for col, width in zip(columns, widths, strict=True)
        )
