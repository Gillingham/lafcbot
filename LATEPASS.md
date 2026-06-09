# LatePass - URL Repost Tracking System

## Overview
LatePass automatically tracks URLs posted in Discord channels and identifies reposts, rewarding original posters and tracking content popularity through a scoring system.

## How It Works

### 1. First Post
When a URL is posted for the first time in a guild:
- URL is saved to the database with:
  - URL, guild ID, channel ID
  - User ID and username (original poster)
  - Message ID and timestamp
  - Repost count initialized to 0

### 2. Repost Detection
When someone posts a URL that's already been shared:

**Different user reposts:**
- Bot adds `:LatePass:` emoji reaction (or 🕐 if custom emoji not found)
- Replies with timing, scores, rankings, and repost count
- Updates scores: Reposter -1, Original poster +1
- Increments repost counter

**Same user reposts:**
- No reaction, no reply, no score change
- Users can repost their own links without penalty

## Message Format

```
{original_poster} first posted this link {time_ago}. scores: {orig_name} {score} (#{rank}), {reposter_name} {score} (#{rank}). reposted {count} time/times
```

### Examples

**Low repost count:**
```
Alice first posted this link 5 minutes ago. scores: Alice +6 (#1), Bob +1 (#2). reposted 1 time
```

**Popular content:**
```
Charlie first posted this link 1 hour ago. scores: Charlie +10 (#1), Diana -5 (#5). reposted 8 times
```

**Viral content:**
```
Bob first posted this link just now. scores: Bob +3 (#2), Alice -1 (#4). reposted 23 times
```

## Time Format
- Less than 1 minute: "just now"
- 1-59 minutes: "X minute(s) ago"
- 1-23 hours: "X hour(s) ago"
- 1+ days: "X day(s) ago"

Times are displayed in the timezone configured in `config.json` (default: America/Los_Angeles)

## Scoring System

### Scoring Rules

**When User B reposts User A's link:**
- User A (original poster): **+1 point**
- User B (reposter): **-1 point**

**Special cases:**
- Self-reposts: No score change
- Scores are per-guild (each Discord server independent)

### Score Interpretation

- **Positive score**: More of your links get reposted than you repost others
  - Shows you're sharing fresh, popular content
  - Higher score = better content discovery

- **Negative score**: You repost more than others repost your links
  - You might be behind on the news
  - Lower score = more "latepasses"

- **Zero score**: Either new to the server or balanced posting/reposting

### Rankings

Users are ranked by:
1. **Score** (descending) - Higher scores rank better
2. **User ID** (ascending) - Tie-breaker for equal scores

Rankings are shown in messages as `#1`, `#2`, `#3`, etc.

## Repost Counter

Tracks how many times each URL has been reposted:
- **0**: No reposts yet (original post only)
- **1-3**: Moderately interesting content
- **4-10**: Popular content
- **11+**: Viral or highly valuable content

Counter increments each time someone (other than original poster) shares the URL.

## Database Schema

