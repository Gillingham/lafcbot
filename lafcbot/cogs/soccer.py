"""Soccer-related Discord commands for match information and standings."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from lafcbot.bot import load_config
from lafcbot.clients.fotmob import FotMobClient, format_league_name, resolve_league_name
from lafcbot.clients.fotmob.constants import LEAGUE_IDS
from lafcbot.utils.checks import require_fotmob_client
from lafcbot.utils.countries import get_fifa_trigram
from lafcbot.utils.errors import handle_api_errors
from lafcbot.utils.text_image import (
    render_discord_table_to_png,
    render_table_grid_to_png,
)


class SoccerCog(commands.Cog):
    """Cog for soccer match and standings commands."""

    def __init__(self, bot, fotmob_client):
        self.bot = bot
        self.fotmob_client = fotmob_client

        # Initialize formatters
        from lafcbot.formatters.soccer import SoccerFormatter
        from lafcbot.formatters.world_cup import WorldCupFormatter

        timezone = ZoneInfo("America/Los_Angeles")
        self.formatter = SoccerFormatter(timezone)
        self.wc_formatter = WorldCupFormatter(timezone)

    @staticmethod
    def get_league_key_from_id(league_id: int) -> str | None:
        """Get league key from league ID."""
        for key, lid in LEAGUE_IDS.items():
            if lid == league_id:
                return key
        return None

    async def _resolve_league_for_channel(
        self, ctx: commands.Context, league: str | None
    ) -> tuple[str, int, str] | None:
        """
        Resolve league from channel config or explicit name.

        Args:
            ctx: Discord command context
            league: Explicit league name/alias or None to use channel config

        Returns:
            tuple of (league_key, league_id, league_display) if valid
            None if invalid (error message already sent to ctx)
        """
        # Determine league to use
        if league is None:
            # No explicit league provided - check channel configuration
            config = load_config()
            channel_leagues = config.get("channel_leagues", {})
            channel_name = ctx.channel.name if hasattr(ctx.channel, "name") else None
            guild_id = (
                str(ctx.guild.id) if hasattr(ctx, "guild") and ctx.guild else None
            )

            # Support both old format (channel_name: league) and new format (guild_id: {channel_name: league})
            # Try guild-specific lookup first, then fall back to global
            league = None
            if guild_id and isinstance(channel_leagues.get(guild_id), dict):
                # New format: guild-specific channel mappings
                guild_channels = channel_leagues[guild_id]
                if channel_name and channel_name in guild_channels:
                    league = str(guild_channels[channel_name])
            elif channel_name and channel_name in channel_leagues:
                # Old format: global channel mappings
                league = str(channel_leagues[channel_name])

            # Default fallback
            if not league:
                league = "mls"

        # At this point league is always a string
        assert isinstance(league, str)

        # Resolve league name/alias to canonical name and ID
        league_key, league_id = resolve_league_name(league)

        if not league_id or not league_key:
            available_leagues = ", ".join(
                [format_league_name(k) for k in LEAGUE_IDS.keys()]
            )
            await ctx.send(f"Unknown league '{league}'. Available: {available_leagues}")
            return None

        league_display = format_league_name(league_key)
        return league_key, league_id, league_display

    @commands.command()
    @require_fotmob_client()
    @handle_api_errors("matches")
    async def matches(self, ctx: commands.Context, *, league: str | None = None):
        """
        Show matches for a league.

        Usage: !matches [league] [tomorrow|now|later]
        If no league is specified, uses the league configured for this channel.
        Add "tomorrow" to show tomorrow's matches instead of today's.
        Add "now" to show only matches currently in progress.
        Add "later" to show only matches happening later today.

        Examples:
          !matches                # Uses channel-configured league or MLS default
          !matches mls
          !matches World Cup
          !matches World Cup tomorrow
          !matches tomorrow       # Tomorrow's matches for channel-configured league
          !matches now            # Only live matches now
          !matches later          # Only matches happening later today
          !matches Premier now
          !matches Champions later
        """
        # Check for time filters in the league parameter
        show_tomorrow = False
        show_now_only = False
        show_later_only = False

        if league:
            league_lower = league.lower()

            if "tomorrow" in league_lower:
                show_tomorrow = True
                league = league_lower.replace("tomorrow", "").strip()
            elif "now" in league_lower:
                show_now_only = True
                league = league_lower.replace("now", "").strip()
            elif "later" in league_lower:
                show_later_only = True
                league = league_lower.replace("later", "").strip()

            if not league:
                league = None

        # Resolve league from channel config or explicit name
        result = await self._resolve_league_for_channel(ctx, league)
        if result is None:
            return
        league_key, league_id, league_display = result

        league_matches = await self.fotmob_client.get_league_matches(league_id)

        if not league_matches:
            await ctx.send(f"No matches found for {league.upper()}")
            return

        # Get today's date in Los Angeles timezone
        la_tz = ZoneInfo("America/Los_Angeles")
        now_la = datetime.now(la_tz)
        today_la = now_la.date()
        tomorrow_la = today_la + timedelta(days=1)

        # Determine target date based on show_tomorrow flag
        target_date = tomorrow_la if show_tomorrow else today_la

        # Filter matches based on time filter
        target_matches = []
        later_matches = []  # Track later matches for "now" fallback

        for m in league_matches:
            # For "now" filter - only live matches
            if show_now_only:
                if m.is_live:
                    target_matches.append(m)
                # Also collect later matches as fallback
                elif m.start_time:
                    match_time_la = m.start_time.astimezone(la_tz)
                    if match_time_la.date() == today_la and match_time_la > now_la:
                        later_matches.append(m)
            # For "later" filter - only matches after current time today
            elif show_later_only:
                if m.start_time:
                    match_time_la = m.start_time.astimezone(la_tz)
                    if match_time_la.date() == today_la and match_time_la > now_la:
                        target_matches.append(m)
            # For tomorrow or default today view
            else:
                if not show_tomorrow and m.is_live:
                    target_matches.append(m)
                elif m.start_time:
                    match_time_la = m.start_time.astimezone(la_tz)
                    if match_time_la.date() == target_date:
                        target_matches.append(m)

        # For "now" filter: if no live matches, show later matches with different formatting
        # For "later" filter: always show as "Matches Later Today"
        show_later_today = show_later_only
        show_now = show_now_only and bool(
            target_matches
        )  # Only true if we have live matches

        if show_now_only and not target_matches and later_matches:
            await ctx.send(f"No {league_display} matches currently active.")
            target_matches = later_matches
            show_later_today = True

        # Use World Cup formatter for World Cup matches, otherwise use regular formatter
        if league_key == "world_cup":
            responses = await self.wc_formatter.format_daily_matches_message(
                matches=target_matches,
                display_date=target_date,
                is_today=(
                    target_date == today_la and not show_later_today and not show_now
                ),
                fotmob_client=self.fotmob_client,
                is_later_today=show_later_today,
                is_now=show_now,
            )
            # Send each message chunk
            for response in responses:
                await ctx.send(response)
        else:
            response = await self.formatter.format_matches_list(
                matches=target_matches,
                league_name=league_display,
                target_date=target_date,
                is_today=(
                    target_date == today_la and not show_later_today and not show_now
                ),
                is_tomorrow=(target_date == tomorrow_la),
                league_key=league_key,
                is_later_today=show_later_today,
                is_now=show_now,
            )
            await ctx.send(response)

    @commands.command()
    @require_fotmob_client()
    @handle_api_errors("standings")
    async def standings(self, ctx: commands.Context, *, league: str | None = None):
        """
        Show league standings.

        Usage: !standings [league]
        If no league is specified, uses the league configured for this channel.

        Examples:
          !standings              # Uses channel-configured league or MLS default
          !standings mls
          !standings World Cup
          !standings Premier
        """
        # Resolve league from channel config or explicit name
        result = await self._resolve_league_for_channel(ctx, league)
        if result is None:
            return
        league_key, league_id, league_display = result

        standings_data = await self.fotmob_client.get_league_standings(league_id)

        if (
            not standings_data
            or not isinstance(standings_data, list)
            or len(standings_data) == 0
        ):
            await ctx.send(f"No standings found for {league_display}")
            return

        # Extract tables from the data
        data = standings_data[0].get("data", {})
        tables = data.get("tables", [])

        if not tables:
            await ctx.send(f"No standings tables found for {league_display}")
            return

        # Format standings for each table
        group_tables = []
        extra_tables = []

        for table in tables:
            table_name = table.get("leagueName", "Standings")
            table_data = table.get("table", {}).get("all", [])

            if not table_data:
                continue

            # Convert to simple format for formatter
            standings_list = []
            for team in table_data[:10]:
                standings_list.append(
                    {
                        "rank": team.get("idx", 0),
                        "name": team.get("shortName") or team.get("name", "Unknown"),
                        "played": team.get("played", 0),
                        "wins": team.get("wins", 0),
                        "draws": team.get("draws", 0),
                        "losses": team.get("losses", 0),
                        "goal_diff": team.get("goalConDiff", 0),
                        "points": team.get("pts", 0),
                    }
                )

            formatted = await self.formatter.format_standings_table(
                standings_list, table_name, league_key
            )

            if table_name.lower().startswith("best 3rd"):
                extra_tables.append(formatted)
            else:
                group_tables.append(formatted)

        # Special image layout for World Cup group standings
        if league_key == "world_cup" and group_tables:
            try:
                groups_buffer = render_table_grid_to_png(
                    group_tables,
                    overall_title=f"{league_display} Group Standings",
                    columns=2,
                    advancing_third_place_count=8,
                )

                await ctx.send(
                    file=discord.File(
                        fp=groups_buffer,
                        filename="world_cup_group_standings.png",
                    )
                )

                # Send any extra table(s), like Best 3rd placed teams, as separate images
                for i, extra_table in enumerate(extra_tables, start=1):
                    extra_buffer = render_discord_table_to_png(
                        extra_table,
                        default_title="Best 3rd Placed Teams",
                        highlight_top_n=8,
                    )
                    await ctx.send(
                        file=discord.File(
                            fp=extra_buffer,
                            filename=f"world_cup_extra_standings_{i}.png",
                        )
                    )

                return

            except Exception:
                # If image rendering fails, fall back to text below
                pass

        # Fallback: send regular text output
        all_tables = group_tables + extra_tables
        current_batch = []
        current_length = 0

        for table_text in all_tables:
            table_length = len(table_text) + 1

            if current_length + table_length > 1900:
                if current_batch:
                    await ctx.send("\n".join(current_batch))
                current_batch = [table_text]
                current_length = table_length
            else:
                current_batch.append(table_text)
                current_length += table_length

        if current_batch:
            await ctx.send("\n".join(current_batch))

    @commands.command()
    @require_fotmob_client()
    @handle_api_errors("match details")
    async def match(self, ctx: commands.Context, match_id: int):
        """
        Show detailed match summary with highlights and goal clips.

        Usage: !match <match_id>
        Example: !match 4193490
        """
        # Fetch match details
        details = await self.fotmob_client.get_match_details(match_id=match_id)

        if not details:
            await ctx.send(f"Match {match_id} not found")
            return

        match = details.match
        league_key = ""
        if match.league_id:
            key = self.get_league_key_from_id(match.league_id)
            if key:
                league_key = key

        # Use formatter
        message = await self.formatter.format_match_details(details, league_key)
        await ctx.send(message)

    @commands.command()
    @require_fotmob_client()
    @handle_api_errors("statistics")
    async def stats(
        self,
        ctx: commands.Context,
        stat_type: str = "goals",
        *,
        league: str | None = None,
    ):
        """
        Show top player statistics for a league.

        Usage: !stats [stat_type] [league]
        If no league is specified, uses the league configured for this channel.
        Stat types: goals, assists (or goal, assist)

        Examples:
          !stats                    # Top 5 goals for channel-configured league
          !stats goals wc           # World Cup top scorers
          !stats assists mls        # MLS top assists
          !stats assist world cup   # World Cup top assists
        """
        # Normalize stat_type (accept singular and plural forms)
        stat_type_lower = stat_type.lower().strip()
        if stat_type_lower.endswith("s"):
            stat_type_lower = stat_type_lower[:-1]  # Remove trailing 's'

        # Validate stat type
        if stat_type_lower not in ["goal", "assist"]:
            await ctx.send(
                f"Invalid stat type '{stat_type}'. Use: goals, assists (or goal, assist)"
            )
            return

        # Map to FotMob stat type
        fotmob_stat_type = (
            stat_type_lower + "s"
        )  # "goal" -> "goals", "assist" -> "assists"

        # Resolve league from channel config or explicit name
        result = await self._resolve_league_for_channel(ctx, league)
        if result is None:
            return
        league_key, league_id, league_display = result

        # Fetch player stats
        player_stats = await self.fotmob_client.get_league_stats(
            league_id, fotmob_stat_type
        )

        if not player_stats:
            await ctx.send(f"No statistics available yet for {league_display}")
            return

        # Convert to simple format for formatter
        stats_list = []
        for stat in player_stats:
            team_name = stat.team_name or "Unknown"
            fifa_trigram = get_fifa_trigram(team_name)

            stats_list.append(
                {
                    "player_name": truncate_player_name(
                        stat.player_name, max_length=15
                    ),
                    "team_name": fifa_trigram or team_name,
                    fotmob_stat_type: stat.stat_value,
                }
            )

        # Use formatter
        message = await self.formatter.format_player_stats(
            stats_list, fotmob_stat_type, league_display
        )

        try:
            image_buffer = render_discord_table_to_png(
                message,
                default_title=f"{league_display} - Top {fotmob_stat_type.capitalize()}",
            )

            filename = f"{league_key}_{fotmob_stat_type}.png".replace(" ", "_").lower()

            await ctx.send(
                content=f"**{league_display} - Top {fotmob_stat_type.capitalize()}**",
                file=discord.File(fp=image_buffer, filename=filename),
            )
        except Exception:
            # Fallback to text if image rendering fails
            await ctx.send(message)


def truncate_player_name(player_name: str, max_length: int = 17) -> str:
    """
    Truncate a player name to fit compact Discord table output.

    Args:
        player_name: Full player name.
        max_length: Maximum number of characters to keep.

    Returns:
        Truncated player name.
    """
    if len(player_name) <= max_length:
        return player_name

    return player_name[: max_length - 1] + "…"


def setup(bot):
    """Setup function to add the cog."""
    config = load_config()
    match_output_path = config.get("match_output_path")
    fotmob_client = FotMobClient(match_output_path=match_output_path)
    bot.add_cog(SoccerCog(bot, fotmob_client))
