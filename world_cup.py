"""Daily World Cup match updates task."""

import asyncio
import traceback
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks


def get_country_flag(country_name: str) -> str:
    """Convert a country name to its flag emoji."""
    # Map common country names to their ISO 3166-1 alpha-2 codes
    country_codes = {
        # UEFA
        "Germany": "DE",
        "Spain": "ES",
        "France": "FR",
        "Italy": "IT",
        "England": "GB-ENG",
        "Portugal": "PT",
        "Netherlands": "NL",
        "Belgium": "BE",
        "Croatia": "HR",
        "Denmark": "DK",
        "Switzerland": "CH",
        "Austria": "AT",
        "Poland": "PL",
        "Ukraine": "UA",
        "Sweden": "SE",
        "Norway": "NO",
        "Czech Republic": "CZ",
        "Serbia": "RS",
        "Turkey": "TR",
        "Greece": "GR",
        "Scotland": "GB-SCT",
        "Wales": "GB-WLS",
        "Ireland": "IE",
        "Northern Ireland": "GB-NIR",
        # CONMEBOL
        "Brazil": "BR",
        "Argentina": "AR",
        "Uruguay": "UY",
        "Colombia": "CO",
        "Chile": "CL",
        "Peru": "PE",
        "Ecuador": "EC",
        "Paraguay": "PY",
        "Venezuela": "VE",
        "Bolivia": "BO",
        # CONCACAF
        "USA": "US",
        "United States": "US",
        "Mexico": "MX",
        "Canada": "CA",
        "Costa Rica": "CR",
        "Jamaica": "JM",
        "Panama": "PA",
        "Honduras": "HN",
        # AFC
        "Japan": "JP",
        "South Korea": "KR",
        "Korea Republic": "KR",
        "Australia": "AU",
        "Iran": "IR",
        "Saudi Arabia": "SA",
        "Qatar": "QA",
        "UAE": "AE",
        "Iraq": "IQ",
        "China": "CN",
        "Thailand": "TH",
        # CAF
        "Nigeria": "NG",
        "Senegal": "SN",
        "Morocco": "MA",
        "Egypt": "EG",
        "Ghana": "GH",
        "Cameroon": "CM",
        "Algeria": "DZ",
        "Tunisia": "TN",
        "South Africa": "ZA",
        "Ivory Coast": "CI",
        "Côte d'Ivoire": "CI",
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
    flag = "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper())
    return flag


class WorldCupTask:
    """Handles daily World Cup match updates."""

    def __init__(self, bot, fotmob_client, config: dict):
        """
        Initialize the World Cup task.

        Args:
            bot: Discord bot instance
            fotmob_client: FotMob client instance
            config: World Cup configuration dictionary with keys:
                - enabled: bool
                - channel_name: str
                - daily_time_hour: int
                - timezone: str
        """
        self.bot = bot
        self.fotmob_client = fotmob_client
        self.config = config
        self.task = None

    def start(self):
        """Start the daily World Cup task if enabled."""
        if not self.config.get("enabled", False):
            print("World Cup daily task is disabled in config")
            return

        if self.task is None:
            self.task = self._create_task()
            self.task.start()
            print("World Cup daily task started")

    def stop(self):
        """Stop the daily World Cup task."""
        if self.task and self.task.is_running():
            self.task.cancel()
            print("World Cup daily task stopped")

    def _create_task(self):
        """Create and return the task loop."""

        @tasks.loop(hours=24)
        async def daily_world_cup_matches():
            """Send World Cup matches to the configured channel daily."""
            if self.fotmob_client is None:
                return

            # Find the channel across all guilds
            channel_name = self.config.get("channel_name", "world-cup-2026")
            channel = None
            for guild in self.bot.guilds:
                channel = discord.utils.get(guild.channels, name=channel_name)
                if channel:
                    break

            if not channel:
                print(f"Warning: {channel_name} channel not found")
                return

            # Get World Cup matches (league ID 77)
            league_id = 77

            try:
                league_matches = await self.fotmob_client.get_league_matches(league_id)

                if not league_matches:
                    return

                # Get today's date in configured timezone
                tz_name = self.config.get("timezone", "America/Los_Angeles")
                tz = ZoneInfo(tz_name)
                today = datetime.now(tz).date()

                # Filter matches to only those from today (in configured timezone)
                todays_matches = []
                upcoming_by_date = {}

                for m in league_matches:
                    if m.is_live:
                        todays_matches.append(m)
                    elif m.is_finished and m.start_time:
                        match_time = m.start_time.astimezone(tz)
                        if match_time.date() == today:
                            todays_matches.append(m)
                    elif not m.is_finished and m.start_time:
                        match_time = m.start_time.astimezone(tz)
                        match_date = match_time.date()
                        if match_date == today:
                            todays_matches.append(m)
                        else:
                            if match_date not in upcoming_by_date:
                                upcoming_by_date[match_date] = []
                            upcoming_by_date[match_date].append(m)

                # Determine which matches to show
                if todays_matches:
                    matches_to_display = todays_matches
                    display_date = today
                elif upcoming_by_date:
                    next_date = min(upcoming_by_date.keys())
                    matches_to_display = upcoming_by_date[next_date]
                    display_date = next_date
                else:
                    await channel.send("No World Cup matches scheduled.")
                    return

                # Determine header
                if display_date == today:
                    date_header = "Today's Matches"
                else:
                    date_str = display_date.strftime("%A, %b %d")
                    date_header = f"Next Matches - {date_str}"

                lines = ["**World Cup Matches**\n", f"**{date_header}:**"]

                # Only show upcoming matches (no spoilers for finished matches)
                upcoming = [
                    m for m in matches_to_display if not (m.is_live or m.is_finished)
                ]

                # Display upcoming matches with detailed info (limit to 5 for venue/broadcast lookup)
                for match in upcoming[:5]:
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
                                if details.broadcast_channels:
                                    us_broadcast_channels = [
                                        ch.channel_name
                                        for ch in details.broadcast_channels
                                        if ch.country_name
                                        and "USA" in ch.country_name.upper()
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
                        match_time = match.start_time.astimezone(tz)
                        time_str = match_time.strftime("%b %d, %I:%M %p PT")
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
                            match_time = match.start_time.astimezone(tz)
                            time_str = match_time.strftime("%b %d, %I:%M %p PT")
                            lines.append(f"{home_name} vs {away_name} - {time_str}")
                        else:
                            lines.append(f"{home_name} vs {away_name}")

                response = "\n".join(lines)
                if len(response) > 2000:
                    response = response[:1997] + "..."

                await channel.send(response)
                print(f"Sent daily World Cup matches to {channel.name}")

            except Exception as e:
                print(f"Error in daily World Cup task: {e}")
                print(traceback.format_exc())

        @daily_world_cup_matches.before_loop
        async def before_daily_task():
            """Wait until the bot is ready and set the time to configured hour."""
            await self.bot.wait_until_ready()

            # Calculate time until next scheduled time
            tz_name = self.config.get("timezone", "America/Los_Angeles")
            tz = ZoneInfo(tz_name)
            now = datetime.now(tz)

            # Set target time to configured hour today
            hour = self.config.get("daily_time_hour", 8)
            target = datetime.combine(now.date(), time(hour=hour, minute=0), tzinfo=tz)

            # If we've passed the target time today, schedule for tomorrow
            if now >= target:
                target = target + timedelta(days=1)

            # Calculate seconds to wait
            wait_seconds = (target - now).total_seconds()

            print(
                f"Daily World Cup task will start at {target.strftime('%Y-%m-%d %I:%M %p %Z')}"
            )

            await asyncio.sleep(wait_seconds)

        return daily_world_cup_matches
