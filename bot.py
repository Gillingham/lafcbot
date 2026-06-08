import os
import sys
import re
import random

import discord
from discord.ext import commands, tasks

from fotmob import FotMobClient, resolve_league_name, format_league_name
from fotmob.constants import LEAGUE_IDS


def get_country_flag(country_name: str) -> str:
    """Convert a country name to its flag emoji."""
    # Map common country names to their ISO 3166-1 alpha-2 codes
    country_codes = {
        # UEFA
        "Germany": "DE", "Spain": "ES", "France": "FR", "Italy": "IT",
        "England": "GB-ENG", "Portugal": "PT", "Netherlands": "NL", "Belgium": "BE",
        "Croatia": "HR", "Denmark": "DK", "Switzerland": "CH", "Austria": "AT",
        "Poland": "PL", "Ukraine": "UA", "Sweden": "SE", "Norway": "NO",
        "Czech Republic": "CZ", "Serbia": "RS", "Turkey": "TR", "Greece": "GR",
        "Scotland": "GB-SCT", "Wales": "GB-WLS", "Ireland": "IE", "Northern Ireland": "GB-NIR",

        # CONMEBOL
        "Brazil": "BR", "Argentina": "AR", "Uruguay": "UY", "Colombia": "CO",
        "Chile": "CL", "Peru": "PE", "Ecuador": "EC", "Paraguay": "PY",
        "Venezuela": "VE", "Bolivia": "BO",

        # CONCACAF
        "USA": "US", "United States": "US", "Mexico": "MX", "Canada": "CA",
        "Costa Rica": "CR", "Jamaica": "JM", "Panama": "PA", "Honduras": "HN",

        # AFC
        "Japan": "JP", "South Korea": "KR", "Korea Republic": "KR", "Australia": "AU",
        "Iran": "IR", "Saudi Arabia": "SA", "Qatar": "QA", "UAE": "AE",
        "Iraq": "IQ", "China": "CN", "Thailand": "TH",

        # CAF
        "Nigeria": "NG", "Senegal": "SN", "Morocco": "MA", "Egypt": "EG",
        "Ghana": "GH", "Cameroon": "CM", "Algeria": "DZ", "Tunisia": "TN",
        "South Africa": "ZA", "Ivory Coast": "CI", "Côte d'Ivoire": "CI",

        # OFC
        "New Zealand": "NZ",
    }

    code = country_codes.get(country_name, "")
    if not code:
        return ""

    # Handle special UK countries
    if code.startswith("GB-"):
        # For sub-regions, just use GB flag
        code = "GB"

    # Convert ISO code to flag emoji
    # Each letter becomes a regional indicator symbol (🇦 = U+1F1E6, etc.)
    flag = "".join(chr(0x1F1E6 + ord(c) - ord('A')) for c in code.upper())
    return flag


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
fotmob_client = None


