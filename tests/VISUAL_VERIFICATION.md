# Visual Verification Tests

This document explains how to run visual verification tests to manually inspect formatted output from the lafcbot formatters and event detectors.

## Purpose

The visual verification test suite allows you to:

1. **Verify formatting** - See actual formatted output for all event types
2. **Inspect real data** - View how actual FotMob match data is processed
3. **Debug issues** - Quickly spot formatting problems or missing emojis
4. **Validate changes** - Ensure formatter changes produce expected output

## Running Visual Verification Tests

### Run All Visual Tests

```bash
uv run pytest tests/test_visual_verification.py -v -s
```

The `-s` flag is **required** to see print output.

### Run Specific Test Categories

```bash
# Match overview (see available test matches)
uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_match_overview -v -s

# Goal events across matches
uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_goal_events -v -s

# Card events (yellow/red cards)
uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_card_events -v -s

# Substitution events
uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_substitution_events -v -s

# Half-time and full-time events
uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_half_events -v -s

# VAR events
uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_var_events -v -s

# Penalty shootout formatting
uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_penalty_shootout_formatting -v -s

# Team name formatting with flags
uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_team_formatting -v -s

# Venue and broadcast information
uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_venue_and_broadcast -v -s

# Complete match summary (all event types together)
uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_complete_match_summary -v -s

# Match time progression (how formatting changes over time)
uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_match_progression -v -s

# Score progression through a match
uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_score_progression -v -s
```

## What Each Test Shows

### 1. Match Overview
Displays available test matches with basic info:
```
4653703: Germany vs Paraguay (1-1)
4653706: Netherlands vs Morocco (1-1)
```

### 2. Match Progression
Shows how match formatting changes at different time points:
```
Minute 0:   Status: upcoming, Score: 0-0
Minute 45:  Status: live, Score: 0-1 (HT)
Minute 90:  Status: live, Score: 1-1 (90')
```

### 3. Team Formatting
Displays team names with flags and rankings:
```
Original: United States
Formatted: 🇺🇸 United States (#11)
```

### 4. Goal Events
Shows all goals with timing and scorers:
```
⚽ 54' - Kai Havertz (Germany)
⚽ 90+1' - Issa Diop (Morocco)
⚽ 42' - Julio Enciso (Paraguay) (assist: Player Name)
```

### 5. Card Events
Displays yellow and red cards:
```
🟨 47' - Issa Diop (Morocco) - YELLOW
🟥 89' - Player Name (Team) - RED
```

### 6. Substitution Events
Shows player substitutions:
```
🔄 86' - Ryan Gravenberch ON for Player Name (Netherlands)
```

### 7. Half Events
Displays half-time and full-time markers:
```
⏸️ 45' - HT
⏹️ 90' - FT
```

### 8. VAR Events
Shows VAR reviews and decisions:
```
📹 85' - VAR: Goal Check
    Decision: Goal Cancelled
```

### 9. Penalty Shootout
Displays penalty shootout formatting:
```
Penalty Shootout Cards:
🇳🇱 🟩 🟩 🟥 🟩 🟩 | 🇲🇦 🟩 🟥 🟩 🟩 🟥

Individual Kicks:
  Home - Player 1: SCORED ⚽
  Away - Player 2: MISSED ❌
```

### 10. Venue & Broadcast
Shows venue and TV channel formatting:
```
Venue:     🏟️ Monterrey Stadium, Guadalupe
Broadcast: 📺 FOX, Telemundo
```

### 11. Complete Match Summary
Full event timeline with all event types:
```
Match: Netherlands vs Morocco
Final Score: 1-1 (Pen)

Event Timeline:
  120' 📝 ADDEDTIME
  113' 🔄 SUBSTITUTION - Cody Gakpo
  90+1' ⚽ GOAL - Issa Diop
  47' 🟨 CARD - Issa Diop
  45' ⏸️ HALF
```

### 12. Score Progression
Shows how scores change with each goal:
```
Starting Score: 0-0
  54' - Kai Havertz (Germany)
      Score: 1-0
  42' - Julio Enciso (Paraguay)
      Score: 1-1
Final Score: 1-1
```

## Output Statistics

The tests also provide summary statistics:
- Total goals found across matches
- Total cards (yellow/red) found
- Total substitutions found
- Matches with venue information
- Matches with broadcast information
- Total VAR events found

## Example Output

```bash
$ uv run pytest tests/test_visual_verification.py::TestVisualVerification::test_goal_events -v -s

================================================================================
  GOAL EVENTS
================================================================================

--------------------------------------------------------------------------------
  Germany vs Paraguay
--------------------------------------------------------------------------------
  ⚽ 54' - Kai Havertz (Germany)
  ⚽ 42' - Julio Enciso (Paraguay)

--------------------------------------------------------------------------------
  Netherlands vs Morocco
--------------------------------------------------------------------------------
  ⚽ 90+1' - Issa Diop (Morocco)
  ⚽ 72' - Cody Gakpo (Netherlands)

Total goals found across matches: 11
PASSED
```

## Use Cases

### 1. Development Workflow
Run visual tests after making formatter changes to verify output looks correct.

### 2. Bug Investigation
If a user reports incorrect formatting, run the relevant visual test to see the actual output.

### 3. Documentation
Use visual test output to create examples for documentation.

### 4. Emoji Verification
Ensure all event types display with correct emojis (⚽, 🟨, 🟥, 🔄, etc.).

### 5. Timezone Testing
Verify that times are formatted correctly in the PT timezone.

## Adding New Visual Tests

To add a new visual verification test:

1. Add a new test method to `TestVisualVerification` class
2. Use `print_section()` for main headers
3. Use `print_subsection()` for sub-headers
4. Load test matches with `load_test_match()`
5. Call actual formatters/detectors
6. Print the formatted output
7. Add statistics/counts if relevant

Example:
```python
def test_my_new_formatter(self, formatter):
    """Display my new formatter output."""
    print_section("MY NEW FORMATTER")

    sim = load_test_match(4653703)
    details = sim.get_full_match()

    result = formatter.my_new_function(details)

    print(f"Formatted output: {result}")
```

## Notes

- Visual tests use actual production formatters and detectors
- Output comes from real FotMob match data in `test_data/`
- All tests are read-only (no modifications to data)
- Tests skip gracefully if required data is not available
- Output is colorized in terminal for better readability

## Troubleshooting

**No output showing:**
- Make sure you're using the `-s` flag with pytest
- Example: `uv run pytest tests/test_visual_verification.py -v -s`

**Test skipped:**
- Some tests skip if they can't find required data (e.g., penalty shootouts)
- This is expected behavior

**Formatting looks wrong:**
- Check if emojis are rendering correctly in your terminal
- Some terminals may not support all Unicode emoji characters

## Related Documentation

- [Testing Framework README](README.md) - Overview of testing utilities
- [Main Project README](../README.md) - Project documentation
