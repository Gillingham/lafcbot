"""Soccer-related Discord commands for match information and standings."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from discord.ext import commands

from lafcbot.bot import load_config
from lafcbot.clients.fotmob import FotMobClient, format_league_name, resolve_league_name
from lafcbot.clients.fotmob.constants import LEAGUE_IDS
from lafcbot.utils.countries import get_country_flag, get_country_rank


class SoccerCog(commands.Cog):
    """Cog for soccer match and standings commands."""

    def __init__(self, bot, fotmob_client):
        self.bot = bot
        self.fotmob_client = fotmob_client

    @staticmethod
    def clean_team_name(name: str, league_key: str) -> str:
        """Remove unnecessary suffixes from team names based on league context."""
        if league_key == "nwsl" and name.endswith(" (W)"):
            return name[:-4]
        return name

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
            upcoming_by_date = {}

            for m in league_matches:
                if not show_tomorrow and m.is_live:
                    # Only include live matches when showing today
                    target_matches.append(m)
                elif m.is_finished and m.start_time:
                    # Convert to LA timezone for date comparison
                    match_time_la = m.start_time.astimezone(la_tz)
                    if match_time_la.date() == target_date:
                        target_matches.append(m)
                elif not m.is_finished and m.start_time:
                    # Group upcoming matches by date
                    match_time_la = m.start_time.astimezone(la_tz)
                    match_date = match_time_la.date()
                    if match_date == target_date:
                        target_matches.append(m)
                    else:
                        if match_date not in upcoming_by_date:
                            upcoming_by_date[match_date] = []
                        upcoming_by_date[match_date].append(m)

            # Determine which matches to show
            if target_matches:
                # Show target date's matches
                matches_to_display = target_matches
                display_date = target_date
            elif upcoming_by_date:
                # Show next day that has matches
                next_date = min(upcoming_by_date.keys())
                matches_to_display = upcoming_by_date[next_date]
                display_date = next_date
            else:
                matches_to_display = []
                display_date = None

            # Check if we have any matches to display
            if not matches_to_display or display_date is None:
                await ctx.send(f"No matches found for {league_display}")
                return

            # Determine header based on what we're showing
            if display_date == today_la:
                date_header = "Today's Matches"
            elif display_date == tomorrow_la:
                date_header = "Tomorrow's Matches"
            else:
                date_str = display_date.strftime("%A, %b %d")
                date_header = f"Next Matches - {date_str}"

            lines = [f"**{league_display} Matches**\n", f"**{date_header}:**"]

            # Separate finished/live matches from upcoming
            finished_or_live = [
                m for m in matches_to_display if m.is_live or m.is_finished
            ]
            upcoming = [
                m for m in matches_to_display if not (m.is_live or m.is_finished)
            ]

            # Display finished/live matches first
            for match in finished_or_live[:10]:
                score = (
                    f"{match.home_score}-{match.away_score}"
                    if match.home_score is not None
                    else "TBD"
                )
                status_emoji = "🔴" if match.is_live else "✅"

                # Clean team names and add flag emojis for World Cup matches
                home_name = self.clean_team_name(match.home_team.name, league_key)
                away_name = self.clean_team_name(match.away_team.name, league_key)
                if league_key == "world_cup":
                    home_flag = get_country_flag(home_name)
                    home_rank = get_country_rank(home_name) 
                    away_flag = get_country_flag(away_name)
                    away_rank = get_country_rank(away_name)
                    if home_flag:
                        home_rank_text = f" (#{home_rank})" if home_rank is not None else ""
                        home_name = f"{home_flag} {home_name}{home_rank_text}"
                    if away_flag:
                        away_rank_text = f" (#{away_rank})" if away_rank is not None else ""
                        away_name = f"{away_flag} {away_name}{away_rank_text}"

                # Add match time for live matches
                match_line = f"{status_emoji} {home_name} {score} {away_name}"
                if match.is_live and match.match_time_display:
                    match_line += f" ({match.match_time_display})"

                lines.append(match_line)

            # Display upcoming matches with detailed info (limit to 5 for venue/broadcast lookup)
            for match in upcoming[:5]:
                match_line_parts = []

                # Get venue and broadcast information if available
                venue_info = None
                us_broadcast_channels = []
                if match.page_slug:
                    try:
                        details = await self.fotmob_client.get_match_details(
                            page_slug=match.page_slug
                        )
                        if details:
                            if details.match.venue:
                                venue_info = details.match.venue
                            # Extract US broadcast channels
                            if details.broadcast_channels:
                                us_broadcast_channels = [
                                    ch.channel_name
                                    for ch in details.broadcast_channels
                                    if ch.country_name
                                    and "USA" in ch.country_name.upper()
                                ]
                    except Exception:
                        pass  # Continue without venue/broadcast if fetch fails

                # Clean team names and add flag emojis for World Cup
                home_name = self.clean_team_name(match.home_team.name, league_key)
                away_name = self.clean_team_name(match.away_team.name, league_key)
                if league_key == "world_cup":
                    home_flag = get_country_flag(home_name)
                    home_rank = get_country_rank(home_name) 
                    away_flag = get_country_flag(away_name)
                    away_rank = get_country_rank(away_name)
                    if home_flag:
                        home_rank_text = f" (#{home_rank})" if home_rank is not None else ""
                        home_name = f"{home_flag} {home_name}{home_rank_text}"
                    if away_flag:
                        away_rank_text = f" (#{away_rank})" if away_rank is not None else ""
                        away_name = f"{away_flag} {away_name}{away_rank_text}"

                if match.start_time:
                    match_time_la = match.start_time.astimezone(la_tz)
                    time_str = match_time_la.strftime("%b %d, %I:%M %p PT")
                    match_line_parts.append(f"{home_name} vs {away_name} - {time_str}")
                else:
                    match_line_parts.append(f"{home_name} vs {away_name}")

                # Add match line
                lines.append(match_line_parts[0])

                # Add venue information if available
                if venue_info:
                    venue_parts = [f"  🏟️ {venue_info.name}"]
                    if venue_info.city:
                        venue_parts.append(venue_info.city)
                    lines.append(", ".join(venue_parts))

                # Add US broadcast channels if available
                if us_broadcast_channels:
                    lines.append(f"  📺 {', '.join(us_broadcast_channels)}")

            # Show remaining upcoming matches without venue info (6-10)
            if len(upcoming) > 5:
                for match in upcoming[5:10]:
                    # Clean team names and add flag emojis for World Cup matches
                    home_name = self.clean_team_name(match.home_team.name, league_key)
                    away_name = self.clean_team_name(match.away_team.name, league_key)
                    if league_key == "world_cup":
                        home_flag = get_country_flag(home_name)
                        home_rank = get_country_rank(home_name) 
                        away_flag = get_country_flag(away_name)
                        away_rank = get_country_rank(away_name)
                        if home_flag:
                            home_rank_text = f" (#{home_rank})" if home_rank is not None else ""
                            home_name = f"{home_flag} {home_name}{home_rank_text}"
                        if away_flag:
                            away_rank_text = f" (#{away_rank})" if away_rank is not None else ""
                            away_name = f"{away_flag} {away_name}{away_rank_text}"

                    if match.start_time:
                        match_time_la = match.start_time.astimezone(la_tz)
                        time_str = match_time_la.strftime("%b %d, %I:%M %p PT")
                        lines.append(f"{home_name} vs {away_name} - {time_str}")
                    else:
                        lines.append(f"{home_name} vs {away_name}")

            response = "\n".join(lines)
            if len(response) > 2000:
                response = response[:1997] + "..."

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

            # Format standings for each table (e.g., Eastern/Western for MLS, Groups for World Cup)
            all_tables = []
            for table in tables:  # Show all tables
                table_name = table.get("leagueName", "Standings")
                table_data = table.get("table", {}).get("all", [])

                if not table_data:
                    continue

                lines = [f"**{table_name}**\n"]
                lines.append("```")
                # Header
                lines.append(
                    f"{'#':<3} {'Team':<20} {'P':<3} {'W':<3} {'D':<3} {'L':<3} {'GD':<4} {'Pts':<4}"
                )
                lines.append("-" * 50)

                # Teams (top 10 or all for small groups)
                for team in table_data[:10]:
                    pos = team.get("idx", 0)
                    name = team.get("shortName", team.get("name", "Unknown"))
                    name = self.clean_team_name(name, league_key)[:18]
                    played = team.get("played", 0)
                    wins = team.get("wins", 0)
                    draws = team.get("draws", 0)
                    losses = team.get("losses", 0)
                    gd = team.get("goalConDiff", 0)
                    pts = team.get("pts", 0)

                    lines.append(
                        f"{pos:<3} {name:<20} {played:<3} {wins:<3} {draws:<3} {losses:<3} {gd:<4} {pts:<4}"
                    )

                lines.append("```")
                all_tables.append("\n".join(lines))

            # Batch tables into messages that fit Discord's 2000 char limit
            current_batch = []
            current_length = 0

            for table_text in all_tables:
                table_length = len(table_text) + 1  # +1 for newline separator

                # If adding this table would exceed limit, send current batch
                if current_length + table_length > 1900:  # Leave some buffer
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
            league_key = (
                self.get_league_key_from_id(match.league_id)
                if match.league_id
                else None
            )

            home_team = self.clean_team_name(match.home_team.name, league_key or "")
            away_team = self.clean_team_name(match.away_team.name, league_key or "")

            # Get flags if World Cup match
            home_flag = ""
            away_flag = ""
            if match.league_id == 77:  # World Cup
                home_flag = get_country_flag(home_team)
                away_flag = get_country_flag(away_team)

            home_goals = len(
                [
                    e
                    for e in details.events
                    if e.type.lower() == "goal" and e.team_id == match.home_team.id
                ]
            )
            away_goals = len(
                [
                    e
                    for e in details.events
                    if e.type.lower() == "goal" and e.team_id == match.away_team.id
                ]
            )

            # Build message
            status_emoji = (
                "🏁" if match.is_finished else "🔴" if match.is_live else "📅"
            )

            home_display = f"{home_flag} {home_team}" if home_flag else home_team
            away_display = f"{away_flag} {away_team}" if away_flag else away_team

            lines = [
                f"{status_emoji} **{home_display} {home_goals}-{away_goals} {away_display}**\n"
            ]

            # Add penalty result if applicable
            if details.penalties:
                lines.append(
                    f"**Penalties:** {home_team} {details.penalties.home_score}-{details.penalties.away_score} {away_team}\n"
                )

            # Add goals
            goal_events = [e for e in details.events if e.type.lower() == "goal"]
            if goal_events:
                lines.append("**⚽ Goals:**")
                for goal in goal_events:
                    scorer = goal.player_name or "Unknown"
                    minute = goal.minute
                    goal_line = f"{minute}' - {scorer}"

                    if goal.own_goal:
                        goal_line += " (OG)"
                    elif goal.assist_name:
                        goal_line += f" ({goal.assist_name})"

                    lines.append(goal_line)
                lines.append("")

            # Add official highlights if available
            if details.highlight:
                lines.append(
                    f"📺 **Official Highlights:** [Watch]({details.highlight.url})"
                )

            # Add venue info if available
            if match.venue:
                venue_text = match.venue.name
                if match.venue.city:
                    venue_text += f", {match.venue.city}"
                lines.append(f"🏟️ **Venue:** {venue_text}")

            message = "\n".join(lines)

            # Truncate if too long
            if len(message) > 2000:
                message = message[:1997] + "..."

            await ctx.send(message)

        except Exception as e:
            import traceback

            await ctx.send(f"Error fetching match details: {e}")
            print(traceback.format_exc())


def setup(bot):
    """Setup function to add the cog."""
    config = load_config()
    match_output_path = config.get("match_output_path")
    fotmob_client = FotMobClient(match_output_path=match_output_path)
    bot.add_cog(SoccerCog(bot, fotmob_client))
