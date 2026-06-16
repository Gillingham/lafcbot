"""PandaPing cog for announcing Dodgers home wins."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import aiosqlite
import discord
from discord.ext import commands, tasks

from lafcbot.clients.espn_client import ESPNClient

logger = logging.getLogger(__name__)


class PandaPingCog(commands.Cog):
    """Cog for announcing Dodgers home wins to #other-sports."""

    def __init__(self, bot):
        self.bot = bot
        self.espn_client = ESPNClient()
        self.timezone = self._load_timezone()
        self.channel_name = "other-sports"
        self.role_name = "Panda Ping"

        # State tracking
        self.current_game = None
        self.next_game_time = None
        self.monitoring_active = False

        # Database path for persistent state
        self.db_path = Path(__file__).parent.parent.parent / "lafcbot.db"

        # Start the main scheduler
        self.scheduler.start()

    def _load_timezone(self) -> ZoneInfo:
        """Load timezone from config.json."""
        config_path = Path(__file__).parent.parent.parent / "config.json"
        try:
            with open(config_path) as f:
                config = json.load(f)
                tz_name = config.get("timezone", "America/Los_Angeles")
                return ZoneInfo(tz_name)
        except Exception as e:
            logger.error(f"Error loading timezone from config: {e}, using default")
            return ZoneInfo("America/Los_Angeles")

    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.scheduler.cancel()
        if self.game_monitor.is_running():
            self.game_monitor.cancel()

    @tasks.loop(minutes=1)
    async def scheduler(self):
        """Main scheduler that decides what to do next."""
        try:
            now = datetime.now(self.timezone)

            # If we have a scheduled next game time, wait for it
            if self.next_game_time:
                if now < self.next_game_time:
                    # Still waiting for next game to start
                    return
                else:
                    # Time to check the game!
                    logger.info(f"Scheduled game time reached at {now}")
                    self.next_game_time = None

            # If we're already monitoring a game, don't check schedule
            if self.monitoring_active:
                return

            # Check for Dodgers games
            await self._check_dodgers_schedule()

        except Exception as e:
            logger.error(f"Error in scheduler: {e}", exc_info=True)

    @scheduler.before_loop
    async def before_scheduler(self):
        """Wait until bot is ready before starting scheduler."""
        await self.bot.wait_until_ready()
        await self._init_database()

    async def _init_database(self):
        """Initialize the database table for tracking sent panda pings."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS panda_pings (
                    game_id TEXT PRIMARY KEY,
                    away_team TEXT NOT NULL,
                    home_score INTEGER NOT NULL,
                    away_score INTEGER NOT NULL,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.commit()

    async def _has_ping_been_sent(self, game_id: str) -> bool:
        """Check if a panda ping has already been sent for this game."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM panda_pings WHERE game_id = ?", (game_id,)
            )
            result = await cursor.fetchone()
            return result is not None

    async def _mark_ping_sent(
        self, game_id: str, away_team: str, home_score: int, away_score: int
    ):
        """Record that a panda ping has been sent for this game."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO panda_pings (game_id, away_team, home_score, away_score)
                VALUES (?, ?, ?, ?)
                """,
                (game_id, away_team, home_score, away_score),
            )
            await db.commit()

    async def _check_dodgers_schedule(self):
        """Check ESPN MLB schedule for Dodgers home games."""
        try:
            league_name, games = await self.espn_client.get_scoreboard("mlb")

            if not games:
                logger.info("No MLB games found in schedule")
                return

            # Find Dodgers home game
            dodgers_game = None
            for game in games:
                if game.home_team == "LAD":  # Dodgers home game
                    dodgers_game = game
                    break

            if not dodgers_game:
                # No Dodgers home game today, check again tomorrow
                logger.info("No Dodgers home game found today")
                tomorrow = datetime.now(self.timezone) + timedelta(days=1)
                self.next_game_time = tomorrow.replace(
                    hour=8, minute=0, second=0, microsecond=0
                )
                logger.info(f"Will check again at {self.next_game_time}")
                return

            # Found a Dodgers home game
            if dodgers_game.is_scheduled:
                # Game hasn't started yet, schedule monitoring for game time
                if dodgers_game.scheduled_time:
                    game_start = dodgers_game.scheduled_time.astimezone(self.timezone)
                    self.next_game_time = game_start
                    logger.info(
                        f"Dodgers home game scheduled at {game_start}, will start monitoring then"
                    )
                else:
                    # No scheduled time available, check again in an hour
                    self.next_game_time = datetime.now(self.timezone) + timedelta(
                        hours=1
                    )
                    logger.info(
                        "Dodgers game scheduled but no start time, checking again in 1 hour"
                    )
            else:
                # Game is in progress or finished, start monitoring
                self.current_game = dodgers_game
                logger.info(
                    f"Dodgers game in progress/finished: {dodgers_game.away_team} @ {dodgers_game.home_team} ({dodgers_game.status})"
                )

                if not self.game_monitor.is_running():
                    self.monitoring_active = True
                    self.game_monitor.start()

        except Exception as e:
            logger.error(f"Error checking Dodgers schedule: {e}", exc_info=True)

    @tasks.loop(minutes=30)
    async def game_monitor(self):
        """Monitor the current Dodgers game every 30 minutes during play."""
        try:
            league_name, games = await self.espn_client.get_scoreboard("mlb")

            if not games:
                logger.warning("No MLB games found during monitoring")
                return

            # Find Dodgers home game
            dodgers_game = None
            for game in games:
                if game.home_team == "LAD":
                    dodgers_game = game
                    break

            if not dodgers_game:
                # Game is no longer in the schedule, stop monitoring
                logger.info("Dodgers game no longer in schedule, stopping monitor")
                self.monitoring_active = False
                self.current_game = None
                self.game_monitor.cancel()
                return

            # Check if game is finished
            if dodgers_game.status == "Final":
                logger.info(
                    f"Dodgers game finished: {dodgers_game.away_team} {dodgers_game.away_score} @ LAD {dodgers_game.home_score}"
                )

                # Check if we already sent a ping for this game
                game_id = dodgers_game.game_id
                already_sent = await self._has_ping_been_sent(game_id)

                if already_sent:
                    logger.info(f"Panda ping already sent for game {game_id}, skipping")
                else:
                    # Send panda ping for both wins and losses
                    try:
                        dodgers_score = int(dodgers_game.home_score)
                        opponent_score = int(dodgers_game.away_score)
                        is_win = dodgers_score > opponent_score

                        await self._send_panda_ping(dodgers_game, is_win)
                    except ValueError as e:
                        logger.error(f"Error parsing scores: {e}")

                # Stop monitoring and schedule next check
                self.monitoring_active = False
                self.current_game = None
                self.game_monitor.cancel()

                # Schedule next check for tomorrow morning
                tomorrow = datetime.now(self.timezone) + timedelta(days=1)
                self.next_game_time = tomorrow.replace(
                    hour=8, minute=0, second=0, microsecond=0
                )
                logger.info(f"Game finished, will check again at {self.next_game_time}")
            else:
                # Game still in progress
                logger.info(
                    f"Dodgers game in progress: {dodgers_game.away_team} {dodgers_game.away_score} @ LAD {dodgers_game.home_score} ({dodgers_game.status})"
                )
                self.current_game = dodgers_game

        except Exception as e:
            logger.error(f"Error monitoring game: {e}", exc_info=True)

    async def _send_panda_ping(self, game, is_win: bool):
        """Send the panda ping message to #other-sports.

        Args:
            game: Game object with score information
            is_win: True if Dodgers won, False if they lost
        """
        try:
            # Find the channel
            channel = None
            for guild in self.bot.guilds:
                channel = discord.utils.get(guild.text_channels, name=self.channel_name)
                if channel:
                    break

            if not channel:
                logger.error(f"Channel #{self.channel_name} not found")
                return

            # Find the role
            role = discord.utils.get(channel.guild.roles, name=self.role_name)
            if not role:
                logger.error(
                    f"Role '{self.role_name}' not found in {channel.guild.name}"
                )
                return

            # Build the message with spoiler tags
            scoreline = f"{game.away_team} {game.away_score} - {game.home_score} LAD"

            if is_win:
                # Win message with role mention (triggers notification)
                result_text = f"Dodgers win at home! Final: {scoreline}"
                message = f"{role.mention} ||{result_text}||"
            else:
                # Loss message without role mention (no notification)
                # Padded to match win message length to prevent spoiling by length
                result_text = f"Dodgers lose at home.  Final: {scoreline}"
                message = f"||{result_text}||"

            # Send the message
            await channel.send(message)
            logger.info(
                f"Sent panda ping to #{self.channel_name}: {scoreline} "
                f"({'win' if is_win else 'loss'})"
            )

            # Mark as sent in database
            await self._mark_ping_sent(
                game.game_id,
                game.away_team,
                int(game.home_score),
                int(game.away_score),
            )

        except Exception as e:
            logger.error(f"Error sending panda ping: {e}", exc_info=True)

    @commands.group(invoke_without_command=True)
    async def panda(self, ctx: commands.Context):
        """PandaPing commands for Dodgers home win announcements.

        Usage:
          !panda status - Show monitor status
          !panda check  - Manually trigger schedule check
        """
        await ctx.send("Use `!panda status` or `!panda check`")

    @panda.command(name="status")
    @commands.has_permissions(administrator=True)
    async def panda_status(self, ctx: commands.Context):
        """Show the current status of the PandaPing monitor (admin only).

        Usage: !panda status
        """
        now = datetime.now(self.timezone)

        status_lines = ["**PandaPing Status**"]

        if self.monitoring_active:
            if self.current_game:
                status_lines.append(
                    f"🔴 Currently monitoring: {self.current_game.away_team} {self.current_game.away_score} @ {self.current_game.home_score} LAD ({self.current_game.status})"
                )
            else:
                status_lines.append("🔴 Monitoring active (no game data)")
        else:
            status_lines.append("⚪ Not currently monitoring a game")

        if self.next_game_time:
            time_until = self.next_game_time - now
            hours = int(time_until.total_seconds() // 3600)
            minutes = int((time_until.total_seconds() % 3600) // 60)
            status_lines.append(
                f"Next check scheduled: {self.next_game_time.strftime('%a %m/%d at %I:%M %p')} ({hours}h {minutes}m)"
            )
        else:
            status_lines.append("Next check: On next scheduler tick (~1 minute)")

        await ctx.message.reply("\n".join(status_lines))

    @panda.command(name="check")
    @commands.has_permissions(administrator=True)
    async def panda_check(self, ctx: commands.Context):
        """Manually trigger a schedule check (admin only).

        Usage: !panda check
        """
        try:
            # Reset state to force a fresh check
            self.next_game_time = None

            await self._check_dodgers_schedule()

            # Report back
            if self.monitoring_active:
                await ctx.send(
                    f"✅ Now monitoring Dodgers game: {self.current_game.away_team} @ LAD"
                )
            elif self.next_game_time:
                await ctx.send(
                    f"✅ Next game check scheduled for {self.next_game_time.strftime('%a %m/%d at %I:%M %p')}"
                )
            else:
                await ctx.send("✅ Check complete, no Dodgers home game found")

        except Exception as e:
            await ctx.send(f"❌ Error checking schedule: {e}")
            logger.error(f"Error in manual check: {e}", exc_info=True)


def setup(bot):
    """Setup function to add the cog."""
    bot.add_cog(PandaPingCog(bot))
