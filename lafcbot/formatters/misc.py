"""Formatters for miscellaneous commands."""

from lafcbot.formatters.base import BaseFormatter


class MiscFormatter(BaseFormatter):
    """Formats misc command responses."""

    def format_dice_roll(
        self,
        notation: str,
        rolls: list[int],
        modifier: int,
        total: int,
    ) -> str:
        """
        Format !dice command output.

        Args:
            notation: Dice notation (e.g., "3d6+2")
            rolls: List of individual roll results
            modifier: Modifier value
            total: Total result

        Returns:
            Formatted dice roll string
        """
        rolls_str = ", ".join(str(r) for r in rolls)
        mod_str = f"{modifier:+d}" if modifier else ""
        return f"Rolled {notation}: [{rolls_str}] {mod_str} = **{total}**"

    def format_8ball_response(self, response: str) -> str:
        """
        Format !8ball command output.

        Args:
            response: 8-ball response text

        Returns:
            Formatted 8-ball response
        """
        return f"🎱 {response}"
