"""Event classification and detection utilities for match events."""


def normalize_half_type(event) -> str:
    """
    Normalize half_type value to prevent duplicate detections.

    The API sometimes returns inconsistent half_type values (None vs "HT"/"FT")
    for the same event. This ensures consistent deduplication.

    Args:
        event: Event object with minute and optional half_type attributes

    Returns:
        Normalized half_type string: "HT" for first half, "FT" for full-time
    """
    if event.half_type:
        return event.half_type
    # Fallback based on minute
    return "FT" if event.minute >= 90 else "HT"


def is_card_event(event) -> bool:
    """
    Check if an event is a yellow or red card.

    Args:
        event: Event object with type, card_color, and description attributes

    Returns:
        True if event is a card, False otherwise
    """
    # Prefer explicit card_color if populated by parser
    card_color = getattr(event, "card_color", None)
    if card_color:
        return card_color.lower() in ("yellow", "red")

    # Fall back to event type or description inspection
    try:
        if event.type and str(event.type).lower() == "card":
            return True
    except Exception:
        pass

    event_text = f"{event.type or ''} {event.description or ''}".lower()
    return "card" in event_text and ("yellow" in event_text or "red" in event_text)


def get_card_color(event) -> str:
    """
    Determine the color of a card event.

    Args:
        event: Event object with card_color, type, and description attributes

    Returns:
        "red", "yellow", or "card" (as fallback)
    """
    # Use explicit card_color when available
    card_color = getattr(event, "card_color", None)
    if card_color:
        return str(card_color).lower()

    event_text = f"{event.type or ''} {event.description or ''}".lower()
    if "red" in event_text and "yellow" not in event_text:
        return "red"
    if "yellow" in event_text:
        return "yellow"
    if "red" in event_text:
        return "red"
    return "card"


def is_substitution_event(event) -> bool:
    """
    Check if an event is a substitution.

    Args:
        event: Event object with type, assist_name, player_name, and description

    Returns:
        True if event is a substitution, False otherwise
    """
    # Prefer explicit substitution type
    try:
        if event.type and str(event.type).lower() in ("substitution", "sub"):
            return True
    except Exception:
        pass

    # If assist_name and player_name are both present and different,
    # it likely represents a swap (player out and player in)
    if getattr(event, "assist_name", None) and getattr(event, "player_name", None):
        return True

    # Fall back to description containing 'on for' or 'sub'
    event_text = f"{event.type or ''} {event.description or ''}".lower()
    return "on for" in event_text or "sub" in event_text


def is_half_event(event) -> bool:
    """
    Check if an event is a half-time or full-time event.

    Args:
        event: Event object with type attribute

    Returns:
        True if event is a half-time or full-time marker, False otherwise
    """
    try:
        if event.type and str(event.type).lower() == "half":
            return True
        etype = str(event.type or "").lower()
        # Normalize check for various halftime/fulltime indicators
        return etype in ("half", "half-time", "ht", "ft", "periodend")
    except Exception:
        pass
    return False


def is_var_event(event) -> bool:
    """
    Check if an event is a VAR review event.

    Args:
        event: Event object with type attribute

    Returns:
        True if event is a VAR event, False otherwise
    """
    try:
        return event.type and str(event.type).upper() == "VAR"
    except Exception:
        return False


def is_goal_cancelled_by_var(event) -> bool:
    """
    Check if a VAR event indicates a cancelled/disallowed goal.

    Args:
        event: Event object with type and var_decision attributes

    Returns:
        True if VAR event cancelled a goal, False otherwise
    """
    if not is_var_event(event):
        return False

    var_data = getattr(event, "var_decision", None)
    if not var_data or not isinstance(var_data, dict):
        return False

    decision = var_data.get("decision", {})
    decision_keys = decision.get("key", [])
    return "var_goal_cancelled" in decision_keys


def get_var_cancellation_reason(event) -> str | None:
    """
    Extract the cancellation reason from a VAR event.

    Args:
        event: VAR event object with var_decision attribute

    Returns:
        Human-readable cancellation reason, or None if not available
    """
    var_data = getattr(event, "var_decision", None)
    if not var_data or not isinstance(var_data, dict):
        return None

    decision = var_data.get("decision", {})
    values = decision.get("value", [])

    # values[0] is typically "Goal ruled out", values[1] is the reason
    return values[1] if len(values) > 1 else None
