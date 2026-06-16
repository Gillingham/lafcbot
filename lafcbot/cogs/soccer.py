"""Soccer-related Discord commands for match information and standings."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from discord.ext import commands

from lafcbot.bot import load_config
from lafcbot.clients.fotmob import FotMobClient, format_league_name, resolve_league_name
from lafcbot.clients.fotmob.constants import LEAGUE_IDS


class SoccerCog(commands.Cog):
    """Cog for soccer match and standings commands."""

    def __init__(self, bot, fotmob_client):
        self.bot = bot
        self.fotmob_client = fotmob_client

        # Initialize formatter
        from lafcbot.formatters.soccer import SoccerFormatter

        timezone = ZoneInfo("America/Los_Angeles")
        self.formatter = SoccerFormatter(timezone)

    @staticmethod
    def get_league_key_from_id(league_id: int) -> str | None:
        """Get league key from league ID."""
        for key, lid in LEAGUE_IDS.items():
            if lid == league_id:
                return key
        return None

    @commands.command()
    async def matches(self, ctx: commands.Context, *, league: str | None = None):
        """
        Show matches for a league.

        Usage: !matches [league] [tomorrow]
        If no league is specified, uses the league configured for this channel.
        Add "tomorrow" to show tomorrow's matches instead of today's.

        Examples:
          !matches                # Uses channel-configured league or MLS default
          !matches mls
          !matches World Cup
          !matches World Cup tomorrow
          !matches tomorrow       # Tomorrow's matches for channel-configured league
          !matches Premier
          !matches Champions
        """
        if self.fotmob_client is None:
            await ctx.send(
                "FotMob client not initialized. Please wait for bot to fully start."
            )
            return

        # Check if "tomorrow" is in the league parameter
        show_tomorrow = False
        if league and "tomorrow" in league.lower():
            show_tomorrow = True
            # Remove "tomorrow" from league string
            league = league.lower().replace("tomorrow", "").strip()
            if not league:
                league = None

        # Determine league to use
        if league is None:
            # No explicit league provided - check channel configuration
            config = load_config()
            channel_leagues = config.get("channel_leagues", {})
            channel_name = ctx.channel.name if hasattr(ctx.channel, "name") else None

            if channel_name and channel_name in channel_leagues:
                league = str(channel_leagues[channel_name])
            else:
                league = "mls"  # Default fallback

        # At this point league is always a string
        assert isinstance(league, str)

        # Resolve league name/alias to nonical name and ID
        league_key, league_id = resolve_league_name(league)

        if not league_id or not league_key:
            available_leagues = ", ".join(
                [format_league_name(k) for k in LEAGUE_IDS.keys()]
            )
            await ctx.send(f"Unknown league '{league}'. Available: {available_leagues}")
            return

        league_display = format_league_name(league_key)
        try:
            league_matches = await self.fotmob_client.get_league_matches(league_id)

            if not league_matches:
                await ctx.send(f"No matches found for {league.upper()}")
                return

            # Get today's date in Los Angeles timezone
            la_tz = ZoneInfo("America/Los_Angeles")
            today_la = datetime.now(la_tz).date()
            tomorrow_la = today_la + timedelta(days=1)

            # Determine target date based on show_tomorrow flag
            target_date = tomorrow_la if show_tomorrow else today_la

            # Filter matches for the target date
            target_matches = []
            for m in league_matches:
                if not show_tomorrow and m.is_live:
                    target_matches.append(m)
                elif m.start_time:
                    match_time_la = m.start_time.astimezone(la_tz)
                    if match_time_la.date() == target_date:
                        target_matches.append(m)

            # Use formatter to generate response
            response = await self.formatter.format_matches_list(
                matches=target_matches,
                league_name=league_display,
                target_date=target_date,
                is_today=(target_date == today_la),
                is_tomorrow=(target_date == tomorrow_la),
                league_key=league_key,
            )

            await ctx.send(response)

        except Exception as e:
            import traceback

            await ctx.send(f"Error fetching matches: {e}")
            print(traceback.format_exc())

    @commands.command()
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
        if self.fotmob_client is None:
            await ctx.send(
                "FotMob client not initialized. Please wait for bot to fully start."
            )
            return

        # Determine league to use
        if league is None:
            # No explicit league provided - check channel configuration
            config = load_config()
            channel_leagues = config.get("channel_leagues", {})
            channel_name = ctx.channel.name if hasattr(ctx.channel, "name") else None

            if channel_name and channel_name in channel_leagues:
                league = str(channel_leagues[channel_name])
            else:
                league = "mls"  # Default fallback

        # At this point league is always a string
        assert isinstance(league, str)

        # Resolve league name/alias to canonical name and ID
        league_key, league_id = resolve_league_name(league)

        if not league_id or not league_key:
            available_leagues = ", ".join(
                [format_league_name(k) for k in LEAGUE_IDS.keys()]
            )
            await ctx.send(f"Unknown league '{league}'. Available: {available_leagues}")
            return

        league_display = format_league_name(league_key)

        try:
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
            all_tables = []
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
                            "name": team.get("shortName")
                            or team.get("name", "Unknown"),
                            "played": team.get("played", 0),
                            "wins": team.get("wins", 0),
                            "draws": team.get("draws", 0),
                            "losses": team.get("losses", 0),
                            "goal_diff": team.get("goalConDiff", 0),
                            "points": team.get("pts", 0),
                        }
                    )

                # Use formatter
                formatted = await self.formatter.format_standings_table(
                    standings_list, table_name, league_key
                )
                all_tables.append(formatted)

            # Batch tables into messages that fit Discord's 2000 char limit
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

            # Send remaining batch
            if current_batch:
                await ctx.send("\n".join(current_batch))

        except Exception as e:
            import traceback

            await ctx.send(f"Error fetching standings: {e}")
            print(traceback.format_exc())

    @commands.command()
    async def match(self, ctx: commands.Context, match_id: int):
        """
        Show detailed match summary with highlights and goal clips.

        Usage: !match <match_id>
        Example: !match 4193490
        """
        if self.fotmob_client is None:
            await ctx.send(
                "FotMob client not initialized. Please wait for bot to fully start."
            )
            return

        try:
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

        except Exception as e:
            import traceback

            await ctx.send(f"Error fetching match details: {e}")
            print(traceback.format_exc())

    @commands.command()
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
        if self.fotmob_client is None:
            await ctx.send(
                "FotMob client not initialized. Please wait for bot to fully start."
            )
            return

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

        # Determine league to use
        if league is None:
            # No explicit league provided - check channel configuration
            config = load_config()
            channel_leagues = config.get("channel_leagues", {})
            channel_name = ctx.channel.name if hasattr(ctx.channel, "name") else None

            if channel_name and channel_name in channel_leagues:
                league = str(channel_leagues[channel_name])
            else:
                league = "mls"  # Default fallback

        # Resolve league name/alias to canonical name and ID
        league_key, league_id = resolve_league_name(league)

        if not league_id or not league_key:
            available_leagues = ", ".join(
                [format_league_name(k) for k in LEAGUE_IDS.keys()]
            )
            await ctx.send(f"Unknown league '{league}'. Available: {available_leagues}")
            return

        league_display = format_league_name(league_key)

        try:
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
                stats_list.append(
                    {
                        "player_name": stat.player_name,
                        "team_name": stat.team_name or "Unknown",
                        fotmob_stat_type: stat.stat_value,
                    }
                )

            # Use formatter
            message = await self.formatter.format_player_stats(
                stats_list, fotmob_stat_type, league_display
            )
            await ctx.send(message)

        except Exception as e:
            import traceback

            await ctx.send("Failed to fetch statistics. Please try again.")
            print(f"Error fetching stats: {e}")
            print(traceback.format_exc())


def setup(bot):
    """Setup function to add the cog."""
    config = load_config()
    match_output_path = config.get("match_output_path")
    fotmob_client = FotMobClient(match_output_path=match_output_path)
    bot.add_cog(SoccerCog(bot, fotmob_client))
