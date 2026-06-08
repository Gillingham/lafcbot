# lafcbot

Discord bot for soccer match information, powered by FotMob data.

## Features

- 🏟️ Match schedules with venue information
- 📺 US TV provider information
- 🏆 League standings
- 🌍 Support for major leagues (MLS, NWSL, World Cup, Premier League, Champions League)
- ⏰ Times displayed in Pacific Time (PT)
- 🚩 Country flags for World Cup matches
- ⚽ **Real-time goal notifications** for World Cup matches
- 🎥 **Automatic Reddit replay clips** from r/soccer
- 🏁 **Post-match summaries** with highlights
- ⏱️ **Extra time and penalty shootout alerts**

## Prerequisites

- Python 3.11+
- `uv` (https://docs.astral.sh/uv/)
- A Discord bot token

## Quick Start

```bash
# Install dependencies
uv sync

# Install pre-commit hooks (optional but recommended)
uv tool install pre-commit
pre-commit install

# Set your Discord bot token
export DISCORD_TOKEN="your_token_here"

# Run the bot
uv run python bot.py
```

## Configuration

The bot uses `config.json` for settings. Create it in the project root:

```json
{
  "channel_leagues": {
    "mls": "mls",
    "nwsl": "nwsl",
    "premier-league": "premier_league",
    "ucl": "champions_league",
    "world-cup-2026": "world_cup"
  },
  "world_cup": {
    "enabled": true,
    "channel_name": "world-cup-2026",
    "daily_time_hour": 8,
    "timezone": "America/Los_Angeles",
    "live_monitoring": {
      "enabled": true,
      "channel_name": "world-cup-2026-live",
      "check_interval_seconds": 60,
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

### Channel-Specific Leagues

Configure which league `!matches` shows by default in each channel:

The `channel_leagues` section maps Discord channel names to league identifiers. When `!matches` is called without arguments in a mapped channel, it shows that league's matches automatically.

**Valid league identifiers:**
- `mls` - Major League Soccer
- `nwsl` - National Women's Soccer League
- `premier_league` - English Premier League
- `champions_league` - UEFA Champions League
- `world_cup` - FIFA World Cup

**Example:** In the `#premier-league` channel, typing `!matches` will show Premier League matches. In unmapped channels, it defaults to MLS.

**World Cup Settings:**

**Basic Settings:**
- `enabled`: Toggle all World Cup features on/off
- `channel_name`: Discord channel for daily spoiler-free match schedules
- `daily_time_hour`: Hour (0-23) for daily schedule posts
- `timezone`: IANA timezone name (e.g., "America/Los_Angeles", "America/New_York")

**Live Monitoring:**
- `live_monitoring.enabled`: Enable real-time goal notifications and live match monitoring
- `live_monitoring.channel_name`: Discord channel for live updates (can have spoilers)
- `live_monitoring.check_interval_seconds`: How often to check for updates (default: 60)
- `notifications.goals`: Enable goal notifications
- `notifications.extra_time`: Enable extra time alerts
- `notifications.penalties`: Enable penalty shootout alerts
- `notifications.include_reddit_clips`: Automatically fetch Reddit replay clips

**Highlights:**
- `highlights.reddit_enabled`: Enable Reddit r/soccer clip searching
- `highlights.cache_path`: Where to cache found clips

If `config.json` is missing, the bot will run with World Cup updates disabled.

## Commands

### `!matches [league]`
Shows matches for the current day, or the next day with matches if none today.

**If no league is specified**, the command uses the league configured for the current Discord channel (see Configuration below). If no channel mapping exists, defaults to MLS.

**Examples:**
```
!matches                # Uses channel-configured league (or MLS if none)
!matches World Cup      # World Cup with country flags
!matches Premier        # Premier League
!matches UCL            # Champions League
```

**Output includes:**
- ✅ Finished matches with scores
- 🔴 Live matches in progress
- Match times in Pacific Time
- 🏟️ Venue/stadium information (first 5 upcoming matches)
- 📺 US TV providers (when available)
- 🚩 Country flags (World Cup only)

**Sample:**
```
**World Cup Matches**

**Today's Matches:**
✅ 🇺🇸 USA 2-1 🇵🇾 Paraguay
🔴 🇧🇷 Brazil 1-0 🇲🇦 Morocco

**Upcoming:**
🇲🇽 Mexico vs 🇿🇦 South Africa - Jun 11, 12:00 PM PT
  🏟️ Mexico City Stadium, Ciudad de México
  📺 FOX, Telemundo
```

### `!standings [league]`
Shows league standings/tables.

**If no league is specified**, the command uses the league configured for the current Discord channel (see Configuration below). If no channel mapping exists, defaults to MLS.

**Examples:**
```
!standings              # Uses channel-configured league (or MLS if none)
!standings World Cup    # World Cup group standings
!standings Premier      # Premier League table
```

**Output:**
- Top 10 teams per table
- Position, Team, Played, Wins, Draws, Losses, Goal Difference, Points
- Multiple tables for leagues with conferences (e.g., MLS Eastern/Western)

### `!match <match_id>`
Shows detailed match summary with goals, assists, and highlights.

**Examples:**
```
!match 4193490
```

**Output includes:**
- Match status (Live, Finished, or Upcoming)
- Final score or current score
- All goals with scorer and assist information
- 🎥 Official match highlights link (if available)
- 🏟️ Venue information
- Penalty shootout results (if applicable)

### Other Commands

- `!ping` - Check bot latency
- `!wut` - Just... wut
- `!dice <notation>` - Roll dice (e.g., `!dice 3d6+2`)
- `!servers` - (Owner only) List servers bot is in

## Supported Leagues

| League | Aliases | ID |
|--------|---------|-----|
| **MLS** | mls, Major League Soccer | 130 |
| **NWSL** | nwsl, womens | 289 |
| **World Cup** | World Cup, world cup, WC, worldcup | 77 |
| **Premier League** | Premier, EPL, English Premier League | 47 |
| **Champions League** | Champions, UCL, UEFA | 42 |

**All commands are case-insensitive and support multi-word names without quotes.**

## Technical Details

### FotMob Wrapper Library

The bot includes a complete async Python library for scraping FotMob:

- **Scraping:** Extracts `__NEXT_DATA__` JSON from Next.js SSR pages
- **Rate Limiting:** 1 second delay between requests
- **Retry Logic:** 3 attempts with exponential backoff
- **Data Models:** Type-safe dataclasses for matches, teams, venues, standings

**Location:** `fotmob/` package

### Data Sources

- **Match Data:** FotMob.com (via HTML scraping and API)
- **Venue Information:** Extracted from match details pages
- **TV Providers:** Extracted from match page HTML (US only)
- **Goal Replay Clips:** Reddit r/soccer (via public JSON API)
- **Highlights:** FotMob official highlights URLs

### Time Zones

All times displayed in **Pacific Time (PT)**, automatically handling PST/PDT transitions. "Today" filtering uses Los Angeles timezone.

## Project Structure

```
lafcbot/
├── fotmob/                    # FotMob wrapper library
│   ├── client.py              # HTTP client with rate limiting
│   ├── constants.py           # League IDs and configuration
│   ├── models.py              # Data models (Match, MatchEvent, Highlight, etc.)
│   ├── parser.py              # HTML/JSON extraction
│   └── __init__.py            # Public API
├── bot.py                     # Discord bot with commands
├── world_cup.py               # World Cup daily schedule + live monitoring
├── reddit_client.py           # Reddit r/soccer clip fetcher with caching
├── config.json                # Bot configuration (user-created)
├── WORLD_CUP_FEATURES.md      # Detailed World Cup features documentation
├── .pre-commit-config.yaml    # Pre-commit hook configuration
├── ruff.toml                  # Ruff linting rules
├── pyproject.toml             # Dependencies and metadata
└── README.md                  # This file
```

## Dependencies

- `py-cord>=2.0` - Discord bot framework
- `aiohttp>=3.9.0` - Async HTTP client (for FotMob and Reddit APIs)
- `beautifulsoup4>=4.12.0` - HTML parsing
- `lxml>=5.0.0` - Fast XML/HTML processing

## Development

### Code Quality

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. Pre-commit hooks automatically run Ruff on all staged files.

```bash
# Install pre-commit hooks
uv tool install pre-commit
pre-commit install

# Run manually on all files
pre-commit run --all-files

# Run ruff directly
uv tool run ruff check .
uv tool run ruff format .
```

**Configuration:**
- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `ruff.toml` - Ruff linting and formatting rules

## Important Notes

### Legal/Ethical

⚠️ This bot scrapes FotMob without official permission and may violate their Terms of Service.

**Intended for:**
- Educational purposes
- Personal use
- Non-commercial projects

**Not for:**
- Commercial applications
- High-volume scraping
- Redistributing FotMob's data

### Rate Limiting

The bot respects FotMob's servers:
- 1 second delay between requests
- Browser-like User-Agent headers
- Exponential backoff on failures

### Reliability

- Dependent on FotMob's HTML structure
- May break if FotMob updates their website
- FotMob's old API endpoints are deprecated (return 404)

## World Cup Live Monitoring

For detailed information about World Cup live monitoring features, see [WORLD_CUP_FEATURES.md](WORLD_CUP_FEATURES.md).

### Quick Overview

When live monitoring is enabled, the bot will:

1. **Monitor live World Cup matches** every 60 seconds
2. **Send instant notifications** when goals are scored, including:
   - Scorer and assist
   - Current score
   - Country flags
   - Automatic Reddit replay clips (when available)
3. **Alert on special events:**
   - Extra time notifications
   - Penalty shootout alerts
4. **Post automatic summaries** when matches finish with:
   - All goals and assists
   - Official FotMob highlights
   - Final score and penalty results

### Example Notifications

**Goal:**
```
⚽ GOAL! 🇪🇸 Spain 2-1 🇩🇪 Germany

Scorer: Álvaro Morata 67'
Assist: Dani Olmo

🎥 Replay
```

**Post-Match:**
```
🏁 FINAL: 🇪🇸 Spain 3-1 🇩🇪 Germany

⚽ Goals:
12' - Pedri
34' - Morata (Olmo)
67' - Morata

📺 Official Highlights: [Watch](...)
```

## Credits

- Goal notification system inspired by [golazo project](https://github.com/0xjuanma/golazo)
- Data from FotMob.com and Reddit r/soccer
- Built with py-cord
