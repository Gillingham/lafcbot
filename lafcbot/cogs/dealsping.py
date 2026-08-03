"""DealsPing cog for announcing LA sports deals from lahomewin.com."""

import asyncio
import logging
from datetime import datetime, time, timedelta

import aiosqlite
import discord
from discord.ext import commands, tasks

from lafcbot.clients.lahomewin_client import LaHomeWinClient
from lafcbot.formatters.deals import DealsFormatter
from lafcbot.utils.config import get_db_path, load_timezone

logger = logging.getLogger(__name__)


class DealsPingCog(commands.Cog):
    """Cog for announcing LA sports deals from lahomewin.com."""

    def __init__(self, bot):
        self.bot = bot
        self.lahomewin_client = LaHomeWinClient()
        self.timezone = load_timezone()

        # Load per-server configuration
        from lafcbot.utils.config import load_config

        config = load_config()
        self.dealsping_config = config.get("dealsping", {})
        self.enabled = self.dealsping_config.get("enabled", True)
        self.scrape_time_hour = self.dealsping_config.get("scrape_time_hour", 8)
        self.server_configs = self.dealsping_config.get("servers", [])

        # Log configuration on startup
        if not self.enabled:
            logger.info("DealsPing is disabled in config")
            return

        if self.server_configs:
            logger.info(
                f"DealsPing configured for {len(self.server_configs)} server(s)"
            )
        else:
            logger.warning(
                "DealsPing has no servers configured - announcements will not be sent"
            )

        # Initialize formatter
        self.formatter = DealsFormatter(self.timezone)

        # Database path for persistent state
        self.db_path = get_db_path()

        # Start the daily scraper
        if self.enabled:
            self.daily_deals_scraper.start()

    def cog_unload(self):
        """Clean up when cog is unloaded."""
        if self.daily_deals_scraper.is_running():
            self.daily_deals_scraper.cancel()

    @tasks.loop(hours=24)
    async def daily_deals_scraper(self):
        """Scrape lahomewin.com daily for active deals."""
        try:
            logger.info("Starting daily deals scraper")

            # Scrape website
            deals = await self.lahomewin_client.get_all_deals()

            if not deals:
                logger.warning("No deals found from lahomewin.com")
                return

            # Filter to only "Active Today" deals
            active_deals = [d for d in deals if d.status == "active"]
            logger.info(
                f"Found {len(active_deals)} active deals out of {len(deals)} total"
            )

            # Send notifications for each active deal
            for deal in active_deals:
                await self._send_deal_notification(deal)

        except Exception as e:
            logger.error(f"Error in daily scraper: {e}", exc_info=True)

    @daily_deals_scraper.before_loop
    async def before_scraper(self):
        """Wait until bot is ready and schedule for configured time."""
        await self.bot.wait_until_ready()
        await self._init_database()

        # Calculate time until scrape_time_hour today or tomorrow
        now = datetime.now(self.timezone)
        target = datetime.combine(
            now.date(), time(hour=self.scrape_time_hour, minute=0), tzinfo=self.timezone
        )

        # If we've passed the scrape time today, schedule for tomorrow
        if now >= target:
            target = target + timedelta(days=1)

        # Calculate seconds to wait
        wait_seconds = (target - now).total_seconds()

        logger.info(
            f"Daily deals scraper will start at {target.strftime('%Y-%m-%d %I:%M %p %Z')}"
        )
        await asyncio.sleep(wait_seconds)

    async def _init_database(self):
        """Initialize the database table for tracking sent deals."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS deals_pings (
                    deal_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (deal_id, guild_id, DATE(sent_at))
                )
                """
            )
            await db.commit()
            logger.info("Deals database table initialized")

    async def _has_ping_been_sent_today(self, deal_id: str, guild_id: str) -> bool:
        """Check if a deal notification has already been sent to this guild today.

        Args:
            deal_id: The deal ID
            guild_id: The guild ID

        Returns:
            True if notification was already sent today
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT 1 FROM deals_pings
                WHERE deal_id = ? AND guild_id = ? AND DATE(sent_at) = DATE('now')
                """,
                (deal_id, guild_id),
            )
            result = await cursor.fetchone()
            return result is not None

    async def _mark_ping_sent(self, deal_id: str, guild_id: str):
        """Record that a deal notification was sent.

        Args:
            deal_id: The deal ID
            guild_id: The guild ID
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO deals_pings (deal_id, guild_id) VALUES (?, ?)",
                (deal_id, guild_id),
            )
            await db.commit()

    async def _send_deal_notification(self, deal):
        """Send notification for an active deal to all configured guilds.

        Args:
            deal: The Deal object to notify about
        """
        for server_config in self.server_configs:
            try:
                guild_id = server_config.get("guild_id")
                if not guild_id:
                    logger.warning("Server config missing guild_id, skipping")
                    continue

                # Check if already sent today
                if await self._has_ping_been_sent_today(deal.deal_id, guild_id):
                    logger.debug(
                        f"Already sent {deal.deal_id} to guild {guild_id} today"
                    )
                    continue

                # Look up routing - ONLY configured deals, no default fallback
                deal_routes = server_config.get("deal_routes", {})
                route = deal_routes.get(deal.deal_id)

                if not route:
                    logger.debug(
                        f"Deal {deal.deal_id} not configured for guild {guild_id}, skipping"
                    )
                    continue

                # Send to Discord
                await self._send_to_guild(deal, route, guild_id)

            except Exception as e:
                logger.error(
                    f"Error sending deal notification to guild {server_config.get('guild_id')}: {e}",
                    exc_info=True,
                )

    async def _send_to_guild(self, deal, route: dict, guild_id: str):
        """Send deal notification to a specific guild.

        Args:
            deal: The Deal object
            route: Routing config (channel_name, role_name)
            guild_id: Guild ID
        """
        channel_name = route.get("channel_name")
        role_name = route.get("role_name")

        if not channel_name:
            logger.warning(f"No channel_name in route for {deal.deal_id}")
            return

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

        # Format the deal message
        message_content = self.formatter.format_deal_activation(deal)

        # Add role mention if configured
        if role_name:
            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                message_content = f"{role.mention}\n{message_content}"
            else:
                logger.warning(
                    f"Role '{role_name}' not found in guild {guild.name} ({guild_id})"
                )

        # Send the message
        await channel.send(message_content)
        logger.info(
            f"Sent deal notification to #{channel_name} in {guild.name}: {deal.deal_id}"
        )

        # Mark as sent in database
        await self._mark_ping_sent(deal.deal_id, guild_id)

    @commands.group(invoke_without_command=True)
    async def deals(self, ctx: commands.Context):
        """Show today's active deals with redemption instructions.

        Usage:
          !deals - Show active deals
          !deals list - List all available deals
          !deals check - [Admin] Manually trigger deal check
        """
        try:
            # Fetch all deals
            deals = await self.lahomewin_client.get_all_deals()

            if not deals:
                await ctx.send("No deals found on lahomewin.com")
                return

            # Filter to only active deals
            active_deals = [d for d in deals if d.status == "active"]

            if not active_deals:
                await ctx.send("No deals are active today")
                return

            # Format active deals with redemption info
            message = self.formatter.format_active_deals_with_redemption(active_deals)
            await ctx.send(message)

        except Exception as e:
            logger.error(f"Error in !deals: {e}", exc_info=True)
            await ctx.send(f"Error fetching deals: {e}")

    @deals.command(name="list")
    async def deals_list(self, ctx: commands.Context):
        """List all available deals from lahomewin.com.

        Usage: !deals list
        """
        try:
            deals = await self.lahomewin_client.get_all_deals()

            if not deals:
                await ctx.send("No deals found on lahomewin.com")
                return

            # Format the deals list
            message = self.formatter.format_deal_list(deals)
            await ctx.send(message)

        except Exception as e:
            logger.error(f"Error in !deals list: {e}", exc_info=True)
            await ctx.send(f"Error fetching deals: {e}")

    @deals.command(name="check")
    @commands.has_permissions(administrator=True)
    async def deals_check(self, ctx: commands.Context):
        """Manually trigger a deal check (admin only).

        Usage: !deals check
        """
        try:
            await ctx.send("Checking for active deals...")

            # Run the scraper manually
            deals = await self.lahomewin_client.get_all_deals()

            if not deals:
                await ctx.send("No deals found")
                return

            active_deals = [d for d in deals if d.status == "active"]

            if not active_deals:
                await ctx.send(
                    f"Found {len(deals)} total deals, but none are active today"
                )
                return

            # Send notifications
            for deal in active_deals:
                await self._send_deal_notification(deal)

            await ctx.send(
                f"Deal check complete! Found {len(active_deals)} active deal(s)"
            )

        except Exception as e:
            logger.error(f"Error in !deals check: {e}", exc_info=True)
            await ctx.send(f"Error checking deals: {e}")


def setup(bot):
    """Setup function to add the cog."""
    bot.add_cog(DealsPingCog(bot))
