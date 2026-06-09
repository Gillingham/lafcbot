"""Daily World Cup match updates and live monitoring task."""

import asyncio
import logging
import traceback
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks

from lafcbot.clients import reddit_client

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

            if live_matches:
                # Matches are live right now! Start monitoring
                logger.info(f"Found {len(live_matches)} live World Cup match(es)")
                self.live_match_ids = {m.id for m in live_matches}

                if (
                    not self.game_monitor_task
                    or not self.game_monitor_task.is_running()
                ):
                    self.monitoring_active = True
                    if self.game_monitor_task is None:
                        self.game_monitor_task = self._create_game_monitor_task()
                    self.game_monitor_task.start()
                    logger.info("Started game monitor for live matches")

            elif upcoming_matches:
                # Schedule check before next match
                next_match = min(upcoming_matches, key=lambda m: m.start_time)
                pre_match_min = self.config.get("live_monitoring", {}).get(
                    "pre_match_minutes", 15
                )
                check_time = next_match.start_time.astimezone(
                    self.timezone
                ) - timedelta(minutes=pre_match_min)

                self.next_check_time = check_time
                match_time_str = next_match.start_time.astimezone(
                    self.timezone
                ).strftime("%a %b %d at %I:%M %p %Z")
                check_time_str = check_time.strftime("%a %b %d at %I:%M %p %Z")

                logger.info(
                    f"Next match: {next_match.home_team.name} vs {next_match.away_team.name} "
                    f"at {match_time_str}. Will start monitoring at {check_time_str}"
                )

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

                if not live_matches:
                    # No more live matches, stop monitoring
                    logger.info("No more live matches, stopping game monitor")
                    self.monitoring_active = False
                    self.live_match_ids.clear()
                    game_monitor.cancel()
                    return

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

                # Check for matches that finished
                await self._check_finished_matches()

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
            # Get detailed match info
            details = await self.fotmob_client.get_match_details(match_id=match.id)
            if not details:
                return

            match_id = match.id

            # Initialize match state if not tracked
            if match_id not in self.monitored_matches:
                self.monitored_matches[match_id] = {
                    "last_events": [],
                    "last_home_score": match.home_score or 0,
                    "last_away_score": match.away_score or 0,
                    "was_live": True,
                    "extra_time_sent": False,
                    "penalties_sent": False,
                }

            state = self.monitored_matches[match_id]

            # Check for new goals
            await self._check_for_goals(details, state, channel)

            # Check for extra time
            await self._check_extra_time(details, state, channel)

            # Check for penalties
            await self._check_penalties(details, state, channel)

            # Update state
            state["last_events"] = [
                {"id": e.id, "type": e.type, "minute": e.minute} for e in details.events
            ]
            state["last_home_score"] = match.home_score or 0
            state["last_away_score"] = match.away_score or 0
            state["was_live"] = True

        except Exception as e:
            logger.error(f"Error monitoring match {match.id}: {e}")

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

        for goal in new_goals:
            await self._send_goal_notification(details, goal, channel)

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
        minute = goal_event.minute

        # Calculate current score (approximate based on events)
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

        score_line = (
            f"{home_flag} {home_team} {home_goals}-{away_goals} {away_team} {away_flag}"
        )

        message = f"⚽ **GOAL!** {score_line}\n\n"

        if goal_event.own_goal:
            message += f"**Own Goal:** {scorer} {minute}'"
        else:
            message += f"**Scorer:** {scorer} {minute}'"
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
                    minute,
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

        except asyncio.TimeoutError:
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

            # Get scores from events
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

            # Get regular time scores
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

            try:
                # Get fresh match details
                details = await self.fotmob_client.get_match_details(match_id=match_id)

                if details and details.match.is_finished:
                    # Match finished, send summary
                    await self._send_match_summary(details)

                    # Remove from monitoring
                    del self.monitored_matches[match_id]

            except Exception as e:
                logger.error(f"Error checking finished match {match_id}: {e}")

    async def _send_match_summary(self, details):
        """Send post-match summary with highlights and goal clips."""
        live_config = self.config.get("live_monitoring", {})
        channel_name = live_config.get("channel_name", "world-cup-live")

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

        # Calculate final score from events
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

        message = "\n".join(lines)

        # Send summary
        await channel.send(message)

        logger.info(f"Sent post-match summary for {home_team} vs {away_team}")
