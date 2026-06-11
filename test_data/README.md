# Test Data

This directory contains captured real-world data from FotMob API for testing purposes.

## Mexico vs South Africa Match Data

**File:** `mexico_vs_south_africa_match_data.json`

**Match Details:**
- Match ID: 4667751
- Date: June 11, 2026 at 19:00 UTC
- Competition: World Cup Group A
- Status: Finished
- Total Events: 21

**Captured:** 2026-06-11 at 14:12 PST (approximately 20 minutes after match ended)

### Data Structure

The JSON file contains:

```json
{
  "captured_at": "ISO timestamp of when this data was captured",
  "match_id": 4667751,
  "match_name": "Mexico vs South Africa",
  "general": {
    // Match metadata (teams, league, start time, status, etc.)
  },
  "events": [
    // Array of all match events (goals, cards, substitutions, etc.)
  ],
  "match_facts": {
    // Additional match facts (excluding events which are separate)
  }
}
```

### Event Fields

Each event in the `events` array contains:
- `eventId`: Unique identifier for deduplication
- `time`: Match minute (e.g., 9, 17, 23)
- `type`: Event type (Goal, Card, substitution, etc.)
- `player`: Player information (id, name, profileUrl)
- `isHome`: Boolean indicating home/away team
- `homeScore`/`awayScore`: Score at time of event
- Event-specific fields (e.g., `card` color, `assistStr` for goals)

**Important Note:** Events do NOT have real-world timestamps, only match clock minutes.

### Usage

This data can be used to:
1. Test event parsing logic
2. Verify staleness check behavior
3. Test event deduplication by event ID
4. Simulate match monitoring scenarios

Example events captured:
- 9': Goal by Julián Quiñones (with assist)
- 17': Yellow card to Teboho Mokoena
- 23': Yellow card to Brian Gutiérrez
- Plus 18 more events throughout the match