@tasks.loop(hours=24)
async def daily_world_cup_matches():
    """Send World Cup matches to the world-cup-2026 channel daily at 8am PST."""
    if fotmob_client is None:
        return

    # Find the world-cup-2026 channel across all guilds
    channel = None
    for guild in bot.guilds:
        channel = discord.utils.get(guild.channels, name="world-cup-2026")
        if channel:
            break

    if not channel:
        print("Warning: world-cup-2026 channel not found")
        return

    # Get World Cup matches (league ID 77)
    league_id = 77

    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        league_matches = await fotmob_client.get_league_matches(league_id)

        if not league_matches:
            return

        # Get today's date in Los Angeles timezone
        la_tz = ZoneInfo("America/Los_Angeles")
        today_la = datetime.now(la_tz).date()

        # Filter matches to only those from today (in LA time)
        todays_matches = []
        upcoming_by_date = {}

        for m in league_matches:
            if m.is_live:
                todays_matches.append(m)
            elif m.is_finished and m.start_time:
                match_time_la = m.start_time.astimezone(la_tz)
                if match_time_la.date() == today_la:
                    todays_matches.append(m)
            elif not m.is_finished and m.start_time:
                match_time_la = m.start_time.astimezone(la_tz)
                match_date = match_time_la.date()
                if match_date == today_la:
                    todays_matches.append(m)
                else:
                    if match_date not in upcoming_by_date:
                        upcoming_by_date[match_date] = []
                    upcoming_by_date[match_date].append(m)

        # Determine which matches to show
        if todays_matches:
            matches_to_display = todays_matches
            display_date = today_la
        elif upcoming_by_date:
            next_date = min(upcoming_by_date.keys())
            matches_to_display = upcoming_by_date[next_date]
            display_date = next_date
        else:
            await channel.send("No World Cup matches scheduled.")
            return

        # Determine header
        if display_date == today_la:
            date_header = "Today's Matches"
        else:
            date_str = display_date.strftime("%A, %b %d")
            date_header = f"Next Matches - {date_str}"

        lines = ["**World Cup Matches**\n", f"**{date_header}:**"]

        # Only show upcoming matches (no spoilers for finished matches)
        upcoming = [m for m in matches_to_display if not (m.is_live or m.is_finished)]

        # Display upcoming matches with detailed info (limit to 5 for venue/broadcast lookup)
        for match in upcoming[:5]:
            venue_info = None
            us_broadcast_channels = []
            if match.page_slug:
                try:
                    details = await fotmob_client.get_match_details(page_slug=match.page_slug)
                    if details:
                        if details.match.venue:
                            venue_info = details.match.venue
                        if details.broadcast_channels:
                            us_broadcast_channels = [
                                ch.channel_name for ch in details.broadcast_channels
                                if ch.country_name and "USA" in ch.country_name.upper()
                            ]
                except Exception:
                    pass

            home_name = match.home_team.name
            away_name = match.away_team.name
            home_flag = get_country_flag(home_name)
            away_flag = get_country_flag(away_name)
            if home_flag:
                home_name = f"{home_flag} {home_name}"
            if away_flag:
                away_name = f"{away_flag} {away_name}"

            if match.start_time:
                match_time_la = match.start_time.astimezone(la_tz)
                time_str = match_time_la.strftime("%b %d, %I:%M %p PT")
                lines.append(f"{home_name} vs {away_name} - {time_str}")
            else:
                lines.append(f"{home_name} vs {away_name}")

            if venue_info:
                venue_parts = [f"  🏟️ {venue_info.name}"]
                if venue_info.city:
                    venue_parts.append(venue_info.city)
                lines.append(", ".join(venue_parts))

            if us_broadcast_channels:
                lines.append(f"  📺 {', '.join(us_broadcast_channels)}")

        # Show remaining upcoming matches without venue info (6-10)
        if len(upcoming) > 5:
            for match in upcoming[5:10]:
                home_name = match.home_team.name
                away_name = match.away_team.name
                home_flag = get_country_flag(home_name)
                away_flag = get_country_flag(away_name)
                if home_flag:
                    home_name = f"{home_flag} {home_name}"
                if away_flag:
                    away_name = f"{away_flag} {away_name}"

                if match.start_time:
                    match_time_la = match.start_time.astimezone(la_tz)
                    time_str = match_time_la.strftime("%b %d, %I:%M %p PT")
                    lines.append(f"{home_name} vs {away_name} - {time_str}")
                else:
                    lines.append(f"{home_name} vs {away_name}")

        response = "\n".join(lines)
        if len(response) > 2000:
            response = response[:1997] + "..."

        await channel.send(response)
        print(f"Sent daily World Cup matches to {channel.name}")

    except Exception as e:
        import traceback
        print(f"Error in daily World Cup task: {e}")
        print(traceback.format_exc())


@daily_world_cup_matches.before_loop
async def before_daily_task():
    """Wait until the bot is ready and set the time to 8am PST."""
    await bot.wait_until_ready()

    # Calculate time until next 8am PST
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    la_tz = ZoneInfo("America/Los_Angeles")
    now = datetime.now(la_tz)

    # Set target time to 8am today
    target = datetime.combine(now.date(), time(hour=8, minute=0), tzinfo=la_tz)

    # If we've passed 8am today, schedule for tomorrow
    if now >= target:
        from datetime import timedelta
        target = target + timedelta(days=1)

    # Calculate seconds to wait
    wait_seconds = (target - now).total_seconds()

    print(f"Daily World Cup task will start at {target.strftime('%Y-%m-%d %I:%M %p %Z')}")

    import asyncio
    await asyncio.sleep(wait_seconds)


@bot.event
async def on_ready():
    global fotmob_client
    fotmob_client = FotMobClient()

    print(f"Logged in as: {bot.user} (ID: {bot.user.id})")
    print("Connected guilds:")
    for g in bot.guilds:
        # use guild.member_count to avoid iterating members (no privileged intent required)
        print(f"- {g.name} (ID: {g.id}) — {g.member_count} members")
    print("------")

    # Start the daily World Cup task
    if not daily_world_cup_matches.is_running():
        daily_world_cup_matches.start()


