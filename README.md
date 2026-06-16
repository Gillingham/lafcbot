# lafcbot

Discord bot for soccer match information and fun utilities, powered by FotMob data.

## Features

### Soccer
- 🏟️ Match schedules with venue information
- 📺 US TV provider information
- 🏆 League standings
- 🌍 Support for major leagues (MLS, NWSL, World Cup, Premier League, Champions League)
- ⏰ Times displayed in configurable timezone (default: Pacific Time)
- 🚩 Country flags for World Cup matches
- ⚽ **Real-time goal notifications** for World Cup matches
- 🎥 **Automatic Reddit replay clips** from r/soccer
- 🏁 **Post-match summaries** with highlights
- ⏱️ **Extra time and penalty shootout alerts**

### Utilities
- 🌦️ **Weather** - Current weather conditions with AQI data
- 🏀 **Sports Scores** - Live scores for NBA, MLB, NHL, NFL, F1
- 🔗 **LatePass** - URL repost tracking with scoring system
- 🐼 **PandaPing** - Automated Dodgers home game win/loss announcements
- 🎲 **Dice rolling** - Standard RPG dice notation
- 🎱 **Magic 8-ball** - Answer your burning questions

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

# Create a .env file from the example
cp .env.example .env
# Edit .env and add your DISCORD_TOKEN

# Run the bot
uv run python run.py
```

## Configuration

### Environment Variables

The bot uses a `.env` file for sensitive credentials. Create it in the project root:

```bash
# .env
DISCORD_TOKEN=your_discord_token_here
```

**Important:** The `.env` file is already in `.gitignore` to prevent accidentally committing secrets to version control.

### Bot Settings

The bot uses `config.json` for settings. Create it in the project root:

```json
{
  "timezone": "America/Los_Angeles",
  "log_level": "INFO",
  "match_output_path": null,
  "latepass": {
    "ignored_domains": [
      "tenor.com",
      "giphy.com",
      "gfycat.com",
      "imgur.com"
    ]
  },
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
    "live_monitoring": {
      "enabled": true,
      "channel_name": "world-cup-2026-live",
      "check_interval_seconds": 60,
      "pre_match_minutes": 15,
      "fallback_check_hours": 12,
      "notifications": {
        "goals": true,
        "cards": true,
        "substitutions": true,
        "half_events": true,
        "extra_time": true,
        "penalties": true,
        "include_reddit_clips": true
      }
    },
    "highlights": {
      "reddit_enabled": true,
      "cache_path": "~/.lafcbot/reddit_cache.json"
    }
  },
  "pandaping": {
    "servers": [
      {
        "guild_id": "YOUR_GUILD_ID",
        "channel_name": "other-sports",
        "role_name": "Panda Ping",
        "announce_wins": true,
        "announce_losses": true,
        "daily_reminder": true
      }
    ]
  }
}
```

### Channel-Specific Leagues

Configure which league `!matches` shows by default in each channel. When `!matches` is called without arguments in a mapped channel, it shows that league's matches automatically.

**Valid league identifiers:**
- `mls` - Major League Soccer
- `nwsl` - National Women's Soccer League
- `premier_league` - English Premier League
- `champions_league` - UEFA Champions League
- `world_cup` - FIFA World Cup

**Configuration formats:**

**Single-server (legacy format):** Maps channel names directly to leagues
```json
"channel_leagues": {
  "mls": "mls",
  "premier-league": "premier_league",
  "ucl": "champions_league"
}
```

**Multi-server format:** Maps guild_id to channel-league mappings
```json
"channel_leagues": {
  "123456789012345678": {
    "mls": "mls",
    "premier-league": "premier_league"
  },
  "987654321098765432": {
    "soccer": "champions_league",
    "football": "world_cup"
  }
}
```

Both formats are supported. The bot will check guild-specific mappings first, then fall back to global mappings. In unmapped channels, it defaults to MLS.

**To get your guild ID:** Enable Developer Mode in Discord settings, right-click server name, "Copy Server ID"

### Global Settings

- `timezone`: IANA timezone name (e.g., "America/Los_Angeles", "America/New_York")
  - Used for time displays across the bot (matches, weather, latepass timestamps)
  - Defaults to "America/Los_Angeles" if not specified

### Debugging Settings

- `log_level`: Controls logging verbosity (optional)
  - Valid values: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`
  - Default: `"INFO"` if not specified
  - Use `"DEBUG"` for troubleshooting issues

