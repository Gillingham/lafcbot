"""Daily World Cup match updates and live monitoring task."""

import asyncio
import logging
import traceback
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks

from lafcbot.clients import reddit_client

# Threshold for considering notifications "stale" (do not send if event/match is older than this)
# Used for: match start notifications and post-match summaries
STALE_EVENT_THRESHOLD = timedelta(minutes=10)

logger = logging.getLogger(__name__)


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
        "Haiti": "HT",
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

    # UK Subdivision flags to prevent bot from using UK flags for scotland, english and wales
    SUBDIVISION_FLAGS = {
        "GB-ENG": "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",  # England
        "GB-SCT": "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f",  # Scotland
        "GB-WLS": "\U0001f3f4\U000e0067\U000e0062\U000e0077\U000e006c\U000e0073\U000e007f",  # Wales
    }
    if code in SUBDIVISION_FLAGS:
        return SUBDIVISION_FLAGS[code]
    # Northern Ireland has no official Unicode subdivision flag, plus they arent in the WC anyway.

    # Convert ISO code to flag emoji
    # Each letter becomes a regional indicator symbol (🇦 = U+1F1E6, etc.)
    flag = "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper())
    return flag


def format_minute(event) -> str:
    """Format minute display with added time if present."""
    if event.added_time:
        return f"{event.minute}+{event.added_time}'"
    return f"{event.minute}'"


