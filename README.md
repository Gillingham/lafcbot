# lafcbot

Discord bot for soccer match information, powered by FotMob data.

## Features

- 🏟️ Match schedules with venue information
- 📺 US TV provider information
- 🏆 League standings
- 🌍 Support for major leagues (MLS, NWSL, World Cup, Premier League, Champions League)
- ⏰ Times displayed in Pacific Time (PT)
- 🚩 Country flags for World Cup matches

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
  "world_cup": {
    "enabled": true,
    "channel_name": "world-cup",
    "live_channel_name": "world-cup-live",
    "daily_time_hour": 8,
    "timezone": "America/Los_Angeles"
  }
}
```

**World Cup Settings:**
- `enabled`: Toggle daily World Cup updates on/off
- `channel_name`: Discord channel name (without #) for daily spoiler-free updates
- `live_channel_name`: Discord channel name (without #) for real-time updates with spoilers
- `daily_time_hour`: Hour (0-23) for daily updates
- `timezone`: IANA timezone name (e.g., "America/Los_Angeles", "America/New_York")

If `config.json` is missing, the bot will run with World Cup updates disabled.

## Commands

### `!matches [league]`
Shows matches for the current day, or the next day with matches if none today.

**Examples:**
```
!matches                # MLS (default)
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

**Examples:**
```
!standings              # MLS (default)
!standings World Cup    # World Cup group standings
!standings Premier      # Premier League table
```

**Output:**
- Top 10 teams per table
- Position, Team, Played, Wins, Draws, Losses, Goal Difference, Points
- Multiple tables for leagues with conferences (e.g., MLS Eastern/Western)

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

- **Match Data:** FotMob.com (via HTML scraping)
- **Venue Information:** Extracted from match details pages
- **TV Providers:** Extracted from match page HTML (US only)

### Time Zones

All times displayed in **Pacific Time (PT)**, automatically handling PST/PDT transitions. "Today" filtering uses Los Angeles timezone.

## Project Structure

```
lafcbot/
├── fotmob/                    # FotMob wrapper library
│   ├── client.py              # HTTP client with rate limiting
│   ├── constants.py           # League IDs and configuration
│   ├── models.py              # Data models
│   ├── parser.py              # HTML/JSON extraction
│   └── __init__.py            # Public API
├── bot.py                     # Discord bot with commands
├── world_cup.py               # World Cup functionality
├── config.json                # Bot configuration (user-created)
├── .pre-commit-config.yaml    # Pre-commit hook configuration
├── ruff.toml                  # Ruff linting rules
├── pyproject.toml             # Dependencies and metadata
└── README.md                  # This file
```

## Dependencies

- `py-cord>=2.0` - Discord bot framework
- `aiohttp>=3.9.0` - Async HTTP client

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

## Credits

- Implementation inspired by [golazo project](https://github.com/0xjuanma/golazo)
- Data from FotMob.com
- Built with py-cord