- `match_output_path`: Directory path for match data JSON dumps (optional)
  - Set to a directory path (e.g., `"test_data"`) to save raw match data from FotMob
  - Set to `null` or omit to disable (default behavior)
  - Useful for debugging match parsing issues or analyzing FotMob's data structure
  - Files are saved as `match_{match_id}_dump.json` in the specified directory
  - Directory is created automatically if it doesn't exist

### LatePass Settings

- `latepass.ignored_domains`: Array of domain names to ignore for URL tracking
  - Useful for excluding GIF/image hosts that are frequently "reposted" but are just media links
  - Supports subdomain matching (e.g., "tenor.com" matches "media.tenor.com")
  - Default domains to consider: `tenor.com`, `giphy.com`, `gfycat.com`, `imgur.com`

### World Cup Settings

**Configuration Format:**

The World Cup feature supports both legacy single-server and new multi-server configurations.

**Multi-server format (recommended):**
```json
"world_cup": {
  "enabled": true,
  "daily_time_hour": 8,
  "servers": [
    {
      "guild_id": "123456789012345678",
      "channel_name": "world-cup-2026",
      "live_channel_name": "world-cup-2026-live"
    },
    {
      "guild_id": "987654321098765432",
      "channel_name": "wc-updates",
      "live_channel_name": "wc-live"
    }
  ],
  "live_monitoring": { ... }
}
```

**Legacy single-server format (still supported):**
```json
"world_cup": {
  "enabled": true,
  "channel_name": "world-cup-2026",
  "live_monitoring": {
    "channel_name": "world-cup-2026-live",
    ...
  }
}
```

**Basic Settings:**
- `enabled`: Toggle all World Cup features on/off
- `daily_time_hour`: Hour (0-23) for daily schedule posts
- `servers`: Array of server configurations (multi-server format)
  - `guild_id`: Discord server/guild ID (required) - Enable Developer Mode, right-click server, "Copy Server ID"
  - `channel_name`: Channel for daily spoiler-free schedules
  - `live_channel_name`: Channel for live match updates

**Live Monitoring:**
- `live_monitoring.enabled`: Enable real-time goal notifications and live match monitoring
- `live_monitoring.check_interval_seconds`: How often to check for updates during matches (default: 60)
- `live_monitoring.pre_match_minutes`: Start monitoring N minutes before kickoff (default: 15)
- `live_monitoring.fallback_check_hours`: How long to sleep if no matches found (default: 12)

**Notifications:**
- `notifications.goals`: Enable goal notifications
- `notifications.cards`: Enable yellow/red card notifications
- `notifications.substitutions`: Enable player substitution notifications
- `notifications.half_events`: Enable half-time and full-time notifications
- `notifications.extra_time`: Enable extra time alerts
- `notifications.penalties`: Enable penalty shootout alerts
- `notifications.include_reddit_clips`: Automatically fetch Reddit replay clips for goals

**Highlights:**
- `highlights.reddit_enabled`: Enable Reddit r/soccer clip searching
- `highlights.cache_path`: Where to cache found clips

If `config.json` is missing, the bot will run with World Cup updates disabled.

### PandaPing Settings

Configure Dodgers game announcements per server:

**Configuration options:**
- `servers`: Array of server configurations (required)
  - `guild_id`: Discord server/guild ID (required) - Enable Developer Mode in Discord, right-click server name, "Copy Server ID"
  - `channel_name`: Channel name for announcements (default: "other-sports")
  - `role_name`: Role to mention (default: "Panda Ping")
  - `announce_wins`: Send notifications for wins (default: true)
  - `announce_losses`: Send notifications for losses (default: true)
  - `daily_reminder`: Send daily reminders at 10 AM (default: true)

**Example configuration:**
```json
"pandaping": {
  "servers": [
    {
      "guild_id": "123456789012345678",
      "channel_name": "other-sports",
      "role_name": "Panda Ping",
      "announce_wins": true,
      "announce_losses": true,
      "daily_reminder": true
    },
    {
      "guild_id": "987654321098765432",
      "channel_name": "dodgers",
      "role_name": "Baseball Fans",
      "announce_wins": true,
      "announce_losses": false,
      "daily_reminder": false
    }
  ]
}
```

**Multi-server support:** You can configure PandaPing for multiple Discord servers by adding multiple entries to the `servers` array. Each server can have different channel names, role names, and notification preferences.

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

