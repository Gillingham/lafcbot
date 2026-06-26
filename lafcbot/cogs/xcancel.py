"""XCancel cog for replacing x.com links with xcancel.com alternatives."""

import logging
import re

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class XCancelCog(commands.Cog):
    """Cog for detecting x.com links and replying with xcancel.com alternatives."""

    def __init__(self, bot):
        self.bot = bot

        # Load per-server configuration
        from lafcbot.utils.config import load_config

        config = load_config()
        self.xcancel_config = config.get("xcancel", {})
        self.enabled_guilds = set(self.xcancel_config.get("enabled_guilds", []))

        # Log configuration on startup
        if self.enabled_guilds:
            logger.info(
                f"XCancel configured for {len(self.enabled_guilds)} server(s): {self.enabled_guilds}"
            )
        else:
            logger.warning(
                "XCancel has no servers configured - link replacement will not be active"
            )

        # Regex pattern to match x.com and twitter.com URLs
        # Matches: x.com/user/status/123, twitter.com/user/status/123, etc.
        self.url_pattern = re.compile(
            r"https?://(?:www\.)?(x\.com|twitter\.com)/([^\s]+)",
            re.IGNORECASE,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages containing x.com or twitter.com links.

        Args:
            message: Discord message object
        """
        # Ignore bot messages
        if message.author.bot:
            return

        # Check if this guild has XCancel enabled
        if message.guild and str(message.guild.id) not in self.enabled_guilds:
            return

        # Check if message contains x.com or twitter.com links
        matches = self.url_pattern.findall(message.content)
        if not matches:
            return

        try:
            # Add red card emoji reaction
            await message.add_reaction("🟥")

            # Build xcancel.com replacements
            xcancel_links = []
            for _domain, path in matches:
                xcancel_url = f"https://xcancel.com/{path}"
                xcancel_links.append(xcancel_url)

            # Reply with xcancel.com links
            if len(xcancel_links) == 1:
                reply_text = f"xcancel.com version: {xcancel_links[0]}"
            else:
                # Multiple links - format as numbered list
                formatted_links = "\n".join(
                    f"{i + 1}. {link}" for i, link in enumerate(xcancel_links)
                )
                reply_text = f"xcancel.com versions:\n{formatted_links}"

            await message.reply(reply_text, mention_author=False)

            logger.info(
                f"Replaced {len(xcancel_links)} x.com/twitter.com link(s) in guild {message.guild.id if message.guild else 'DM'}"
            )

        except discord.Forbidden:
            logger.warning(
                f"Missing permissions to react/reply in channel {message.channel.id}"
            )
        except Exception as e:
            logger.error(f"Error processing x.com link: {e}", exc_info=True)

    @commands.group(invoke_without_command=True)
    async def xcancel(self, ctx: commands.Context):
        """XCancel commands for managing x.com link replacement.

        Usage:
          !xcancel status - Show if XCancel is enabled in this server
        """
        await ctx.send("Use `!xcancel status` to check if XCancel is enabled")

    @xcancel.command(name="status")
    async def xcancel_status(self, ctx: commands.Context):
        """Show if XCancel is enabled in this server.

        Usage: !xcancel status
        """
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        guild_id = str(ctx.guild.id)
        is_enabled = guild_id in self.enabled_guilds

        if is_enabled:
            await ctx.message.reply(
                f"✅ XCancel is **enabled** in {ctx.guild.name}\n"
                f"x.com and twitter.com links will be automatically replaced with xcancel.com versions."
            )
        else:
            await ctx.message.reply(
                f"⚪ XCancel is **disabled** in {ctx.guild.name}\n"
                f"To enable, add this server's guild ID ({guild_id}) to the `xcancel.enabled_guilds` list in config.json"
            )


def setup(bot):
    """Setup function to add the cog."""
    bot.add_cog(XCancelCog(bot))