@bot.command()
async def ping(ctx: commands.Context):
    """Responds with Pong and latency in ms."""
    await ctx.send(f"Pong! {round(bot.latency * 1000)}ms")


@bot.command()
async def wut(ctx: commands.Context):
    await ctx.send("wut")


@bot.command()
@commands.is_owner()
async def servers(ctx: commands.Context):
    """DMs the command caller the list of guilds the bot is in."""
    lines = [f"{g.name} (ID: {g.id}) — {g.member_count} members" for g in bot.guilds]
    content = "\n".join(lines) or "Not in any guilds"
    try:
        await ctx.author.send(content)
    except Exception:
        await ctx.send("Could not send DM; check your privacy settings.")


@bot.command()
async def matches(ctx: commands.Context, *, league: str = "mls"):
    """
    Show matches for a league.

    Usage: !matches [league]
    Examples:
      !matches
      !matches mls
      !matches World Cup
      !matches Premier
      !matches Champions
    """
    if fotmob_client is None:
        await ctx.send("FotMob client not initialized. Please wait for bot to fully start.")
        return

    # Resolve league name/alias to canonical name and ID
    league_key, league_id = resolve_league_name(league)

    if not league_id or not league_key:
        available_leagues = ", ".join([format_league_name(k) for k in LEAGUE_IDS.keys()])
        await ctx.send(f"Unknown league '{league}'. Available: {available_leagues}")
        return

    league_display = format_league_name(league_key)
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        league_matches = await fotmob_client.get_league_matches(league_id)

        if not league_matches:
            await ctx.send(f"No matches found for {league.upper()}")
            return

        # Get today's date in Los Angeles timezone
        la_tz = ZoneInfo("America/Los_Angeles")
        today_la = datetime.now(la_tz).date()

        # Filter matches to only those from today (in LA time)
        todays_matches = []
        upcoming_by_date = {}

        for m in league_matches:
            if m.is_live:
                todays_matches.append(m)
            elif m.is_finished and m.start_time:
                # Convert to LA timezone for date comparison
                match_time_la = m.start_time.astimezone(la_tz)
                if match_time_la.date() == today_la:
                    todays_matches.append(m)
            elif not m.is_finished and m.start_time:
                # Group upcoming matches by date
                match_time_la = m.start_time.astimezone(la_tz)
                match_date = match_time_la.date()
                if match_date == today_la:
                    todays_matches.append(m)
                else:
                    if match_date not in upcoming_by_date:
                        upcoming_by_date[match_date] = []
                    upcoming_by_date[match_date].append(m)

        # Determine which matches to show
        if todays_matches:
            # Show today's matches
            matches_to_display = todays_matches
            display_date = today_la
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
        else:
            date_str = display_date.strftime("%A, %b %d")
            date_header = f"Next Matches - {date_str}"

        lines = [f"**{league_display} Matches**\n", f"**{date_header}:**"]

        # Separate finished/live matches from upcoming
        finished_or_live = [m for m in matches_to_display if m.is_live or m.is_finished]
        upcoming = [m for m in matches_to_display if not (m.is_live or m.is_finished)]

        # Display finished/live matches first
        for match in finished_or_live[:10]:
            score = f"{match.home_score}-{match.away_score}" if match.home_score is not None else "TBD"
            status_emoji = "🔴" if match.is_live else "✅"

            # Add flag emojis for World Cup matches
            home_name = match.home_team.name
            away_name = match.away_team.name
            if league_key == "world_cup":
                home_flag = get_country_flag(home_name)
                away_flag = get_country_flag(away_name)
                if home_flag:
                    home_name = f"{home_flag} {home_name}"
                if away_flag:
                    away_name = f"{away_flag} {away_name}"

            lines.append(f"{status_emoji} {home_name} {score} {away_name}")

        # Display upcoming matches with detailed info (limit to 5 for venue/broadcast lookup)
        for match in upcoming[:5]:
            match_line_parts = []

            # Get venue and broadcast information if available
            venue_info = None
            us_broadcast_channels = []
            if match.page_slug:
                try:
                    details = await fotmob_client.get_match_details(page_slug=match.page_slug)
                    if details:
                        if details.match.venue:
                            venue_info = details.match.venue
                        # Extract US broadcast channels
                        if details.broadcast_channels:
                            us_broadcast_channels = [
                                ch.channel_name for ch in details.broadcast_channels
                                if ch.country_name and "USA" in ch.country_name.upper()
                            ]
                except Exception:
                    pass  # Continue without venue/broadcast if fetch fails

            # Build match line with flag emojis for World Cup
            home_name = match.home_team.name
            away_name = match.away_team.name
            if league_key == "world_cup":
                home_flag = get_country_flag(home_name)
                away_flag = get_country_flag(away_name)
                if home_flag:
                    home_name = f"{home_flag} {home_name}"
                if away_flag:
                    away_name = f"{away_flag} {away_name}"

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
                # Add flag emojis for World Cup matches
                home_name = match.home_team.name
                away_name = match.away_team.name
                if league_key == "world_cup":
                    home_flag = get_country_flag(home_name)
                    away_flag = get_country_flag(away_name)
                    if home_flag:
                        home_name = f"{home_flag} {home_name}"
                    if away_flag:
                        away_name = f"{away_flag} {away_name}"

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


