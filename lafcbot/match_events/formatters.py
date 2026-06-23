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
    reason: str | None = None,
) -> str:
    """
    Format a cancelled/disallowed goal notification message.

    Args:
        scorer: Name of the player who scored (before disallowed)
        team_display: Formatted team display (with flag if applicable)
        minute_display: Formatted minute string (e.g., "65+2'")
        score_line: Full score line with team names and scores
        reason: Optional cancellation reason (e.g., "offside", "foul")

    Returns:
        Formatted notification message string

    Example:
        >>> format_cancelled_goal_notification(
        ...     "Azizjon Ganiev",
        ...     "Uzbekistan 🇺🇿",
        ...     "29'",
        ...     "🇵🇹 Portugal 2-0 Uzbekistan 🇺🇿",
        ...     "foul"
        ... )
        '🚫 **NO GOAL!** Goal disallowed (foul)\\n**Scorer:** Azizjon Ganiev (Uzbekistan 🇺🇿) 29\\'\\n**Score remains:** 🇵🇹 Portugal 2-0 Uzbekistan 🇺🇿'
    """
    reason_text = f" ({reason})" if reason else ""
    return (
        f"🚫 **NO GOAL!** Goal disallowed{reason_text}\n"
        f"**Scorer:** {scorer} ({team_display}) {minute_display}\n"
        f"**Score remains:** {score_line}"
    )