### `!stats [stat_type] [league]`
Shows top player statistics for a league.

**If no league is specified**, the command uses the league configured for the current Discord channel. If no stat type is specified, defaults to goals.

**Examples:**
```
!stats                    # Top goals for channel-configured league
!stats goals              # Same as above
!stats assists            # Top assists for channel-configured league
!stats goals wc           # World Cup top scorers
!stats assists mls        # MLS top assists
!stats assist world cup   # World Cup top assists (singular also works)
```

**Stat types:** `goals`, `assists` (or `goal`, `assist`)

**Output includes:**
- Player name
- Team name
- Statistic count
- Top performers (typically top 5)

### Weather Commands

#### `!weather [location]`
Shows current weather conditions with detailed information.

**Examples:**
```
!weather                # Uses your saved location
!weather Seattle        # Weather for Seattle
!weather 90210          # Weather by ZIP code
```

**Output includes:**
- Current temperature (F/C) and conditions
- Feels like temperature
- Humidity percentage
- Wind speed and direction
- Air Quality Index (AQI) with category
- Today's high/low and precipitation chance

**Sample:**
```
Seattle, Washington, United States: 58F overcast; feels 56F; humidity 81%; wind ESE 5 mph; AQI 48 good; Today 59F/49F, 91% rain
```

The bot remembers your last location for quick checks.

### Scores Commands

#### `!scores <league>`
Shows today's scores for a sports league in a single concise line.

**Examples:**
```
!scores              # Show available leagues
!scores mlb          # Major League Baseball: SEA 6 @ BAL 3 Final | NYY 7 @ CLE 5 Bot 10th | ...
!scores nba          # National Basketball Association: SA 76 @ NY 76 5:37 - 3rd
!scores nhl          # National Hockey League: VGK @ CAR (Mon 6/9 8:00 PM)
!scores nfl          # National Football League: SEA @ NE (Sun 9/9 8:20 PM)
!scores f1           # Formula 1: [race results]
```

**Supported leagues:** nba, mlb, nhl, nfl, f1

**Output includes:**
- Live games with current score and clock time
- Final games with final scores
- Scheduled games with localized start time
- All games on a single line separated by ` | `

### LatePass Commands

LatePass automatically tracks URL reposts and maintains a scoring system. See [LATEPASS.md](LATEPASS.md) for complete documentation.

#### `!latepass [user]`
Shows your latepass score or another user's score.

**Examples:**
```
!latepass               # Your score
!latepass @Alice        # Alice's score
```

#### `!latepass leaderboard [limit]`
Shows the server leaderboard (top 10 by default, range 5-50).

#### `!latepass stats`
Shows server-wide statistics (total URLs, reposts, most reposted URL).

#### `!latepass top [limit]`
Shows most reposted URLs (top 10 by default, range 5-25).

#### `!latepass viral [min_reposts]`
Shows viral URLs with high repost counts (10+ by default, range 5-100).

**Scoring System:**
- Original poster: +1 point per repost
- Reposter: -1 point per repost
- Positive scores = sharing fresh content
- Negative scores = reposting others' content

**Auto-tracking:**
When someone reposts a URL, the bot automatically:
- Adds a :LatePass: emoji reaction
- Replies with original poster, time ago, scores, ranks, and total reposts
- Updates both users' scores

### PandaPing Commands

PandaPing automatically monitors Dodgers home games and announces results to the #other-sports channel with role mentions.

#### `!panda`
Check if PandaPing is enabled and active.

#### `!panda status`
Shows current monitoring status, active game info, and next scheduled game.

**Example output:**
```
🐼 PandaPing Status:
Monitoring: Active 🟢
Current Game: Dodgers vs Giants - Top 5th, LAD 3-2
Next Game: Tomorrow at 7:10 PM PT vs Padres (Home)
```

#### `!panda check`
Manually trigger a check for Dodgers game updates (useful for testing or forcing an update).

**Automatic Features:**
- **Game Result Announcements:** When a Dodgers home game ends, automatically posts to #other-sports
  - Wins: Mentions @Panda Ping role with final score
  - Losses: Posts without role mention (still visible but no notification)
  - All results use spoiler tags to hide scores
- **Daily Reminders:** Every day around 10 AM PT (with randomization), posts upcoming home games for the day
- **Smart Monitoring:** Only actively checks during game times to minimize API usage

### Other Commands