class WorldCupTask:
    """Handles daily World Cup match updates and live monitoring."""

    def __init__(self, bot, fotmob_client, config: dict):
        """
        Initialize the World Cup task.

        Args:
            bot: Discord bot instance
            fotmob_client: FotMob client instance
            config: World Cup configuration dictionary with keys:
                - enabled: bool
                - channel_name: str
                - live_channel_name: str
                - daily_time_hour: int
                - timezone: str
                - live_monitoring: dict with enabled, check_interval_seconds, etc.
        """
        self.bot = bot
        self.fotmob_client = fotmob_client
        self.config = config
        self.daily_task = None
        self.scheduler_task = None
        self.game_monitor_task = None
        self.reddit_client = reddit_client.RedditGoalFetcher()

        # Load timezone
        tz_name = self.config.get("timezone", "America/Los_Angeles")
        self.timezone = ZoneInfo(tz_name)

        # State tracking for smart scheduling
        self.next_check_time = None
        self.monitoring_active = False
        self.live_match_ids = set()
        self.empty_polls_count = 0  # Track consecutive polls with no live matches

        # State tracking for monitored matches
        # Format: {match_id: {last_events, last_home_score, last_away_score, was_live, extra_time_sent, penalties_sent}}
        self.monitored_matches: dict[int, dict] = {}

    def start(self):
        """Start the World Cup tasks if enabled."""
        if not self.config.get("enabled", False):
            print("World Cup tasks are disabled in config")
            return

        # Start daily task
        if self.daily_task is None:
            self.daily_task = self._create_daily_task()
            self.daily_task.start()
            print("World Cup daily task started")

        # Start smart scheduler for live monitoring if enabled
        live_config = self.config.get("live_monitoring", {})
        if live_config.get("enabled", False):
            if self.scheduler_task is None:
                self.scheduler_task = self._create_scheduler_task()
                self.scheduler_task.start()
                print("World Cup smart scheduler started")

    def stop(self):
        """Stop the World Cup tasks."""
        if self.daily_task and self.daily_task.is_running():
            self.daily_task.cancel()
            print("World Cup daily task stopped")

        if self.scheduler_task and self.scheduler_task.is_running():
            self.scheduler_task.cancel()
            print("World Cup scheduler stopped")

        if self.game_monitor_task and self.game_monitor_task.is_running():
            self.game_monitor_task.cancel()
            print("World Cup game monitor stopped")

        # Close Reddit client
        asyncio.create_task(self.reddit_client.close())

    def _create_daily_task(self):
        """Create and return the daily task loop."""

        @tasks.loop(hours=24)
        async def daily_world_cup_matches():
            """Send World Cup matches to the configured channel daily."""
            if self.fotmob_client is None:
                return

            regular_channel_name = self.config.get("channel_name", "world-cup-2026")
            live_channel_name = self.config.get("live_monitoring", {}).get(
                "channel_name", "world-cup-live"
            )

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
                    await self._send_to_channels(
                        "No World Cup matches scheduled.",
                        [regular_channel_name, live_channel_name],
                    )
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

                regular_channel_name = self.config.get("channel_name", "world-cup-2026")
                live_channel_name = self.config.get("live_monitoring", {}).get(
                    "channel_name", "world-cup-live"
                )
                await self._send_to_channels(
                    response, [regular_channel_name, live_channel_name]
                )
                print(
                    f"Sent daily World Cup matches to {regular_channel_name} and {live_channel_name}"
                )

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

    def _create_scheduler_task(self):
        """Create and return the smart scheduler task loop."""

        @tasks.loop(minutes=5)
        async def scheduler():
            """Smart scheduler that decides when to check for matches."""
            try:
                now = datetime.now(self.timezone)

                # If monitoring is active, don't interfere
                if self.monitoring_active:
                    return

                # If we have a scheduled next check time, wait for it
                if self.next_check_time:
                    if now < self.next_check_time:
                        # Still waiting for scheduled check time
                        return
                    else:
                        # Time to check the schedule!
                        logger.info(f"Scheduled check time reached at {now}")
                        self.next_check_time = None

                # Check for matches and decide next action
                await self._check_schedule()

            except Exception as e:
                logger.error(f"Error in scheduler: {e}", exc_info=True)

        @scheduler.before_loop
        async def before_scheduler():
            """Wait until bot is ready."""
            await self.bot.wait_until_ready()
            logger.info("World Cup smart scheduler starting...")

        return scheduler

    async def _check_schedule(self):
        """Check match schedule and decide next action."""
        try:
            # Get all World Cup matches
            all_matches = await self.fotmob_client.get_league_matches(77)

            if not all_matches:
                logger.info("No World Cup matches found in schedule")
                # Fallback: check again in N hours
                fallback_hours = self.config.get("live_monitoring", {}).get(
                    "fallback_check_hours", 12
                )
                self.next_check_time = datetime.now(self.timezone) + timedelta(
                    hours=fallback_hours
                )
                logger.info(f"Will check again at {self.next_check_time}")
                return

            # Separate matches by status
            live_matches = [m for m in all_matches if m.is_live]
            upcoming_matches = [
                m
                for m in all_matches
                if not m.is_live and not m.is_finished and m.start_time
            ]

            logger.debug(
                f"Schedule check: {len(all_matches)} total matches, {len(live_matches)} live, {len(upcoming_matches)} upcoming"
            )

            if live_matches:
                # Matches are live right now! Start monitoring
                match_names = ", ".join(
                    f"{m.home_team.name} vs {m.away_team.name}" for m in live_matches
                )
                logger.info(
                    f"Found {len(live_matches)} live World Cup match(es): {match_names}"
                )
                self.live_match_ids = {m.id for m in live_matches}

                if (
                    not self.game_monitor_task
                    or not self.game_monitor_task.is_running()
                ):
                    logger.info("Starting game monitor for live matches...")
                    self.monitoring_active = True
                    if self.game_monitor_task is None:
                        self.game_monitor_task = self._create_game_monitor_task()
                    self.game_monitor_task.start()
                    logger.info("Game monitor task started")
                else:
                    logger.debug("Game monitor already running, skipping start")

            elif upcoming_matches:
                # Schedule check before next match
                next_match = min(upcoming_matches, key=lambda m: m.start_time)
                pre_match_min = self.config.get("live_monitoring", {}).get(
                    "pre_match_minutes", 15
                )
                match_time_utc = next_match.start_time
                match_time_local = match_time_utc.astimezone(self.timezone)
                check_time = match_time_local - timedelta(minutes=pre_match_min)
                now = datetime.now(self.timezone)

                self.next_check_time = check_time
                match_time_str = match_time_local.strftime("%a %b %d at %I:%M %p %Z")
                check_time_str = check_time.strftime("%a %b %d at %I:%M %p %Z")
                now_str = now.strftime("%a %b %d at %I:%M %p %Z")

                logger.info(
                    f"Next match: {next_match.home_team.name} vs {next_match.away_team.name}"
                )
                logger.info(
                    f"  Match start time (UTC): {match_time_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
                logger.info(f"  Match start time (local): {match_time_str}")
                logger.info(f"  Current time (local): {now_str}")
                logger.info(f"  Pre-match check scheduled for: {check_time_str}")
                # If we're already past pre-match time, start monitoring now
                if now >= check_time:
                    logger.info(
                        "Current time is past pre-match window, starting monitoring now"
                    )
                    self.monitoring_active = True
                    if self.game_monitor_task is None:
                        self.game_monitor_task = self._create_game_monitor_task()
                    self.game_monitor_task.start()
                    logger.info("Game monitor task started")
                else:
                    logger.info(f"Will start monitoring at {check_time_str}")

            else:
                # No matches with schedule info
                fallback_hours = self.config.get("live_monitoring", {}).get(
                    "fallback_check_hours", 12
                )
                self.next_check_time = datetime.now(self.timezone) + timedelta(
                    hours=fallback_hours
                )
                logger.info(
                    f"No upcoming World Cup matches found, will check again at {self.next_check_time}"
                )

        except Exception as e:
            logger.error(f"Error checking schedule: {e}", exc_info=True)
            # Fallback on error
            fallback_hours = self.config.get("live_monitoring", {}).get(
                "fallback_check_hours", 12
            )
            self.next_check_time = datetime.now(self.timezone) + timedelta(
                hours=fallback_hours
            )

    def _create_game_monitor_task(self):
        """Create and return the game monitor task loop."""
        live_config = self.config.get("live_monitoring", {})
        check_interval = live_config.get("check_interval_seconds", 60)

        @tasks.loop(seconds=check_interval)
        async def game_monitor():
            """Monitor live World Cup matches for goals and events."""
            if self.fotmob_client is None:
                return

            try:
                # Get all live World Cup matches
                live_matches = await self.fotmob_client.get_live_world_cup_matches()
                # If no live matches from API, check if we have any in progress by time window
                if not live_matches:
                    logger.debug(
                        "get_live_world_cup_matches() returned empty, checking by time window..."
                    )
                    all_matches = await self.fotmob_client.get_league_matches(77)
                    now = datetime.now(self.timezone)
                    # Matches are "in progress" if they started within last ~3 hours
                    # (assuming matches last ~2 hours, plus some buffer for delays)
                    live_matches = [
                        m
                        for m in all_matches
                        if m.start_time
                        and not m.is_finished
                        and (
                            now - m.start_time.astimezone(self.timezone)
                        ).total_seconds()
                        < 10800  # 3 hours
                        and (
                            now - m.start_time.astimezone(self.timezone)
                        ).total_seconds()
                        > -600  # not more than 10 min before kickoff
                    ]
                    if live_matches:
                        logger.info(
                            f"Found {len(live_matches)} match(es) in time window (not marked as is_live by API)"
                        )

                # Check for matches that finished before deciding to stop
                await self._check_finished_matches()

                if not live_matches:
                    # No more live matches - but keep polling for a few iterations
                    # to ensure we catch match summaries for recently finished matches
                    self.empty_polls_count += 1

                    # Keep polling for 3 more iterations after no live matches detected
                    # This gives ~3 minutes (3 x 60s) to detect finished matches
                    if self.empty_polls_count >= 3 and not self.monitored_matches:
                        # No live matches AND no monitored matches left, stop monitoring
                        logger.info(
                            f"No more live matches after {self.empty_polls_count} polls and "
                            f"no monitored matches remaining, stopping game monitor"
                        )
                        self.monitoring_active = False
                        self.live_match_ids.clear()
                        self.empty_polls_count = 0
                        game_monitor.cancel()
                        return
                    else:
                        logger.info(
                            f"No live matches found (poll #{self.empty_polls_count}/3), "
                            f"but {len(self.monitored_matches)} match(es) still being monitored for finish status"
                        )
                        # Skip the rest and wait for next iteration
                        return
                else:
                    # Reset counter when we find live matches
                    self.empty_polls_count = 0

                # Find live monitoring channel
                channel_name = live_config.get("channel_name", "world-cup-live")
                channel = None
                for guild in self.bot.guilds:
                    channel = discord.utils.get(guild.channels, name=channel_name)
                    if channel:
                        break

                if not channel:
                    logger.warning(f"Live channel {channel_name} not found")
                    return

                # Check each live match for new events
                for match in live_matches:
                    await self._monitor_match(match, channel)

            except Exception as e:
                logger.error(f"Error in game monitor: {e}")
                logger.error(traceback.format_exc())

        @game_monitor.before_loop
        async def before_game_monitor():
            """Wait until bot is ready."""
            await self.bot.wait_until_ready()
            logger.info("World Cup game monitor starting...")

        return game_monitor

    async def _monitor_match(self, match, channel):
        """
        Monitor a single match for new events.

        Args:
            match: Match object
            channel: Discord channel to send notifications to
        """
        try:
            # Get detailed match info using authenticated endpoint for fresher data
            details = await self.fotmob_client.get_match_details_authenticated(
                match_id=match.id, force_refresh=True
            )
            if not details:
                logger.warning(f"Could not get details for match {match.id}")
                return

            match_id = match.id
            match_name = (
                f"{details.match.home_team.name} vs {details.match.away_team.name}"
            )

            # Initialize match state if not tracked
            if match_id not in self.monitored_matches:
                logger.info(f"Starting to monitor match: {match_name}")
                # Populate last_events with ALL current events so we don't notify
                # about events that already occurred before we started monitoring
                # IMPORTANT: Include half-events if match already started, to avoid
                # sending stale HT/FT notifications when bot starts mid-match
                initial_events = [
                    {
                        "id": e.id,
                        "type": e.type,
                        "minute": e.minute,
                        "added_time": e.added_time,  # For added time distinction
                        "half_type": e.half_type,  # For HT/FT distinction
                        "team_id": e.team_id,  # For substitution distinction
                        "player_name": e.player_name,  # For substitution distinction
                    }
                    for e in details.events
                ]
                self.monitored_matches[match_id] = {
                    "last_events": initial_events,
                    "last_home_score": match.home_score or 0,
                    "last_away_score": match.away_score or 0,
                    "was_live": True,
                    "extra_time_sent": False,
                    "penalties_sent": False,
                    "start_sent": False,
                    "summary_sent": False,
                    "initialized_at": datetime.now(self.timezone),
                    "page_slug": match.page_slug,
                }
                if initial_events:
                    logger.info(
                        f"Initialized monitoring with {len(initial_events)} existing events to avoid duplicates"
                    )

            state = self.monitored_matches[match_id]

            match_started = match.is_live or details.match.is_live
            if not match_started and details.match.start_time:
                now = datetime.now(self.timezone)
                start_time = details.match.start_time.astimezone(self.timezone)
                match_started = start_time <= now <= start_time + timedelta(hours=3)

            if match_started and not state.get("start_sent", False):
                if details.match.start_time:
                    start_time = details.match.start_time.astimezone(self.timezone)
                    now_check = datetime.now(self.timezone)
                    age = now_check - start_time
                    if age > STALE_EVENT_THRESHOLD:
                        logger.info(
                            f"Skipping start notification for {match_name} "
                            f"(start time: {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}, now: {now_check.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
                            f"age: {age.total_seconds():.1f}s, threshold: {STALE_EVENT_THRESHOLD.total_seconds():.1f}s)"
                        )
                        state["start_sent"] = True
                    else:
                        logger.info(f"Sending start notification for: {match_name}")
                        await self._send_match_start_notification(details)
                        state["start_sent"] = True
                else:
                    logger.info(f"Sending start notification for: {match_name}")
                    await self._send_match_start_notification(details)
                    state["start_sent"] = True

            # Check for new events (goals, cards, etc.)
            await self._check_for_events(details, state, channel)

            # Check for extra time
            await self._check_extra_time(details, state, channel)

            # Check for penalties
            await self._check_penalties(details, state, channel)

            # Update state
            state["last_events"] = [
                {
                    "id": e.id,
                    "type": e.type,
                    "minute": e.minute,
                    "added_time": e.added_time,  # For added time distinction
                    "half_type": e.half_type,  # For HT/FT distinction
                    "team_id": e.team_id,  # For substitution distinction
                    "player_name": e.player_name,  # For substitution distinction
                }
                for e in details.events
            ]
            state["last_home_score"] = match.home_score or 0
            state["last_away_score"] = match.away_score or 0
            state["was_live"] = True

        except Exception as e:
            logger.error(f"Error monitoring match {match.id}: {e}")

    async def _send_match_start_notification(self, details):
        """Send a notification when a World Cup match starts."""
        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        kickoff_info = ""
        if match.start_time:
            start_time = match.start_time.astimezone(self.timezone)
            kickoff_info = f"\nKickoff: {start_time.strftime('%b %d, %I:%M %p %Z')}"

        message = (
            f"🟢 **MATCH STARTED:** {home_flag} {home_team} vs {away_team} {away_flag}"
            f"{kickoff_info}\n\n"
            "Live updates are available in the World Cup live channel."
        )

        regular_channel_name = self.config.get("channel_name", "world-cup-2026")
        live_channel_name = self.config.get("live_monitoring", {}).get(
            "channel_name", "world-cup-live"
        )

        logger.debug(
            f"Attempting to send start notification to channels: {regular_channel_name}, {live_channel_name}"
        )
        await self._send_to_channels(message, [regular_channel_name, live_channel_name])
        logger.info(f"Match start notification sent for {home_team} vs {away_team}")

    async def _send_to_channels(self, message, channel_names):
        """Send a message to one or more configured channels."""
        sent_channel_ids = set()
        for channel_name in channel_names:
            if not channel_name:
                logger.debug("Skipping empty channel name")
                continue

            channel = self._find_channel_by_name(channel_name)
            if not channel:
                logger.warning(f"Channel '{channel_name}' not found in any guild")
                continue

            if channel.id in sent_channel_ids:
                logger.debug(
                    f"Channel {channel_name} already has this message, skipping"
                )
                continue

            try:
                await channel.send(message)
                sent_channel_ids.add(channel.id)
                logger.debug(f"Message sent to channel #{channel_name}")
            except Exception as e:
                logger.error(f"Failed to send message to channel {channel_name}: {e}")

    def _find_channel_by_name(self, channel_name):
        """Find a channel object by name across all guilds."""
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.channels, name=channel_name)
            if channel:
                return channel
        return None

    async def _check_for_goals(self, details, state, channel):
        """Check for new goals and send notifications."""
        notifications_config = self.config.get("live_monitoring", {}).get(
            "notifications", {}
        )
        if not notifications_config.get("goals", True):
            return

        # Get current event IDs
        old_event_ids = {e["id"] for e in state["last_events"]}

        # Find new goal events
        new_goals = [
            e
            for e in details.events
            if e.id not in old_event_ids and e.type.lower() == "goal"
        ]

        # Since we now initialize last_events with all existing events when monitoring starts,
        # new_goals should only contain truly new events. No staleness check needed - if the
        # event ID is new, we should notify about it.

        for goal in new_goals:
            await self._send_goal_notification(details, goal, channel)

    async def _check_for_events(self, details, state, channel):
        """Generic event checker that delegates to specific event handlers."""
        try:
            await self._check_for_goals(details, state, channel)
        except Exception as e:
            logger.error(f"Error checking goals: {e}")

        try:
            await self._check_for_cards(details, state, channel)
        except Exception as e:
            logger.error(f"Error checking cards: {e}")
        try:
            await self._check_for_substitutions(details, state, channel)
        except Exception as e:
            logger.error(f"Error checking substitutions: {e}")
        try:
            await self._check_for_half_events(details, state, channel)
        except Exception as e:
            logger.error(f"Error checking half events: {e}")

    async def _check_for_cards(self, details, state, channel):
        """Check for new yellow/red card events and send notifications."""
        notifications_config = self.config.get("live_monitoring", {}).get(
            "notifications", {}
        )
        if not notifications_config.get("cards", True):
            return

        old_event_ids = {e["id"] for e in state["last_events"]}
        new_cards = [
            e
            for e in details.events
            if e.id not in old_event_ids and self._is_card_event(e)
        ]
        logger.debug(
            f"Checking cards: {len(new_cards)} new card event(s) out of {len(details.events)} total events"
        )

        # Since we initialize last_events with all existing events when monitoring starts,
        # new_cards should only contain truly new events.
        for card in new_cards:
            await self._send_card_notification(details, card, channel)

    def _is_card_event(self, event):
        # Prefer explicit card_color if populated by parser
        card_color = getattr(event, "card_color", None)
        if card_color:
            return card_color.lower() in ("yellow", "red")

        # Fall back to event type or description inspection
        try:
            if event.type and str(event.type).lower() == "card":
                return True
        except Exception:
            pass

        event_text = f"{event.type or ''} {event.description or ''}".lower()
        return "card" in event_text and ("yellow" in event_text or "red" in event_text)

    def _get_card_color(self, event):
        # Use explicit card_color when available
        card_color = getattr(event, "card_color", None)
        if card_color:
            return str(card_color).lower()

        event_text = f"{event.type or ''} {event.description or ''}".lower()
        if "red" in event_text and "yellow" not in event_text:
            return "red"
        if "yellow" in event_text:
            return "yellow"
        if "red" in event_text:
            return "red"
        return "card"

    def _is_substitution_event(self, event):
        # Prefer explicit substitution type
        try:
            if event.type and str(event.type).lower() in ("substitution", "sub"):
                return True
        except Exception:
            pass

        # If assist_name and player_name are both present and different,
        # it likely represents a swap (player out and player in)
        if getattr(event, "assist_name", None) and getattr(event, "player_name", None):
            return True

        # Fall back to description containing 'on for' or 'sub'
        event_text = f"{event.type or ''} {event.description or ''}".lower()
        return "on for" in event_text or "sub" in event_text

    async def _check_for_substitutions(self, details, state, channel):
        """Check for substitutions and send notifications."""
        notifications_config = self.config.get("live_monitoring", {}).get(
            "notifications", {}
        )
        if not notifications_config.get("substitutions", True):
            return

        # Substitutions have null eventId (parsed as id=0), so use composite key
        # to distinguish multiple subs: (minute, added_time, team_id, player_out)
        old_subs = {
            (e["minute"], e.get("added_time"), e.get("team_id"), e.get("player_name"))
            for e in state["last_events"]
            if e["type"].lower() == "substitution"
        }

        new_subs = [
            e
            for e in details.events
            if self._is_substitution_event(e)
            and (e.minute, e.added_time, e.team_id, e.player_name) not in old_subs
        ]

        logger.debug(
            f"Checking substitutions: {len(new_subs)} new substitution event(s)"
        )

        # Since we initialize last_events with all existing events when monitoring starts,
        # new_subs should only contain truly new events.
        for sub in new_subs:
            await self._send_substitution_notification(details, sub, channel)

    async def _send_substitution_notification(self, details, sub_event, channel):
        """Send a substitution notification to Discord."""
        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        player_out = sub_event.player_name or "Unknown"
        player_in = getattr(sub_event, "assist_name", None)
        minute_display = format_minute(sub_event)

        team_name = home_team if sub_event.team_id == match.home_team.id else away_team
        team_flag = home_flag if sub_event.team_id == match.home_team.id else away_flag

        emoji = "🔁"
        if player_in:
            message = f"{emoji} **Substitution:** {player_in} on for {player_out} ({team_flag} {team_name}) {minute_display}"
        else:
            message = f"{emoji} **Substitution:** {player_out} ({team_flag} {team_name}) {minute_display}"

        await channel.send(message)

    async def _check_for_half_events(self, details, state, channel):
        """Check for half-time and full-time events."""
        notifications_config = self.config.get("live_monitoring", {}).get(
            "notifications", {}
        )
        if not notifications_config.get("half_events", True):
            return

        # For half-events, use composite key (minute, half_type) since they all have id=0
        # This allows us to distinguish HT (minute 45) from FT (minute 90)
        old_half_events = {
            (e["minute"], e.get("half_type"))
            for e in state["last_events"]
            if e["type"].lower() == "half"
        }

        new_half_events = [
            e
            for e in details.events
            if self._is_half_event(e) and (e.minute, e.half_type) not in old_half_events
        ]

        logger.debug(f"Checking half events: {len(new_half_events)} new half event(s)")

        # Since we initialize last_events with all existing events when monitoring starts,
        # new_half_events should only contain truly new events.
        for half_event in new_half_events:
            await self._send_half_event_notification(details, half_event, channel)

    def _is_half_event(self, event):
        """Check if event is a half-time or full-time event."""
        try:
            if event.type and str(event.type).lower() == "half":
                return True
            etype = str(event.type or "").lower()
            # Normalize check for various halftime/fulltime indicators
            return etype in ("half", "half-time", "ht", "ft", "periodend")
        except Exception:
            pass
        return False

    async def _send_half_event_notification(self, details, half_event, channel):
        """Send a half-time or full-time notification to Discord."""
        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        # Get the half type from the event (HT or FT)
        half_type = half_event.half_type or ("FT" if half_event.minute >= 90 else "HT")

        # Get score directly from match object
        home_goals = match.home_score or 0
        away_goals = match.away_score or 0

        score_line = (
            f"{home_flag} {home_team} {home_goals}-{away_goals} {away_team} {away_flag}"
        )

        if half_type == "HT":
            emoji = "⏸️"
            title = "HALF-TIME"
        else:
            emoji = "🏁"
            title = "FULL-TIME"

        message = f"{emoji} **{title}:** {score_line}"

        await channel.send(message)

    async def _send_card_notification(self, details, card_event, channel):
        """Send a yellow or red card notification to Discord."""
        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        card_color = self._get_card_color(card_event)
        emoji = "🟥" if card_color == "red" else "🟨"
        card_title = "Red Card" if card_color == "red" else "Yellow Card"

        player = card_event.player_name or "Unknown"
        minute_display = format_minute(card_event)
        team_name = home_team if card_event.team_id == match.home_team.id else away_team
        team_flag = home_flag if card_event.team_id == match.home_team.id else away_flag

        message = f"{emoji} **{card_title}:** {player} {minute_display} for {team_flag} {team_name}"
        if card_event.description:
            description = card_event.description.strip()
            if description.lower() not in {"yellow card", "red card"}:
                message += f"\n{description}"

        await channel.send(message)

    async def _send_goal_notification(self, details, goal_event, channel):
        """Send a goal notification to Discord."""
        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name

        # Get flags
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        # Determine which team scored
        scoring_team = (
            home_team if goal_event.team_id == match.home_team.id else away_team
        )

        # Build message
        scorer = goal_event.player_name or "Unknown"
        minute_display = format_minute(goal_event)

        # Get current score directly from match object
        home_goals = match.home_score or 0
        away_goals = match.away_score or 0

        score_line = (
            f"{home_flag} {home_team} {home_goals}-{away_goals} {away_team} {away_flag}"
        )

        message = f"⚽ **GOAL!** {score_line}\n\n"

        if goal_event.own_goal:
            message += f"**Own Goal:** {scorer} {minute_display}"
        else:
            message += f"**Scorer:** {scorer} {minute_display}"
            if goal_event.assist_name:
                message += f"\n**Assist:** {goal_event.assist_name}"

        # Send notification
        sent_msg = await channel.send(message)

        # Try to fetch Reddit clip in background
        if (
            self.config.get("live_monitoring", {})
            .get("notifications", {})
            .get("include_reddit_clips", True)
        ):
            asyncio.create_task(
                self._add_reddit_clip(
                    sent_msg,
                    home_team,
                    away_team,
                    goal_event.minute,
                    match.start_time,
                    scoring_team,
                    home_goals,
                    away_goals,
                )
            )

    async def _add_reddit_clip(
        self,
        message,
        home_team,
        away_team,
        minute,
        match_time,
        scoring_team,
        home_score,
        away_score,
    ):
        """Try to add Reddit clip link to goal notification."""
        try:
            result = await asyncio.wait_for(
                self.reddit_client.search_goal(
                    home_team=home_team,
                    away_team=away_team,
                    minute=minute,
                    match_time=match_time,
                    scoring_team=scoring_team,
                    home_score=home_score,
                    away_score=away_score,
                ),
                timeout=5.0,
            )

            if result:
                # Edit message to add clip link
                new_content = message.content + f"\n\n🎥 [Replay]({result['post_url']})"
                await message.edit(content=new_content)

        except TimeoutError:
            logger.debug(f"Reddit search timed out for goal at {minute}'")
        except Exception as e:
            logger.error(f"Failed to add Reddit clip: {e}")

    async def _check_extra_time(self, details, state, channel):
        """Check for extra time and send notification."""
        notifications_config = self.config.get("live_monitoring", {}).get(
            "notifications", {}
        )
        if not notifications_config.get("extra_time", True):
            return

        if details.extra_time and not state["extra_time_sent"]:
            match = details.match
            home_team = match.home_team.name
            away_team = match.away_team.name
            home_flag = get_country_flag(home_team)
            away_flag = get_country_flag(away_team)

            # Get scores directly from match object
            home_goals = match.home_score or 0
            away_goals = match.away_score or 0

            message = (
                f"⏱️ **EXTRA TIME:** {home_flag} {home_team} {home_goals}-{away_goals} "
                f"{away_team} {away_flag}\n\nThe match is going to extra time!"
            )

            await channel.send(message)
            state["extra_time_sent"] = True

    async def _check_penalties(self, details, state, channel):
        """Check for penalty shootout and send notification."""
        notifications_config = self.config.get("live_monitoring", {}).get(
            "notifications", {}
        )
        if not notifications_config.get("penalties", True):
            return

        if details.penalties and not state["penalties_sent"]:
            match = details.match
            home_team = match.home_team.name
            away_team = match.away_team.name
            home_flag = get_country_flag(home_team)
            away_flag = get_country_flag(away_team)

            # Get regular time scores directly from match object
            home_goals = match.home_score or 0
            away_goals = match.away_score or 0

            message = (
                f"🎯 **PENALTY SHOOTOUT:** {home_flag} {home_team} vs {away_team} {away_flag}\n\n"
                f"After Extra Time: {home_team} {home_goals}-{away_goals} {away_team}\n"
                f"The match will be decided on penalties!"
            )

            await channel.send(message)
            state["penalties_sent"] = True

    async def _check_finished_matches(self):
        """Check for matches that finished and send post-match summaries."""
        # Get list of match IDs we're monitoring
        match_ids = list(self.monitored_matches.keys())

        for match_id in match_ids:
            state = self.monitored_matches[match_id]

            # Only check matches that were live last time
            if not state.get("was_live"):
                continue

            # Skip if we already sent the summary
            if state.get("summary_sent"):
                continue

            try:
                # Get fresh match details
                details = await self.fotmob_client.get_match_details(
                    match_id=match_id,
                    page_slug=state.get("page_slug"),
                )

                if details and details.match.is_finished:
                    logger.info(
                        f"Match {details.match.home_team.name} vs {details.match.away_team.name} finished, sending summary"
                    )
                    # Mark summary as sent BEFORE calling _send_match_summary to prevent
                    # duplicates if the match is checked again before dict deletion
                    state["summary_sent"] = True

                    # Match finished, send summary (may skip if stale or channel not found)
                    await self._send_match_summary(details)

                    # Remove from monitoring
                    del self.monitored_matches[match_id]
                elif details:
                    logger.debug(
                        f"Match {details.match.home_team.name} vs {details.match.away_team.name} "
                        f"not finished yet (status: {details.match.status})"
                    )

            except Exception as e:
                logger.error(f"Error checking finished match {match_id}: {e}")

    async def _send_match_summary(self, details):
        """Send post-match summary with highlights and goal clips."""
        live_config = self.config.get("live_monitoring", {})
        channel_name = live_config.get("channel_name", "world-cup-live")

        # Check if match ended too long ago to send summary
        # Use the last event's minute to calculate actual match duration
        if details.match.start_time and details.events:
            start_time = details.match.start_time.astimezone(self.timezone)

            # Find the last event minute to estimate when the match actually ended
            # FotMob includes Half events with "FT" (full time) which mark the end
            # Include added time for accurate calculation (e.g., 90+5 = 95 minutes)
            last_event_minute = max(
                (
                    e.minute + (e.added_time or 0)
                    for e in details.events
                    if e.minute is not None
                ),
                default=90,
            )

            # Add buffer for post-match activities (typically 5-10 minutes after last event)
            estimated_end_time = start_time + timedelta(minutes=last_event_minute + 10)
            now = datetime.now(self.timezone)
            age_since_end = now - estimated_end_time

            if age_since_end > STALE_EVENT_THRESHOLD:
                logger.info(
                    f"Skipping post-match summary for {details.match.home_team.name} vs {details.match.away_team.name} "
                    f"(last event: minute {last_event_minute}, estimated end: {estimated_end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
                    f"now: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}, age since end: {age_since_end.total_seconds():.1f}s, "
                    f"threshold: {STALE_EVENT_THRESHOLD.total_seconds():.1f}s)"
                )
                return

        # Find channel
        channel = None
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.channels, name=channel_name)
            if channel:
                break

        if not channel:
            return

        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        # Get final score directly from match object
        home_goals = match.home_score or 0
        away_goals = match.away_score or 0

        # Build message
        lines = [
            f"🏁 **FINAL:** {home_flag} {home_team} {home_goals}-{away_goals} {away_team} {away_flag}\n"
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
                minute_display = format_minute(goal)
                goal_line = f"{minute_display} - {scorer}"

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

        message = "\n".join(lines)

        # Send summary
        await self._send_to_channels(message, [channel_name])

        logger.info(f"Sent post-match summary for {home_team} vs {away_team}")
