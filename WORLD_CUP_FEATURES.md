# World Cup Goal Notifications & Highlights

This document describes the World Cup live monitoring and highlights features.

## Features

### 1. Live Goal Notifications

When World Cup matches are live, the bot automatically monitors them and sends notifications to Discord when:
- **Goals are scored** - Includes scorer, minute, assist, and current score
- **Matches go to extra time** - Notification when regulation time ends tied
- **Penalty shootouts begin** - Alert when matches go to penalties

Goal notifications automatically attempt to find and link Reddit replay clips from r/soccer.

### 2. Post-Match Summaries

When a monitored live match finishes, the bot automatically posts a summary including:
- Final score (with penalty result if applicable)
- All goals with scorers and assists
- Link to official match highlights (if available from FotMob)
- Venue information

### 3. Manual Match Summaries

Use the `!match <match_id>` command to get a summary of any match:

```
!match 4193490
```

This works for live, finished, or upcoming matches.

## Configuration

Edit `config.json` to enable/disable features:

```json
{
  "world_cup": {
    "enabled": true,
    "channel_name": "world-cup-2026",
    "daily_time_hour": 8,
    "timezone": "America/Los_Angeles",
    "live_monitoring": {
      "enabled": true,
      "channel_name": "world-cup-2026-live",
      "check_interval_seconds": 60,
      "pre_match_minutes": 15,
      "fallback_check_hours": 12,
      "notifications": {
        "goals": true,
        "extra_time": true,
        "penalties": true,
        "include_reddit_clips": true
      }
    },
    "highlights": {
      "reddit_enabled": true,
      "cache_path": "~/.lafcbot/reddit_cache.json"
    }
  }
}
```

### Configuration Options

- **`enabled`**: Enable/disable all World Cup features
- **`channel_name`**: Channel for daily match schedules
- **`daily_time_hour`**: Hour (0-23) to post daily schedule
- **`timezone`**: Timezone for scheduling (e.g., "America/Los_Angeles")

#### Live Monitoring

- **`live_monitoring.enabled`**: Enable/disable live match monitoring
- **`live_monitoring.channel_name`**: Channel for live notifications
- **`live_monitoring.check_interval_seconds`**: How often to check for updates during matches (default: 60)
- **`live_monitoring.pre_match_minutes`**: Start monitoring N minutes before kickoff (default: 15)
- **`live_monitoring.fallback_check_hours`**: How long to sleep if no matches found (default: 12)
- **`notifications.goals`**: Enable goal notifications
- **`notifications.extra_time`**: Enable extra time notifications
- **`notifications.penalties`**: Enable penalty shootout notifications
- **`notifications.include_reddit_clips`**: Try to find Reddit replay clips

#### Highlights

- **`highlights.reddit_enabled`**: Enable Reddit clip searching
- **`highlights.cache_path`**: Where to cache found clips

## How It Works

### Smart Scheduling

The live monitoring system uses intelligent scheduling to minimize API calls while ensuring timely notifications:

**Two-tier architecture:**
1. **Scheduler** (checks every 5 minutes): Decides what to do next based on match schedule
2. **Game Monitor** (polls every 60 seconds): Only active when matches are live

**Scheduling logic:**
- When matches are **live**: Activates game monitor immediately
- When matches are **upcoming**: Sleeps until 15 minutes before kickoff (configurable)
- When **no matches scheduled**: Sleeps for 12 hours then checks again (configurable)
- When matches **finish**: Game monitor stops itself, scheduler takes over

**Benefits:**
- ~95% fewer API calls on non-match days (2-4 calls vs 1,440)
- Timezone-aware: works globally with matches at any time
- Match-driven: all timing based on actual kickoff times, not arbitrary schedules
- Graceful fallback: handles tournament gaps and API issues

### Goal Detection

When the game monitor is active (matches are live), it polls FotMob's API every 60 seconds (configurable). It:
1. Fetches detailed match information including all events
2. Compares event IDs to detect new goals
3. Sends Discord notifications immediately
4. Attempts to find Reddit clips in the background (with 5-second timeout)
5. Edits the notification to add clip links when found

### Reddit Clip Search

The Reddit integration searches r/soccer for goal clips using multiple strategies:
1. Both teams + minute (e.g., "Spain Germany 34'")
2. Scoring team + minute + score
3. Short team names sorted by upvotes

Results are cached to avoid repeated API calls. The Reddit API is rate-limited to 10 requests per minute.

### Post-Match Summaries

When a match transitions from `live` to `finished`, the bot:
1. Detects the status change in the next polling cycle
2. Fetches complete match details
3. Posts a comprehensive summary with all goals
4. Includes official highlights link if available from FotMob
5. Removes the match from active monitoring

## Finding Match IDs

To use the `!match` command, you need a FotMob match ID. You can find these by:
1. Using `!matches world cup` to see upcoming/current matches
2. Looking at FotMob URLs (the number at the end)
3. The bot logs match IDs when monitoring live matches

## Troubleshooting

### No notifications appearing

1. Check that `live_monitoring.enabled` is `true` in config.json
2. Verify the channel name matches an existing Discord channel
3. Check bot logs for errors
4. Ensure there are actually live World Cup matches

### Reddit clips not appearing

1. Reddit API is rate-limited and may be slow
2. Clips may not be posted to r/soccer yet (try again later)
3. Check that `include_reddit_clips` is `true`
4. Look for timeout/error messages in logs

### Match summaries not posting

1. Ensure the match was monitored while live (bot must be running during the match)
2. Check that the live monitoring channel exists
3. Verify bot has permissions to post in the channel

## Technical Details

### Data Sources

- **Match data**: FotMob API (official match details, events, highlights)
- **Replay clips**: Reddit r/soccer (community-posted goal clips)

### Rate Limiting

- FotMob: Built-in rate limiting with retries
- Reddit: 10 requests per minute, with batching and delays

### Caching

- Reddit clips are cached locally at `~/.lafcbot/reddit_cache.json`
- Found clips are cached permanently
- Not-found results are cached for 24 hours then retried

### Event Deduplication

Events are tracked by unique ID to prevent duplicate notifications. The bot maintains state for each monitored match including:
- Last known event list (by ID)
- Last known scores
- Whether extra time/penalty alerts were sent
- Whether match was live in previous check

## Example Notifications

### Goal Notification

```
⚽ GOAL! 🇪🇸 Spain 2-1 🇩🇪 Germany

Scorer: Álvaro Morata 67'
Assist: Dani Olmo

🎥 Replay (added after search completes)
```

### Extra Time

```
⏱️ EXTRA TIME: 🇪🇸 Spain 2-2 🇩🇪 Germany

The match is going to extra time!
```

### Penalty Shootout

```
🎯 PENALTY SHOOTOUT: 🇪🇸 Spain vs 🇩🇪 Germany

After Extra Time: Spain 2-2 Germany
The match will be decided on penalties!
```

### Post-Match Summary

```
🏁 FINAL: 🇪🇸 Spain 3-1 🇩🇪 Germany

⚽ Goals:
12' - Pedri
34' - Morata (Olmo)
67' - Morata
89' - Füllkrug

📺 Official Highlights: [Watch](https://...)
```

## Future Enhancements

Potential improvements:
- Live penalty kick tracking (if data becomes available)
- Red card notifications
- Match thread creation/linking
- Player statistics in post-match summaries
- Multi-league support beyond World Cup
