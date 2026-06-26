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

    def split_for_discord(self, message: str, limit: int = 2000) -> list[str]:
        """
        Split message into multiple parts at blank line boundaries for Discord's character limit.

        This ensures matches (or other logical blocks separated by blank lines) stay together.

        Args:
            message: Message to split
            limit: Character limit per message (default 2000 for Discord)

        Returns:
            List of message chunks, each under the limit
        """
        if len(message) <= limit:
            return [message]

        chunks = []
        current_chunk = ""
        current_block = ""  # Accumulate lines until we hit a blank line

        for line in message.split("\n"):
            # Check if this is a blank line (block separator)
            if line.strip() == "":
                # We've completed a block - try to add it to current chunk
                block_to_add = current_block + "\n"  # Include the blank line

                # If adding this block would exceed limit
                if current_chunk and len(current_chunk) + len(block_to_add) > limit:
                    # Save current chunk and start new one
                    chunks.append(current_chunk.rstrip("\n"))
                    current_chunk = block_to_add
                else:
                    # Add block to current chunk
                    current_chunk += block_to_add

                current_block = ""
            else:
                # Add line to current block
                current_block += line + "\n"

        # Handle any remaining content
        if current_block:
            # We have an unfinished block (no trailing blank line)
            if current_chunk and len(current_chunk) + len(current_block) > limit:
                chunks.append(current_chunk.rstrip("\n"))
                chunks.append(current_block.rstrip("\n"))
            else:
                current_chunk += current_block

        if current_chunk:
            chunks.append(current_chunk.rstrip("\n"))

        return chunks if chunks else [message]

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
