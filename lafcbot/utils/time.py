"""Time formatting utilities."""

from datetime import timedelta


def format_time_ago(time_diff: timedelta) -> str:
    """Format a timedelta as a human-readable 'X ago' string.

    Args:
        time_diff: Time difference to format.

    Returns:
        Human-readable string like "2 days ago", "3 hours ago", "5 minutes ago", or "just now".

    Examples:
        >>> from datetime import timedelta
        >>> format_time_ago(timedelta(days=2))
        '2 days ago'
        >>> format_time_ago(timedelta(hours=1))
        '1 hour ago'
        >>> format_time_ago(timedelta(minutes=30))
        '30 minutes ago'
        >>> format_time_ago(timedelta(seconds=15))
        'just now'
    """
    if time_diff.days > 0:
        return f"{time_diff.days} day{'s' if time_diff.days != 1 else ''} ago"
    elif time_diff.seconds >= 3600:
        hours = time_diff.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif time_diff.seconds >= 60:
        minutes = time_diff.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "just now"
