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