@bot.command()
async def standings(ctx: commands.Context, *, league: str = "mls"):
    """
    Show league standings.

    Usage: !standings [league]
    Examples:
      !standings mls
      !standings World Cup
      !standings Premier
    """
    if fotmob_client is None:
        await ctx.send("FotMob client not initialized. Please wait for bot to fully start.")
        return

    # Resolve league name/alias to canonical name and ID
    league_key, league_id = resolve_league_name(league)

    if not league_id or not league_key:
        available_leagues = ", ".join([format_league_name(k) for k in LEAGUE_IDS.keys()])
        await ctx.send(f"Unknown league '{league}'. Available: {available_leagues}")
        return

    league_display = format_league_name(league_key)

    try:
        standings_data = await fotmob_client.get_league_standings(league_id)

        if not standings_data or not isinstance(standings_data, list) or len(standings_data) == 0:
            await ctx.send(f"No standings found for {league_display}")
            return

        # Extract tables from the data
        data = standings_data[0].get("data", {})
        tables = data.get("tables", [])

        if not tables:
            await ctx.send(f"No standings tables found for {league_display}")
            return

        # Format standings for each table (e.g., Eastern/Western for MLS)
        responses = []
        for table in tables[:2]:  # Limit to 2 tables to avoid message length issues
            table_name = table.get("leagueName", "Standings")
            table_data = table.get("table", {}).get("all", [])

            if not table_data:
                continue

            lines = [f"**{table_name}**\n"]
            lines.append("```")
            # Header
            lines.append(f"{'#':<3} {'Team':<20} {'P':<3} {'W':<3} {'D':<3} {'L':<3} {'GD':<4} {'Pts':<4}")
            lines.append("-" * 50)

            # Teams (top 10)
            for team in table_data[:10]:
                pos = team.get("idx", 0)
                name = team.get("shortName", team.get("name", "Unknown"))[:18]
                played = team.get("played", 0)
                wins = team.get("wins", 0)
                draws = team.get("draws", 0)
                losses = team.get("losses", 0)
                gd = team.get("goalConDiff", 0)
                pts = team.get("pts", 0)

                lines.append(f"{pos:<3} {name:<20} {played:<3} {wins:<3} {draws:<3} {losses:<3} {gd:<4} {pts:<4}")

            lines.append("```")
            responses.append("\n".join(lines))

        # Send each table as a separate message
        for response in responses:
            await ctx.send(response)

    except Exception as e:
        import traceback
        await ctx.send(f"Error fetching standings: {e}")
        print(traceback.format_exc())


@bot.command()
async def dice(ctx: commands.Context, notation: str):
    """Roll dice in NdM format, e.g. `1d20`, `4d6`, or with modifier `2d8+3`.

    Usage: `!dice 3d6` -> rolls three 6-sided dice and returns the total and individual rolls.
    """
    pattern = r"^\s*(\d{1,3})d(\d{1,4})([+-]\d+)?\s*$"
    m = re.match(pattern, notation)
    if not m:
        await ctx.send("Invalid notation. Use NdM or NdM+K, e.g. `1d20` or `4d6+2`.")
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
    await ctx.send(f"Rolled {notation}: [{rolls_str}] {mod_str} = **{total}**")


async def shutdown():
    """Clean shutdown of async resources."""
    global fotmob_client
    if fotmob_client:
        await fotmob_client.close()


def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("Error: DISCORD_TOKEN environment variable not set.")
        sys.exit(1)

    try:
        bot.run(token)
    finally:
        import asyncio
        if fotmob_client:
            asyncio.run(shutdown())


if __name__ == "__main__":
    main()
