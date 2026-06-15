"""Latepass tracking system for Discord - tracks URL reposts."""

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from lafcbot.db import (
    get_latepass_leaderboard,
    get_latepass_rank,
    get_latepass_stats,
    get_posted_url,
    get_top_reposted_urls,
    get_viral_urls,
    increment_repost_count,
    save_posted_url,
    update_latepass_score,
)


class LatepassCog(commands.Cog):
    """Cog for tracking URL reposts (latepass system)."""

    def __init__(self, bot):
        self.bot = bot
        # URL pattern to detect URLs in messages
        self.url_pattern = re.compile(r"https?://[^\s<>\"]+|www\.[^\s<>\"]+")
        # Load timezone and config
        self.timezone = self._load_timezone()

    def _load_timezone(self) -> ZoneInfo:
        """Load timezone and latepass config from config.json."""
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


async def setup(bot):
    """Setup function to add the cog."""
    await bot.add_cog(LatepassCog(bot))
