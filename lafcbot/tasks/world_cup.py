"""Daily World Cup match updates and live monitoring task."""

import asyncio
import logging
import traceback
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks

from lafcbot.clients import reddit_client
from lafcbot.match_events.detectors import (
    is_card_event,
    is_half_event,
    is_substitution_event,
    normalize_half_type,
)
from lafcbot.match_events.notifiers import MatchNotifier
from lafcbot.utils.countries import get_country_flag
from lafcbot.utils.discord_helpers import send_to_channels

# Threshold for considering notifications "stale" (do not send if event/match is older than this)
# Used for: match start notifications and post-match summaries
STALE_EVENT_THRESHOLD = timedelta(minutes=10)

logger = logging.getLogger(__name__)


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

        # Initialize notification handler
        self.notifier = MatchNotifier(
            self.bot, self.config, self.timezone, self.reddit_client
        )

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
                    await send_to_channels(
                        self.bot,
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
                await send_to_channels(
                    self.bot, response, [regular_channel_name, live_channel_name]
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
                        # Normalize half_type to prevent duplicates when API provides inconsistent values
                        "half_type": normalize_half_type(e)
                        if e.type.lower() == "half"
                        else e.half_type,
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
                        await self.notifier.notify_match_start(details)
                        state["start_sent"] = True
                else:
                    logger.info(f"Sending start notification for: {match_name}")
                    await self.notifier.notify_match_start(details)
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
                    # Normalize half_type to prevent duplicates when API provides inconsistent values
                    "half_type": normalize_half_type(e)
                    if e.type.lower() == "half"
                    else e.half_type,
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
            await self.notifier.notify_goal(channel, details, goal)

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
            e for e in details.events if e.id not in old_event_ids and is_card_event(e)
        ]
        logger.debug(
            f"Checking cards: {len(new_cards)} new card event(s) out of {len(details.events)} total events"
        )

        # Since we initialize last_events with all existing events when monitoring starts,
        # new_cards should only contain truly new events.
        for card in new_cards:
            await self.notifier.notify_card(channel, details, card)

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
            if is_substitution_event(e)
            and (e.minute, e.added_time, e.team_id, e.player_name) not in old_subs
        ]

        logger.debug(
            f"Checking substitutions: {len(new_subs)} new substitution event(s)"
        )

        # Since we initialize last_events with all existing events when monitoring starts,
        # new_subs should only contain truly new events.
        for sub in new_subs:
            await self.notifier.notify_substitution(channel, details, sub)

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

        # Normalize half_type for deduplication (same logic as when storing events)
        new_half_events = [e for e in details.events if is_half_event(e)]

        # Filter out events we've already seen, using normalized half_type
        filtered_new_events = []
        for e in new_half_events:
            normalized_half_type = normalize_half_type(e)
            if (e.minute, normalized_half_type) not in old_half_events:
                filtered_new_events.append(e)
                logger.debug(
                    f"New half event detected: minute={e.minute}, "
                    f"half_type={e.half_type} (normalized={normalized_half_type})"
                )
            else:
                logger.debug(
                    f"Skipping duplicate half event: minute={e.minute}, "
                    f"half_type={e.half_type} (normalized={normalized_half_type})"
                )

        logger.debug(
            f"Checking half events: {len(filtered_new_events)} new half event(s) after deduplication"
        )

        # Since we initialize last_events with all existing events when monitoring starts,
        # filtered_new_events should only contain truly new events.
        for half_event in filtered_new_events:
            await self.notifier.notify_half_event(channel, details, half_event)

    async def _check_extra_time(self, details, state, channel):
        """Check for extra time and send notification."""
        notifications_config = self.config.get("live_monitoring", {}).get(
            "notifications", {}
        )
        if not notifications_config.get("extra_time", True):
            return

        if details.extra_time and not state["extra_time_sent"]:
            await self.notifier.notify_extra_time(channel, details)
            state["extra_time_sent"] = True

    async def _check_penalties(self, details, state, channel):
        """Check for penalty shootout and send notification."""
        notifications_config = self.config.get("live_monitoring", {}).get(
            "notifications", {}
        )
        if not notifications_config.get("penalties", True):
            return

        if details.penalties and not state["penalties_sent"]:
            await self.notifier.notify_penalties(channel, details)
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
                    await self.notifier.notify_match_summary(
                        details, STALE_EVENT_THRESHOLD
                    )

                    # Remove from monitoring
                    del self.monitored_matches[match_id]
                elif details:
                    logger.debug(
                        f"Match {details.match.home_team.name} vs {details.match.away_team.name} "
                        f"not finished yet (status: {details.match.status})"
                    )

            except Exception as e:
                logger.error(f"Error checking finished match {match_id}: {e}")
