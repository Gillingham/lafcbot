"""PandaPing cog for announcing Dodgers home wins."""

import asyncio
import logging
from datetime import datetime, time, timedelta

import aiosqlite
import discord
from discord.ext import commands, tasks

from lafcbot.clients.espn_client import ESPNClient
from lafcbot.utils.config import get_db_path, load_timezone

logger = logging.getLogger(__name__)


class PandaPingCog(commands.Cog):
    """Cog for announcing Dodgers home wins to #other-sports."""

    def __init__(self, bot):
        self.bot = bot
        self.espn_client = ESPNClient()
        self.timezone = load_timezone()

        # Load per-server configuration
        from lafcbot.utils.config import load_config

        config = load_config()
        self.pandaping_config = config.get("pandaping", {})
        self.server_configs = self.pandaping_config.get("servers", [])

        # Log configuration on startup
        if self.server_configs:
            logger.info(
                f"PandaPing configured for {len(self.server_configs)} server(s)"
            )
        else:
            logger.warning(
                "PandaPing has no servers configured - announcements will not be sent"
            )

        # Initialize formatter
        from lafcbot.formatters.sports import SportsFormatter

        self.formatter = SportsFormatter(self.timezone)

        # State tracking
        self.current_game = None
        self.next_game_time = None
        self.monitoring_active = False

        # Database path for persistent state
        self.db_path = get_db_path()

        # Start the main scheduler
        self.scheduler.start()

        # Start the daily reminder task
        self.daily_panda_reminder.start()

    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.scheduler.cancel()
        if self.game_monitor.is_running():
            self.game_monitor.cancel()
        if self.daily_panda_reminder.is_running():
            self.daily_panda_reminder.cancel()

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
        """Initialize the database table for tracking sent panda pings with migration support."""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if old table exists
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='panda_pings'"
            )
            table_exists = await cursor.fetchone()

            if table_exists:
                # Check if guild_id column exists
                cursor = await db.execute("PRAGMA table_info(panda_pings)")
                columns = await cursor.fetchall()
                has_guild_id = any(col[1] == "guild_id" for col in columns)

                if not has_guild_id:
                    # Migration needed: drop old table (safe since it's just tracking sent pings)
                    logger.info(
                        "Migrating panda_pings table to include guild_id column"
                    )
                    await db.execute("DROP TABLE panda_pings")

            # Create table with new schema (guild-scoped)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS panda_pings (
                    game_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    home_score INTEGER NOT NULL,
                    away_score INTEGER NOT NULL,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (game_id, guild_id)
                )
                """
            )
            await db.commit()

    async def _has_ping_been_sent(self, game_id: str, guild_id: str) -> bool:
        """Check if a panda ping has already been sent for this game in this guild."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM panda_pings WHERE game_id = ? AND guild_id = ?",
                (game_id, guild_id),
            )
            result = await cursor.fetchone()
            return result is not None

    async def _mark_ping_sent(
        self,
        game_id: str,
        guild_id: str,
        away_team: str,
        home_score: int,
        away_score: int,
    ):
        """Record that a panda ping has been sent for this game in this guild."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO panda_pings (game_id, guild_id, away_team, home_score, away_score)
                VALUES (?, ?, ?, ?, ?)
                """,
                (game_id, guild_id, away_team, home_score, away_score),
            )
            await db.commit()

    async def _check_last_game_was_win(self, guild_id: str) -> bool:
        """Check if the most recent game for this guild was a Dodgers win.

        Args:
            guild_id: Guild ID to check

        Returns:
            True if the most recent game was a win, False otherwise (loss or no games)
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT home_score, away_score
                FROM panda_pings
                WHERE guild_id = ?
                ORDER BY sent_at DESC
                LIMIT 1
                """,
                (guild_id,),
            )
            result = await cursor.fetchone()

            if not result:
                # No games recorded yet
                logger.debug(f"Guild {guild_id}: No games recorded in database")
                return False

            home_score, away_score = result
            is_win = home_score > away_score
            logger.debug(
                f"Guild {guild_id}: Last game was {home_score}-{away_score} ({'win' if is_win else 'loss'})"
            )
            return is_win

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

    @tasks.loop(hours=24)
    async def daily_panda_reminder(self):
        """Send daily Panda deal reminder to all configured servers (only after wins)."""
        if not self.server_configs:
            logger.debug("No servers configured for PandaPing, skipping daily reminder")
            return

        for server_config in self.server_configs:
            try:
                # Check if daily reminder is enabled for this server
                if not server_config.get("daily_reminder", True):
                    logger.debug(
                        f"Guild {server_config.get('guild_id')} has daily_reminder=false, skipping"
                    )
                    continue

                guild_id = server_config.get("guild_id")
                if not guild_id:
                    logger.warning(
                        "Server config missing guild_id for daily reminder, skipping"
                    )
                    continue

                # Check if the most recent game was a win
                last_game_was_win = await self._check_last_game_was_win(guild_id)
                if not last_game_was_win:
                    logger.debug(
                        f"Guild {guild_id}: Last game was not a win, skipping daily reminder"
                    )
                    continue

                channel_name = server_config.get("channel_name", "other-sports")
                role_name = server_config.get("role_name", "Panda Ping")

                # Find guild
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    logger.warning(
                        f"Guild {guild_id} not found for daily reminder (bot not in this server?)"
                    )
                    continue

                # Find channel in that guild
                channel = discord.utils.get(guild.text_channels, name=channel_name)
                if not channel:
                    logger.error(
                        f"Channel #{channel_name} not found in guild {guild.name} ({guild_id}) for daily reminder"
                    )
                    continue

                # Find role in that guild
                role = discord.utils.get(guild.roles, name=role_name)
                if not role:
                    logger.error(
                        f"Role '{role_name}' not found in guild {guild.name} ({guild_id}) for daily reminder"
                    )
                    continue

                # Send spoiler-tagged reminder
                message = f"{role.mention} ||Daily reminder: Panda Express deal for Dodgers home wins!||"
                await channel.send(message)
                logger.info(
                    f"Sent daily panda reminder to #{channel_name} in {guild.name} (last game was a win)"
                )

            except Exception as e:
                logger.error(
                    f"Error sending daily reminder to guild {server_config.get('guild_id')}: {e}",
                    exc_info=True,
                )

    @daily_panda_reminder.before_loop
    async def before_daily_reminder(self):
        """Wait until bot is ready and schedule for 10am."""
        await self.bot.wait_until_ready()

        # Calculate time until 10am today or tomorrow
        now = datetime.now(self.timezone)
        target = datetime.combine(
            now.date(), time(hour=10, minute=0), tzinfo=self.timezone
        )

        # If we've passed 10am today, schedule for tomorrow
        if now >= target:
            target = target + timedelta(days=1)

        # Calculate seconds to wait
        wait_seconds = (target - now).total_seconds()

        logger.info(
            f"Daily panda reminder will start at {target.strftime('%Y-%m-%d %I:%M %p %Z')}"
        )
        await asyncio.sleep(wait_seconds)

    async def _send_panda_ping(self, game, is_win: bool):
        """Send panda ping to all configured servers.

        Args:
            game: Game object with score information
            is_win: True if Dodgers won, False if they lost
        """
        if not self.server_configs:
            logger.debug("No servers configured for PandaPing, skipping announcements")
            return

        for server_config in self.server_configs:
            try:
                guild_id = server_config.get("guild_id")
                if not guild_id:
                    logger.warning("Server config missing guild_id, skipping")
                    continue

                # Check server preferences for wins/losses
                if is_win and not server_config.get("announce_wins", True):
                    logger.debug(
                        f"Guild {guild_id} has announce_wins=false, skipping win announcement"
                    )
                    continue
                if not is_win and not server_config.get("announce_losses", True):
                    logger.debug(
                        f"Guild {guild_id} has announce_losses=false, skipping loss announcement"
                    )
                    continue

                # Check if already sent to this guild
                if await self._has_ping_been_sent(game.game_id, guild_id):
                    logger.info(
                        f"Panda ping already sent for game {game.game_id} to guild {guild_id}, skipping"
                    )
                    continue

                # Send to this guild
                await self._send_to_guild(game, is_win, server_config)

            except Exception as e:
                logger.error(
                    f"Error sending panda ping to guild {server_config.get('guild_id')}: {e}",
                    exc_info=True,
                )

    async def _send_to_guild(self, game, is_win: bool, server_config: dict):
        """Send panda ping to a specific guild.

        Args:
            game: Game object with score information
            is_win: True if Dodgers won, False if they lost
            server_config: Server configuration dictionary
        """
        guild_id = server_config["guild_id"]
        channel_name = server_config.get("channel_name", "other-sports")
        role_name = server_config.get("role_name", "Panda Ping")

        # Find guild
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            logger.warning(f"Guild {guild_id} not found (bot not in this server?)")
            return

        # Find channel in that guild
        channel = discord.utils.get(guild.text_channels, name=channel_name)
        if not channel:
            logger.error(
                f"Channel #{channel_name} not found in guild {guild.name} ({guild_id})"
            )
            return

        # Find role in that guild
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            logger.error(
                f"Role '{role_name}' not found in guild {guild.name} ({guild_id})"
            )
            return

        # Use formatter to build result text
        result_text = self.formatter.format_dodgers_game_result(
            opponent=game.away_team,
            dodgers_score=int(game.home_score),
            opponent_score=int(game.away_score),
            is_win=is_win,
            is_home=True,
        )

        # Add "Final: " prefix to match original format
        result_text = f"{result_text} - Final"

        if is_win:
            # Win message with role mention (triggers notification)
            message = f"{role.mention} ||{result_text}||"
        else:
            # Loss message without role mention (no notification)
            message = f"||{result_text}||"

        # Send the message
        await channel.send(message)
        logger.info(
            f"Sent panda ping to #{channel_name} in {guild.name}: {game.away_team} {game.away_score} - {game.home_score} LAD "
            f"({'win' if is_win else 'loss'})"
        )

        # Mark as sent in database for this guild
        await self._mark_ping_sent(
            game.game_id,
            guild_id,
            game.away_team,
            int(game.home_score),
            int(game.away_score),
        )

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
