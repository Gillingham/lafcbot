"""Formatting utilities for match events and notifications."""


def format_minute(event) -> str:
    """
    Format minute display with added time if present.

    Args:
        event: Event object with minute and optional added_time attributes

    Returns:
        Formatted minute string (e.g., "45'" or "45+2'")
    """
    if event.added_time:
        return f"{event.minute}+{event.added_time}'"
    return f"{event.minute}'"


def format_cancelled_goal_notification(
    scorer: str,
    team_display: str,
    minute_display: str,
    score_line: str,
) -> str:
    """
    Format a cancelled/disallowed goal notification message.

    Args:
        scorer: Name of the player who scored (before disallowed)
        team_display: Formatted team display (with flag if applicable)
        minute_display: Formatted minute string (e.g., "65+2'")
        score_line: Full score line with team names and scores

    Returns:
        Formatted notification message string

    Example:
        >>> format_cancelled_goal_notification(
        ...     "Musa Al-Taamari",
        ...     "Jordan 🇯🇴",
        ...     "65+2'",
        ...     "🇦🇹 Austria 1-0 Jordan 🇯🇴"
        ... )
        '🚫 **NO GOAL!** Goal disallowed\\n**Scorer:** Musa Al-Taamari (Jordan 🇯🇴) 65+2\\'\\n**Score remains:** 🇦🇹 Austria 1-0 Jordan 🇯🇴'
    """
    return (
        f"🚫 **NO GOAL!** Goal disallowed\n"
        f"**Scorer:** {scorer} ({team_display}) {minute_display}\n"
        f"**Score remains:** {score_line}"
    )