### Table: user
```sql
CREATE TABLE user (
    user_id TEXT PRIMARY KEY,
    last_weather_location TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

### Table: posted_urls
```sql
CREATE TABLE posted_urls (
    url TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    message_id TEXT NOT NULL,
    posted_at TEXT NOT NULL,
    repost_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (url, guild_id)
)
```
- Tracks first post of each URL per guild
- `repost_count`: Total number of reposts

### Table: latepass_score
```sql
CREATE TABLE latepass_score (
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, guild_id)
)
```
- Tracks each user's score per guild
- Scores start at 0 and can be positive or negative

## Implementation Details

### Database Functions

**URL Tracking:**
- `get_posted_url(url, guild_id)` - Check if URL was posted before
- `save_posted_url(url, guild_id, ...)` - Save new URL post
- `increment_repost_count(url, guild_id)` - Increment counter on repost

**Scoring:**
- `get_latepass_score(user_id, guild_id)` - Get user's score
- `update_latepass_score(user_id, guild_id, delta)` - Update score by delta
- `get_latepass_rank(user_id, guild_id)` - Get score and rank tuple

**Leaderboard & Statistics:**
- `get_latepass_leaderboard(guild_id, limit=10)` - Get ranked users list
- `get_latepass_stats(guild_id)` - Get aggregate statistics (total URLs, reposts, users, most reposted)
- `get_top_reposted_urls(guild_id, limit=10)` - Get most reposted URLs
- `get_viral_urls(guild_id, min_reposts=10)` - Get URLs above repost threshold

### Command Features

- **Command group structure**: Uses `@commands.group()` for subcommands
- **Guild-only**: All commands only work in servers, not DMs
- **Replies to user**: All commands reply to the user's message
- **Configurable limits**: Users can specify custom limits within ranges
- **User-friendly messages**: Clear output with proper formatting
- **Error handling**: Handles missing users gracefully
- **URL truncation**: Long URLs are truncated for readability

### Event Flow

1. **on_message** listener detects URLs in messages
2. Ignores bot messages and DMs (guild-only)
3. For each URL in message:
   - Normalize URL (strip trailing punctuation)
   - Check if posted before
   - If repost and different user:
     - Add reaction
     - Update scores (reposter -1, original +1)
     - Increment repost count
     - Get updated scores, ranks, and count
     - Reply with complete message
   - If first post:
     - Save to database with repost_count=0

## Per-Guild Isolation

All tracking is per-guild (per Discord server):
- URLs tracked separately in each server
- Scores are server-specific
- Repost counts are server-specific
- Same URL can have different stats in different servers

## Ignored Domains

You can configure domains to ignore for latepass tracking in `config.json`:

```json
{
  "latepass": {
    "ignored_domains": [
      "tenor.com",
      "giphy.com",
      "gfycat.com",
      "imgur.com"
    ]
  }
}
```

**Why ignore domains?**
- GIF/image hosting sites (tenor, giphy) are frequently "reposted" but they're just media links
- The same GIF might be sent by multiple people reacting to something
- These aren't really content reposts, just reactions

**How it works:**
- URLs from ignored domains are completely skipped by latepass
- No tracking, no reactions, no score changes
- Supports subdomain matching (e.g., `tenor.com` also matches `media.tenor.com`)

**Default suggestions:**
- `tenor.com` - GIF hosting
- `giphy.com` - GIF hosting
- `gfycat.com` - GIF hosting
- `imgur.com` - Image hosting (optional - you may want to track imgur links)

## Custom Emoji Setup

For best experience, add a custom emoji named `:LatePass:` to your Discord server. The bot will automatically use it. If not found, it falls back to 🕐 (clock emoji).

## Example Usage

### Scenario 1: First Post
```
Alice: Check this out https://example.com/article
```
*(No reaction, URL saved to database with repost_count=0)*

### Scenario 2: First Repost
```
Bob: https://example.com/article
```
*Bot adds :LatePass: reaction and replies:*
```
Alice first posted this link 2 hours ago. scores: Alice +1 (#1), Bob -1 (#2). reposted 1 time
```

### Scenario 3: Multiple Reposts
```
Charlie: https://example.com/article
```
*Bot adds :LatePass: reaction and replies:*
```
Alice first posted this link 1 day ago. scores: Alice +2 (#1), Charlie -1 (#3). reposted 2 times
```

### Scenario 4: Self-Repost
```
Alice: https://example.com/article
```
*(No reaction, no reply - users can repost their own links)*

## Files

### Implementation
- [lafcbot/db.py](lafcbot/db.py) - Database schema and functions
- [lafcbot/cogs/misc.py](lafcbot/cogs/misc.py) - Event listener and message handling

### Configuration
- `config.json` - Timezone setting for time display

## Commands

### `!latepass` - Show Your Score
Shows your own latepass score and rank in the server.

**Example:**
```
!latepass
→ Your latepass score: +15 (#3)
```

### `!latepass @user` - Show Another User's Score
Shows the latepass score and rank for a mentioned user.

**Example:**
```
!latepass @Alice
→ Alice: +25 (#1)
```

If the user hasn't been involved in any latepasses:
```
!latepass @NewUser
→ NewUser hasn't been involved in any latepasses yet.
```

### `!latepass leaderboard [limit]` - Show Leaderboard
Shows the top users by latepass score. Default shows top 10, can specify 5-50.

**Examples:**
```
!latepass leaderboard
→ Latepass Leaderboard - Top 10
  1. Alice: +25
  2. Bob: +15
  3. Charlie: +10
  4. Diana: +5
  5. Eve: +2
  6. Frank: 0
  7. Grace: -1
  8. Henry: -3
  9. Iris: -5
  10. Jack: -8
```

```
!latepass leaderboard 5
→ Shows top 5 users
```

### `!latepass stats` - Show Server Statistics
Shows overall latepass statistics for the server.

**Example:**
```
!latepass stats
→ Latepass Statistics
  Total unique URLs: 342
  Total reposts: 1,248
  Users with scores: 45
  Most reposted: https://example.com/viral-video by Alice (23 times)
```

### `!latepass top [limit]` - Show Most Reposted URLs
Shows the most reposted URLs in the server. Default shows top 10, can specify 5-25.

**Example:**
```
!latepass top 5
→ Most Reposted URLs - Top 5
  1. https://example.com/viral-video
     Posted by Alice, reposted 23 times
  2. https://news.example.com/breaking
     Posted by Bob, reposted 18 times
  3. https://funny.example.com/meme
     Posted by Charlie, reposted 15 times
  4. https://tech.example.com/announcement
     Posted by Diana, reposted 12 times
  5. https://sports.example.com/highlights
     Posted by Eve, reposted 10 times
```

### `!latepass viral [min_reposts]` - Show Viral URLs
Shows URLs with high repost counts. Default minimum is 10 reposts, can specify 5-100.

**Examples:**
```
!latepass viral
→ Viral URLs (10+ reposts)
  1. https://example.com/viral-video
     Posted by Alice, reposted 23 times
  2. https://news.example.com/breaking
     Posted by Bob, reposted 18 times
  3. https://funny.example.com/meme
     Posted by Charlie, reposted 15 times
```

```
!latepass viral 20
→ Viral URLs (20+ reposts)
  1. https://example.com/viral-video
     Posted by Alice, reposted 23 times
```

If no viral URLs:
```
!latepass viral
→ No URLs with 10+ reposts yet in this server.
```
