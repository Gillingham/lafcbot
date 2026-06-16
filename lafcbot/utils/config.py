"""Configuration and timezone utilities."""

import json
from pathlib import Path
from zoneinfo import ZoneInfo


def load_config() -> dict:
    """Load configuration from config.json.

    Returns:
        Configuration dictionary with defaults for missing values.
    """
    # Navigate up from lafcbot/utils/config.py to project root
    config_path = Path(__file__).parent.parent.parent / "config.json"
    try:
        with open(config_path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: {config_path} not found, using defaults")
        return {
            "world_cup": {
                "enabled": False,
                "channel_name": "world-cup",  # Keep for legacy support
                "daily_time_hour": 8,
                "timezone": "America/Los_Angeles",
                "servers": [],  # New multi-server format
            },
            "channel_leagues": {},
            "pandaping": {"servers": []},
        }
    except json.JSONDecodeError as e:
        print(f"Error parsing config.json: {e}")
        return {
            "world_cup": {"enabled": False, "servers": []},
            "channel_leagues": {},
            "pandaping": {"servers": []},
        }


def load_timezone() -> ZoneInfo:
    """Load timezone from config, defaulting to America/Los_Angeles.

    Returns:
        ZoneInfo object for the configured timezone.
    """
    try:
        config = load_config()
        tz_name = config.get("timezone", "America/Los_Angeles")
        return ZoneInfo(tz_name)
    except Exception as e:
        print(f"Error loading timezone from config: {e}, using default")
        return ZoneInfo("America/Los_Angeles")


def get_db_path() -> Path:
    """Get the path to the lafcbot database.

    Returns:
        Path object pointing to lafcbot.db in the project root.
    """
    return Path(__file__).parent.parent.parent / "lafcbot.db"
