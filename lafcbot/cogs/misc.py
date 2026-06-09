"""Miscellaneous Discord commands for fun."""

import json
import random
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from lafcbot.clients.espn_client import ESPNClient
from lafcbot.clients.open_meteo_client import OpenMeteoClient
from lafcbot.db import (
    get_latepass_leaderboard,
    get_latepass_rank,
    get_latepass_stats,
    get_posted_url,
    get_top_reposted_urls,
    get_user,
    get_viral_urls,
    increment_repost_count,
    save_posted_url,
    set_user_weather_location,
    update_latepass_score,
)


class MiscCog(commands.Cog):
    """Cog for miscellaneous fun commands."""

    def __init__(self, bot):
        self.bot = bot
        self.weather_client = OpenMeteoClient()
        self.espn_client = ESPNClient()
        # URL pattern to detect URLs in messages
        self.url_pattern = re.compile(r"https?://[^\s<>\"]+|www\.[^\s<>\"]+")
        # Load timezone from config
        self.timezone = self._load_timezone()

    def _load_timezone(self) -> ZoneInfo:
        """Load timezone from config.json."""
        config_path = Path(__file__).parent.parent.parent / "config.json"
        try:
            with open(config_path) as f:
                config = json.load(f)
                tz_name = config.get("timezone", "America/Los_Angeles")

                # Load latepass ignored domains
                latepass_config = config.get("latepass", {})
                self.ignored_domains = set(latepass_config.get("ignored_domains", []))

                return ZoneInfo(tz_name)
        except Exception as e:
            print(f"Error loading timezone from config: {e}, using default")
            self.ignored_domains = set()
            return ZoneInfo("America/Los_Angeles")

    def _is_domain_ignored(self, url: str) -> bool:
        """Check if a URL's domain is in the ignore list."""
        try:
            # Extract domain from URL
            from urllib.parse import urlparse

            parsed = urlparse(url if url.startswith("http") else f"http://{url}")
            domain = parsed.netloc.lower()

            # Check if domain or any parent domain is in ignore list
            # e.g., "media.tenor.com" matches "tenor.com"
            for ignored_domain in self.ignored_domains:
                if domain == ignored_domain or domain.endswith(f".{ignored_domain}"):
                    return True

            return False
        except Exception as e:
            print(f"Error parsing URL domain {url}: {e}")
            return False

    @commands.command()
    async def scores(self, ctx: commands.Context, league: str | None = None):
        """Show today's scores for a sports league in a single concise line.

        Usage: !scores <league>
        Available leagues: nba, mlb, nhl, nfl, f1

        Examples:
          !scores              - Show available leagues
          !scores mlb          - Major League Baseball scores
          !scores nba          - NBA scores
          !scores nhl          - NHL scores
          !scores nfl          - NFL scores
          !scores f1           - Formula 1 results
        """
        available = "nba, mlb, nhl, nfl, f1"

        # No league specified - show available leagues
        if league is None:
            await ctx.message.reply(f"Available leagues: {available}")
            return

        # Normalize league to lowercase
        league = league.lower()

        # Check if league is valid
        if league not in ESPNClient.SPORT_PATHS:
            await ctx.message.reply(
                f"Unknown league '{league}'. Available leagues: {available}"
            )
            return

        # Fetch scoreboard
        try:
            league_name, games = await self.espn_client.get_scoreboard(league)

            if not league_name:
                await ctx.message.reply(
                    f"Failed to fetch scores for {league.upper()}. Please try again later."
                )
                return

            if not games:
                await ctx.message.reply(f"No games found for {league_name} today.")
                return

            # Format games as single line
            game_strings = []
            for game in games:
                if game.is_scheduled and game.scheduled_time:
                    # For scheduled games, show time without scores
                    local_time = game.scheduled_time.astimezone(self.timezone)
                    time_str = local_time.strftime("%a %-m/%-d %-I:%M %p")
                    game_str = f"{game.away_team} @ {game.home_team} ({time_str})"
                else:
                    # For in-progress or final games, show scores and status
                    game_str = f"{game.away_team} {game.away_score} @ {game.home_team} {game.home_score} {game.status}"
                game_strings.append(game_str)

            output = f"{league_name}: {' | '.join(game_strings)}"
            await ctx.message.reply(output)

        except Exception as e:
            import traceback

            await ctx.message.reply(f"Error fetching scores: {e}")
            print(traceback.format_exc())

    @commands.command()
    async def wut(self, ctx: commands.Context):
        """Responds with wut."""
        await ctx.send("wut")

    @commands.command()
    async def dice(self, ctx: commands.Context, notation: str):
        """Roll dice in NdM format, e.g. `1d20`, `4d6`, or with modifier `2d8+3`.

        Usage: `!dice 3d6` -> rolls three 6-sided dice and returns the total and individual rolls.
        """
        pattern = r"^\s*(\d{1,3})d(\d{1,4})([+-]\d+)?\s*$"
        m = re.match(pattern, notation)
        if not m:
            await ctx.send(
                "Invalid notation. Use NdM or NdM+K, e.g. `1d20` or `4d6+2`."
            )
            return

        count = int(m.group(1))
        sides = int(m.group(2))
        mod = int(m.group(3) or 0)

        # safety limits
        if count < 1 or count > 200:
            await ctx.send("Number of dice must be between 1 and 200.")
            return
        if sides < 2 or sides > 10000:
            await ctx.send("Number of sides must be between 2 and 10000.")
            return

        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + mod

        # Format response
        rolls_str = ", ".join(str(r) for r in rolls)
        mod_str = f"{mod:+d}" if mod else ""
        await ctx.message.reply(
            f"Rolled {notation}: [{rolls_str}] {mod_str} = **{total}**"
        )

    @commands.command(name="8ball")
    async def eightball(self, ctx: commands.Context, *, _question: str):
        """Ask the magic 8-ball a question and receive a mystical answer.

        Usage: `!8ball Will it rain tomorrow?`
        """
        responses = [
            # Positive responses
            "It is certain.",
            "It is decidedly so.",
            "Without a doubt.",
            "Yes definitely.",
            "You may rely on it.",
            "As I see it, yes.",
            "Most likely.",
            "Outlook good.",
            "Yes.",
            "Signs point to yes.",
            # Non-committal responses
            "Reply hazy, try again.",
            "Ask again later.",
            "Better not tell you now.",
            "Cannot predict now.",
            "Concentrate and ask again.",
            # Negative responses
            "Don't count on it.",
            "My reply is no.",
            "My sources say no.",
            "Outlook not so good.",
            "Very doubtful.",
        ]

        answer = random.choice(responses)
        await ctx.message.reply(f"🎱 {answer}")

    @commands.command()
    async def weather(self, ctx: commands.Context, *, location: str | None = None):
        """Get current weather conditions for a location.

        Usage:
          !weather Seattle           - Get weather for Seattle
          !weather London, UK        - Get weather for London
          !weather 90210            - Get weather by ZIP code
          !weather                  - Get weather for your saved location

        The bot will remember your last location so you can just use !weather next time.
        """

        user_id = str(ctx.author.id)

        # If no location provided, try to get from user preferences
        if location is None:
            prefs = await get_user(user_id)
            if prefs and prefs.get("last_weather_location"):
                location = prefs["last_weather_location"]
            else:
                await ctx.send(
                    "Please specify a location (e.g., `!weather Seattle` or `!weather 90210`). "
                    "I'll remember it for next time!"
                )
                return

        # Fetch weather data
        try:
            weather = await self.weather_client.get_current_weather(location)

            if weather is None:
                await ctx.send(
                    f"Could not find weather data for '{location}'. "
                    "Please check the location and try again."
                )
                return

            # Save location preference for this user
            await set_user_weather_location(user_id, location)

            # Format weather response in compact format
            # Example: Pasadena, CA, US: 72F overcast; feels 71F; humidity 63%; wind WSW 8 mph; AQI 64 moderate; Today 79F/59F, 0% rain
            parts = [
                f"{weather.location}: {weather.temperature_f:.0f}F {weather.conditions.lower()}",
                f"feels {weather.feels_like_f:.0f}F",
                f"humidity {weather.humidity}%",
                f"wind {weather.wind_direction_text()} {weather.wind_speed_mph:.0f} mph",
            ]

            # Add AQI if available
            if weather.air_quality_index is not None:
                parts.append(
                    f"AQI {weather.air_quality_index} {weather.air_quality_category}"
                )

            # Add daily forecast
            parts.append(
                f"Today {weather.temp_max_f:.0f}F/{weather.temp_min_f:.0f}F, {weather.precipitation_probability}% rain"
            )

            response = "; ".join(parts)
            await ctx.message.reply(response)

        except Exception as e:
            import traceback

            await ctx.send(f"Error fetching weather: {e}")
            print(traceback.format_exc())

    @commands.group(invoke_without_command=True)
    async def latepass(self, ctx: commands.Context, user: discord.Member | None = None):
        """Show latepass score for yourself or another user.

        Usage:
          !latepass           - Show your own score
          !latepass @user     - Show another user's score
          !latepass leaderboard - Show server leaderboard
          !latepass stats     - Show server statistics
          !latepass top       - Show most reposted URLs
          !latepass viral     - Show viral URLs (10+ reposts)
        """
        if not ctx.guild:
            await ctx.message.reply("This command only works in servers.")
            return

        guild_id = str(ctx.guild.id)

        # If user specified, show their score, otherwise show command caller's score
        target_user = user if user else ctx.author
        user_id = str(target_user.id)

        score, rank = await get_latepass_rank(user_id, guild_id)

        if rank == 0:
            if user:
                await ctx.message.reply(
                    f"{target_user.display_name} hasn't been involved in any latepasses yet."
                )
            else:
                await ctx.message.reply(
                    "You haven't been involved in any latepasses yet."
                )
        else:
            score_text = f"{score:+d}"
            if user:
                await ctx.message.reply(
                    f"{target_user.display_name}: {score_text} (#{rank})"
                )
            else:
                await ctx.message.reply(f"Your latepass score: {score_text} (#{rank})")

    @latepass.command(name="leaderboard")
    async def latepass_leaderboard(self, ctx: commands.Context, limit: int = 10):
        """Show the latepass leaderboard for this server.

        Usage: !latepass leaderboard [limit]
        Example: !latepass leaderboard 20
        """
        if not ctx.guild:
            await ctx.message.reply("This command only works in servers.")
            return

        # Clamp limit
        limit = max(5, min(limit, 50))

        guild_id = str(ctx.guild.id)
        leaderboard = await get_latepass_leaderboard(guild_id, limit)

        if not leaderboard:
            await ctx.message.reply("No latepass scores yet in this server.")
            return

        # Build leaderboard message
        lines = [f"**Latepass Leaderboard - Top {len(leaderboard)}**"]

        for entry in leaderboard:
            user_id = entry["user_id"]
            score = entry["score"]
            rank = entry["rank"]

            # Try to get the member name
            try:
                member = await ctx.guild.fetch_member(int(user_id))
                name = member.display_name
            except (discord.NotFound, discord.HTTPException, ValueError):
                name = f"User {user_id}"

            lines.append(f"{rank}. {name}: {score:+d}")

        await ctx.message.reply("\n".join(lines))

    @latepass.command(name="stats")
    async def latepass_stats(self, ctx: commands.Context):
        """Show overall latepass statistics for this server.

        Usage: !latepass stats
        """
        if not ctx.guild:
            await ctx.message.reply("This command only works in servers.")
            return

        guild_id = str(ctx.guild.id)
        stats = await get_latepass_stats(guild_id)

        lines = [
            "**Latepass Statistics**",
            f"Total unique URLs: {stats['total_urls']}",
            f"Total reposts: {stats['total_reposts']}",
            f"Users with scores: {stats['total_users']}",
        ]

        if stats["most_reposted"]:
            mr = stats["most_reposted"]
            # Truncate URL if too long
            url_display = mr["url"] if len(mr["url"]) <= 50 else mr["url"][:47] + "..."
            lines.append(
                f"Most reposted: {url_display} by {mr['username']} ({mr['count']} times)"
            )

        await ctx.message.reply("\n".join(lines))

    @latepass.command(name="top")
    async def latepass_top(self, ctx: commands.Context, limit: int = 10):
        """Show the most reposted URLs in this server.

        Usage: !latepass top [limit]
        Example: !latepass top 5
        """
        if not ctx.guild:
            await ctx.message.reply("This command only works in servers.")
            return

        # Clamp limit
        limit = max(5, min(limit, 25))

        guild_id = str(ctx.guild.id)
        top_urls = await get_top_reposted_urls(guild_id, limit)

        if not top_urls:
            await ctx.message.reply("No reposted URLs yet in this server.")
            return

        lines = [f"**Most Reposted URLs - Top {len(top_urls)}**"]

        for i, entry in enumerate(top_urls, start=1):
            url = entry["url"]
            count = entry["repost_count"]
            username = entry["username"]

            # Truncate URL if too long
            url_display = url if len(url) <= 60 else url[:57] + "..."
            times_text = "time" if count == 1 else "times"

            lines.append(
                f"{i}. {url_display}\n   Posted by {username}, reposted {count} {times_text}"
            )

        await ctx.message.reply("\n".join(lines))

    @latepass.command(name="viral")
    async def latepass_viral(self, ctx: commands.Context, min_reposts: int = 10):
        """Show viral URLs (highly reposted) in this server.

        Usage: !latepass viral [min_reposts]
        Example: !latepass viral 15
        """
        if not ctx.guild:
            await ctx.message.reply("This command only works in servers.")
            return

        # Clamp min_reposts
        min_reposts = max(5, min(min_reposts, 100))

        guild_id = str(ctx.guild.id)
        viral_urls = await get_viral_urls(guild_id, min_reposts)

        if not viral_urls:
            await ctx.message.reply(
                f"No URLs with {min_reposts}+ reposts yet in this server."
            )
            return

        lines = [f"**Viral URLs ({min_reposts}+ reposts)**"]

        for i, entry in enumerate(viral_urls, start=1):
            url = entry["url"]
            count = entry["repost_count"]
            username = entry["username"]

            # Truncate URL if too long
            url_display = url if len(url) <= 60 else url[:57] + "..."
            times_text = "time" if count == 1 else "times"

            lines.append(
                f"{i}. {url_display}\n   Posted by {username}, reposted {count} {times_text}"
            )

        await ctx.message.reply("\n".join(lines))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for URLs in messages and track reposts (latepass)."""
        # Ignore bot messages
        if message.author.bot:
            return

        # Only track in guilds (not DMs)
        if not message.guild:
            return

        # Extract URLs from message
        urls = self.url_pattern.findall(message.content)
        if not urls:
            return

        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        user_id = str(message.author.id)
        username = message.author.display_name
        message_id = str(message.id)

        for url in urls:
            # Normalize URL (strip trailing punctuation that might not be part of URL)
            url = url.rstrip(".,;!?)")

            # Check if domain is in ignore list
            if self._is_domain_ignored(url):
                continue

            # Check if URL has been posted before in this guild
            previous_post = await get_posted_url(url, guild_id)

            if previous_post:
                # Check if the same user is reposting their own link
                if previous_post["user_id"] == user_id:
                    # Same user reposting their own link - skip latepass
                    continue

                # This is a repost by a different user - add LatePass reaction and reply
                try:
                    # Try to add custom emoji first, fall back to text if not found
                    try:
                        # Search for LatePass emoji in guild
                        latepass_emoji = discord.utils.get(
                            message.guild.emojis, name="LatePass"
                        )
                        if latepass_emoji:
                            await message.add_reaction(latepass_emoji)
                        else:
                            # Fall back to a standard emoji
                            await message.add_reaction("🕐")
                    except discord.errors.HTTPException:
                        # If custom emoji fails, use standard emoji
                        await message.add_reaction("🕐")

                    # Parse the timestamp and format it in the configured timezone
                    posted_at_utc = datetime.fromisoformat(previous_post["posted_at"])
                    posted_at_local = posted_at_utc.astimezone(self.timezone)
                    now_local = datetime.now(self.timezone)
                    time_diff = now_local - posted_at_local

                    # Format time nicely
                    if time_diff.days > 0:
                        time_str = f"{time_diff.days} day{'s' if time_diff.days != 1 else ''} ago"
                    elif time_diff.seconds >= 3600:
                        hours = time_diff.seconds // 3600
                        time_str = f"{hours} hour{'s' if hours != 1 else ''} ago"
                    elif time_diff.seconds >= 60:
                        minutes = time_diff.seconds // 60
                        time_str = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
                    else:
                        time_str = "just now"

                    # Update latepass scores BEFORE getting ranks
                    # Current user (reposter) gets -1
                    # Original poster gets +1
                    try:
                        await update_latepass_score(user_id, guild_id, -1)
                        await update_latepass_score(
                            previous_post["user_id"], guild_id, 1
                        )
                    except Exception as e:
                        print(f"Error updating latepass scores: {e}")

                    # Increment repost count
                    try:
                        await increment_repost_count(url, guild_id)
                    except Exception as e:
                        print(f"Error incrementing repost count: {e}")

                    # Get updated scores, ranks, and repost count
                    try:
                        original_score, original_rank = await get_latepass_rank(
                            previous_post["user_id"], guild_id
                        )
                        reposter_score, reposter_rank = await get_latepass_rank(
                            user_id, guild_id
                        )

                        # Get the updated repost count
                        updated_post = await get_posted_url(url, guild_id)
                        repost_count = (
                            updated_post["repost_count"] if updated_post else 0
                        )

                        # Format the score display with repost count
                        score_text = f"scores: {previous_post['username']} {original_score:+d} (#{original_rank}), {username} {reposter_score:+d} (#{reposter_rank})"

                        # Add repost count (show as times, not counting the original)
                        times_text = "time" if repost_count == 1 else "times"
                        repost_text = f"reposted {repost_count} {times_text}"

                        # Reply to the message with timing, scores, and repost count
                        await message.reply(
                            f"{previous_post['username']} first posted this link {time_str}. {score_text}. {repost_text}"
                        )
                    except Exception as e:
                        print(f"Error getting latepass ranks: {e}")
                        # Fallback to simple message without scores
                        await message.reply(
                            f"{previous_post['username']} first posted this link {time_str}."
                        )

                except Exception as e:
                    print(f"Error handling latepass for URL {url}: {e}")
            else:
                # First time seeing this URL - save it
                try:
                    await save_posted_url(
                        url, guild_id, channel_id, user_id, username, message_id
                    )
                except Exception as e:
                    print(f"Error saving URL {url}: {e}")


def setup(bot):
    """Setup function to add the cog."""
    bot.add_cog(MiscCog(bot))
