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


def is_card_removed_by_var(event) -> bool:
    """
    Check if a VAR event indicates a yellow/red card was removed.

    Args:
        event: Event object with type and var_decision attributes

    Returns:
        True if VAR event removed a card, False otherwise
    """
    if not is_var_event(event):
        return False

    var_data = getattr(event, "var_decision", None)
    if not var_data or not isinstance(var_data, dict):
        return False

    decision = var_data.get("decision", {})
    decision_keys = decision.get("key", [])
    return (
        "var_yellow_card_removed" in decision_keys
        or "var_red_card_removed" in decision_keys
    )


def is_penalty_awarded_by_var(event) -> bool:
    """
    Check if a VAR event indicates a penalty was awarded.

    Args:
        event: Event object with type and var_decision attributes

    Returns:
        True if VAR event awarded a penalty, False otherwise
    """
    if not is_var_event(event):
        return False

    var_data = getattr(event, "var_decision", None)
    if not var_data or not isinstance(var_data, dict):
        return False

    decision = var_data.get("decision", {})
    decision_keys = decision.get("key", [])
    return "var_penalty_awarded" in decision_keys


def is_card_given_by_var(event) -> bool:
    """
    Check if a VAR event indicates a yellow/red card was given.

    Args:
        event: Event object with type and var_decision attributes

    Returns:
        True if VAR event gave a card, False otherwise
    """
    if not is_var_event(event):
        return False

    var_data = getattr(event, "var_decision", None)
    if not var_data or not isinstance(var_data, dict):
        return False

    decision = var_data.get("decision", {})
    decision_keys = decision.get("key", [])
    return (
        "var_yellow_card_given" in decision_keys
        or "var_red_card_given" in decision_keys
    )


def is_penalty_cancelled_by_var(event) -> bool:
    """
    Check if a VAR event indicates a penalty was cancelled.

    Args:
        event: Event object with type and var_decision attributes

    Returns:
        True if VAR event cancelled a penalty, False otherwise
    """
    if not is_var_event(event):
        return False

    var_data = getattr(event, "var_decision", None)
    if not var_data or not isinstance(var_data, dict):
        return False

    decision = var_data.get("decision", {})
    decision_keys = decision.get("key", [])
    return "var_penalty_cancelled" in decision_keys


def is_penalty_retake_by_var(event) -> bool:
    """
    Check if a VAR event indicates a penalty miss should be retaken.

    Args:
        event: Event object with type and var_decision attributes

    Returns:
        True if VAR event ordered penalty retake, False otherwise
    """
    if not is_var_event(event):
        return False

    var_data = getattr(event, "var_decision", None)
    if not var_data or not isinstance(var_data, dict):
        return False

    decision = var_data.get("decision", {})
    decision_keys = decision.get("key", [])
    return "var_penalty_miss_retake" in decision_keys


def get_var_decision_type(event) -> str | None:
    """
    Determine the type of VAR decision.

    Args:
        event: VAR event object with var_decision attribute

    Returns:
        VAR decision type: "goal_cancelled", "card_removed", "penalty_awarded",
        "penalty_cancelled", "penalty_retake", "card_given", or "unknown"
    """
    if not is_var_event(event):
        return None

    if is_goal_cancelled_by_var(event):
        return "goal_cancelled"
    elif is_card_removed_by_var(event):
        return "card_removed"
    elif is_penalty_awarded_by_var(event):
        return "penalty_awarded"
    elif is_penalty_cancelled_by_var(event):
        return "penalty_cancelled"
    elif is_penalty_retake_by_var(event):
        return "penalty_retake"
    elif is_card_given_by_var(event):
        return "card_given"
    else:
        return "unknown"


def get_var_decision_keys(event) -> list[str]:
    """
    Extract all decision keys from a VAR event for logging/debugging.

    Args:
        event: VAR event object with var_decision attribute

    Returns:
        List of decision key strings, or empty list if not available
    """
    var_data = getattr(event, "var_decision", None)
    if not var_data or not isinstance(var_data, dict):
        return []

    decision = var_data.get("decision", {})
    return decision.get("key", [])


def get_var_decision_values(event) -> list[str]:
    """
    Extract all decision values (human-readable descriptions) from a VAR event.

    Args:
        event: VAR event object with var_decision attribute

    Returns:
        List of decision value strings, or empty list if not available
    """
    var_data = getattr(event, "var_decision", None)
    if not var_data or not isinstance(var_data, dict):
        return []

    decision = var_data.get("decision", {})
    return decision.get("value", [])


def get_var_cancellation_reason(event) -> str | None:
    """
    Extract the cancellation reason from a VAR event.

    Args:
        event: VAR event object with var_decision attribute

    Returns:
        Human-readable cancellation reason, or None if not available
    """
    values = get_var_decision_values(event)
    # values[0] is typically "Goal ruled out", values[1] is the reason
    return values[1] if len(values) > 1 else None


def is_penalty_goal(event) -> bool:
    """
    Check if a goal event is a penalty kick goal.

    Args:
        event: Event object with type and goal_description_key attributes

    Returns:
        True if event is a penalty goal, False otherwise
    """
    if not event.type or event.type.lower() != "goal":
        return False

    # Check goal_description_key for "penalty"
    goal_desc_key = getattr(event, "goal_description_key", None)
    if goal_desc_key and goal_desc_key.lower() == "penalty":
        return True

    # Fallback: check shotmap_event situation
    shotmap = getattr(event, "shotmap_event", None)
    if shotmap and isinstance(shotmap, dict):
        situation = shotmap.get("situation", "")
        if situation and situation.lower() == "penalty":
            return True

    return False
