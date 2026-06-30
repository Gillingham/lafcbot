# lafcbot Testing Framework

This testing framework eliminates code duplication by allowing tests to use **actual production code** with **real match data** instead of manually constructing fake data.

## Overview

The testing framework provides:

1. **FotMobSimulator**: Loads real match JSON and allows time-based filtering
2. **MockFotMobClient**: Async wrapper for integration testing
3. **Discord Mocks**: Mock bot/channel/message objects for notification testing
4. **Test Helpers**: Convenience functions for common scenarios

## Quick Start

### Load a Test Match

```python
from lafcbot.testing import load_test_match

# Load match by ID from test_data/
sim = load_test_match(4653706)

# Get full match (finished state)
full_match = sim.get_full_match()

# Get match at specific minute (e.g., halftime)
halftime = sim.get_match_at_minute(45)

# Get match after first 3 events
early_match = sim.get_match_at_event_index(3)
```

### Test Formatters (Strategy 1: Direct Access)

```python
def test_penalty_formatting():
    # Load match and get data
    sim = load_test_match(4653706)
    details = sim.get_full_match()
    
    # Call ACTUAL formatter with real data
    formatter = WorldCupFormatter(timezone=ZoneInfo("UTC"))
    result = formatter.format_penalty_shootout_cards(
        details.penalty_kicks,
        details.match.home_team.name,
        details.match.away_team.name
    )
    
    # Assert on output
    assert "🟩" in result or "🟥" in result
```

### Test Event Detectors (Strategy 1: Direct Access)

```python
def test_goal_detection():
    sim = load_test_match(4653703)
    details = sim.get_full_match()
    
    # Test actual detector functions
    goal_events = [e for e in details.events if e.type.lower() == "goal"]
    
    for goal in goal_events:
        assert goal.team_id is not None
        assert goal.minute >= 0
```

### Test Live Monitoring (Strategy 2: Mock Client)

```python
async def test_goal_notification():
    # Create simulator and mock client
    sim = load_test_match(4653703)
    mock_client = MockFotMobClient(sim)
    
    # Create mock Discord bot
    mock_bot, guild, channels = create_test_bot_with_channels(
        channel_names=["world-cup-live"]
    )
    
    # Create WorldCupTask with mocked dependencies
    task = WorldCupTask(mock_bot, mock_client, config)
    
    # Simulate time progression
    mock_client.set_minute(30)
    await task._monitor_match(match, None)
    
    # Assert notifications were sent
    messages = channels["world-cup-live"].sent_messages
    assert len(messages) > 0
```

## Test Organization

```
tests/
├── test_formatters/          # Formatter tests (Strategy 1)
│   ├── test_world_cup_formatter.py
│   └── test_soccer_formatter.py
├── test_event_detection/     # Event detector tests (Strategy 1)
│   ├── test_detectors.py
│   ├── test_var_detection.py
│   └── test_penalty_detection.py
└── test_live_monitoring/     # Integration tests (Strategy 2)
    ├── test_state_tracking.py
    ├── test_notifications.py
    └── test_match_progression.py
```

## Running Tests

```bash
# Run all tests
uv run pytest tests/

# Run specific test file
uv run pytest tests/test_formatters/test_world_cup_formatter.py

# Run specific test class
uv run pytest tests/test_formatters/test_world_cup_formatter.py::TestTeamFormatting

# Run with verbose output
uv run pytest tests/ -v

# Run with coverage (if pytest-cov installed)
uv run pytest tests/ --cov=lafcbot --cov-report=html
```

## Available Test Data

Test data is stored in `test_data/match_*_dump.json` files. These are real FotMob API responses captured during actual matches.

```python
from lafcbot.testing import list_available_matches

# Get all available match IDs
matches = list_available_matches()
print(f"Available matches: {len(matches)}")
```

## Key Concepts

### Time-Based Filtering

The simulator allows "time travel" through match events:

```python
sim = load_test_match(4653703)

# Pre-match (no events)
pre = sim.get_match_at_minute(0)
assert pre.match.status == "upcoming"

# During match
live = sim.get_match_at_minute(45)
assert live.match.status == "live"

# After match
finished = sim.get_match_at_minute(120)
# Status depends on actual match data
```

### Event Deduplication Testing

Test that notifications aren't sent twice:

```python
async def test_no_duplicates():
    mock_client.set_minute(30)
    await task._monitor_match(match, None)
    first_count = len(channel.sent_messages)
    
    # Same minute again - should not send duplicates
    await task._monitor_match(match, None)
    second_count = len(channel.sent_messages)
    
    assert second_count == first_count
```

### Stale Event Prevention

Test that starting mid-match doesn't notify about past events:

```python
async def test_stale_events():
    # Start monitoring at minute 60
    mock_client.set_minute(60)
    await task._monitor_match(match, None)
    
    # Should not notify about events before minute 60
    early_goals = [m for m in messages if "goal" in m.content.lower()]
    # Assert minimal notifications
```

## Benefits

1. **No duplication**: Tests call actual production code
2. **Real data**: Uses actual FotMob API responses
3. **Repeatable**: Same input → same output every time
4. **Comprehensive**: Can test edge cases from real matches
5. **Maintainable**: Changes to formatters automatically reflected in tests

## Adding New Tests

1. Identify functionality to test (formatter, detector, or monitoring logic)
2. Choose strategy:
   - Strategy 1 (direct access) for pure functions
   - Strategy 2 (mock client) for stateful/async code
3. Load test match with `load_test_match()`
4. Call actual production code
5. Assert on output

Example:

```python
def test_new_formatter_function():
    sim = load_test_match(4653703)
    details = sim.get_full_match()
    
    # Call actual function
    result = formatter.new_function(details)
    
    # Assert expected behavior
    assert expected_value in result
```