- `!ping` - Check bot latency
- `!wut` - Just... wut
- `!dice <notation>` - Roll dice (e.g., `!dice 3d6+2`)
- `!8ball <question>` - Ask the magic 8-ball
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

- **Soccer Match Data:** FotMob.com (via HTML scraping and API)
- **Sports Scores:** ESPN public scoreboard API (NBA, MLB, NHL, NFL, F1)
- **Venue Information:** Extracted from match details pages
- **TV Providers:** Extracted from match page HTML (US only)
- **Goal Replay Clips:** Reddit r/soccer (direct JSON API)
- **Highlights:** FotMob official highlights URLs
- **Weather Data:** Open-Meteo API (free, no API key required)
- **Air Quality:** Open-Meteo Air Quality API

### Reddit Clip Fetching

The bot attempts to fetch goal replay clips from Reddit's r/soccer community using the public JSON API.

**How it works:**

- Uses Reddit's public JSON endpoint (`/r/soccer/search.json`)
- Searches with time filtering (±12 hours from match time)
- Filters by "Media" flair
- Due to Reddit's bot detection, may occasionally return 403 (Forbidden) errors
- Results are cached for 24 hours to minimize API calls

**No configuration needed** - clips are fetched automatically when available.

### Database

The bot uses SQLite for persistent storage:

**Tables:**
- `user` - User preferences (weather locations)
- `posted_urls` - First post tracking for each URL per guild
- `latepass_score` - User scores and rankings per guild

Database is automatically created at `lafcbot.db` on first run.

### Time Zones

Times are displayed in the configured timezone (from `config.json`), defaulting to **Pacific Time (PT)**. Automatically handles PST/PDT transitions. Used for:
- Match times and "today" filtering
- Weather latepass timestamps
- LatePass relative time displays

## Project Structure

```
lafcbot/
├── lafcbot/                   # Main package
│   ├── __init__.py            # Package exports
│   ├── bot.py                 # Discord bot setup and core commands
│   ├── db.py                  # Database operations (SQLite)
│   ├── cogs/                  # Discord command cogs
│   │   ├── __init__.py
│   │   ├── soccer.py          # Soccer commands (matches, standings, match, stats)
│   │   ├── latepass.py        # LatePass URL tracking system
│   │   ├── pandaping.py       # PandaPing Dodgers announcements
│   │   └── misc.py            # Utility commands (weather, scores, dice, 8ball, wut)
│   ├── tasks/                 # Background tasks
│   │   ├── __init__.py
│   │   └── world_cup.py       # World Cup daily schedule + live monitoring
│   └── clients/               # API clients
│       ├── __init__.py
│       ├── fotmob/            # FotMob wrapper library
│       │   ├── client.py      # HTTP client with rate limiting
│       │   ├── constants.py   # League IDs and configuration
│       │   ├── models.py      # Data models (Match, MatchEvent, Highlight, etc.)
│       │   ├── parser.py      # HTML/JSON extraction
│       │   └── __init__.py    # Public API
│       ├── reddit_client.py   # Reddit r/soccer clip fetcher with caching
│       └── open_meteo_client.py  # Open-Meteo weather API client
├── run.py                     # Entry point
├── config.json                # Bot configuration (user-created)
├── lafcbot.db                 # SQLite database (auto-created)
├── LATEPASS.md                # LatePass system documentation
├── WORLD_CUP_FEATURES.md      # Detailed World Cup features documentation
├── .pre-commit-config.yaml    # Pre-commit hook configuration
├── ruff.toml                  # Ruff linting rules
├── pyproject.toml             # Dependencies and metadata
└── README.md                  # This file
```

## Dependencies

- `py-cord>=2.0` - Discord bot framework
- `aiohttp>=3.9.0` - Async HTTP client (for FotMob, Reddit, and weather APIs)
- `beautifulsoup4>=4.12.0` - HTML parsing
- `lxml>=5.0.0` - Fast XML/HTML processing
- `aiosqlite>=0.20.0` - Async SQLite database (for user preferences and latepass tracking)

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

When live monitoring is enabled, the bot uses **smart scheduling** to minimize API calls while ensuring timely notifications:

- **Intelligent scheduling**: Only polls the API when matches are happening
- **Pre-match activation**: Starts monitoring 15 minutes before kickoff (configurable)
- **Auto-sleep**: When no matches are scheduled, sleeps for hours instead of constant polling
- **95% fewer API calls** on non-match days while maintaining full functionality

**During matches, the bot will:**

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
