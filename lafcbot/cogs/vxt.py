"""VxT cog for fixing social media embeds via delete + webhook repost."""

import logging
import re

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

WEBHOOK_NAME = "VxT"

DOMAIN_MAP = {
    "twitter.com": "fxtwitter.com",
    "x.com": "fxtwitter.com",
    "instagram.com": "ddinstagram.com",
    "tiktok.com": "tiktxk.com",
}


class VxTCog(commands.Cog):
    """Cog for detecting social media links, deleting the message, and
    reposting it via a webhook with the embed-fixing domain substituted in.
    """

    def __init__(self, bot):
        self.bot = bot
        self._webhook_cache: dict[int, discord.Webhook] = {}

        # Load per-server configuration
        from lafcbot.utils.config import load_config

        config = load_config()
        self.vxt_config = config.get("vxt", {})
        self.server_settings = {
            server["guild_id"]: server for server in self.vxt_config.get("servers", [])
        }

        # Log configuration on startup
        if self.server_settings:
            logger.info(
                f"VxT configured for {len(self.server_settings)} server(s): {set(self.server_settings)}"
            )
        else:
            logger.warning(
                "VxT has no servers configured - link fixing will not be active"
            )

        self.url_pattern = re.compile(
            r"https?://(?:www\.)?(twitter\.com|x\.com|instagram\.com|tiktok\.com)(/\S*)?",
            re.IGNORECASE,
        )

    def _enabled_domains(self, guild_id: str) -> set[str]:
        """Determine which link domains should be fixed for a given guild."""
        domains = {"twitter.com", "x.com"}
        server_settings = self.server_settings.get(guild_id, {})
        if server_settings.get("instagram_enabled"):
            domains.add("instagram.com")
        if server_settings.get("tiktok_enabled"):
            domains.add("tiktok.com")
        return domains

    def _replace_domain(self, match: re.Match, enabled_domains: set[str]) -> str:
        """Rebuild a matched URL with its embed-fixing domain substituted in,
        leaving the URL untouched if its domain isn't enabled for this guild.
        """
        domain = match.group(1).lower()
        if domain not in enabled_domains:
            return match.group(0)
        rest = match.group(2) or ""
        return f"https://{DOMAIN_MAP[domain]}{rest}"

    async def _get_webhook(self, channel) -> discord.Webhook:
        """Get or create the VxT webhook for a channel, caching the result."""
        if channel.id in self._webhook_cache:
            return self._webhook_cache[channel.id]

        target = channel.parent if isinstance(channel, discord.Thread) else channel
        webhooks = await target.webhooks()
        webhook = next(
            (w for w in webhooks if w.name == WEBHOOK_NAME and w.user == self.bot.user),
            None,
        )
        if webhook is None:
            webhook = await target.create_webhook(
                name=WEBHOOK_NAME, reason="VxT link fixing"
            )

        self._webhook_cache[channel.id] = webhook
        return webhook

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages containing social media links, delete them,
        and repost via webhook with embed-fixing domains substituted in.

        Args:
            message: Discord message object
        """
        if message.author.bot or message.webhook_id is not None:
            return

        if not message.guild:
            return

        guild_id = str(message.guild.id)
        if guild_id not in self.server_settings:
            return

        enabled_domains = self._enabled_domains(guild_id)
        new_content = self.url_pattern.sub(
            lambda m: self._replace_domain(m, enabled_domains), message.content
        )
        if new_content == message.content:
            return

        try:
            files = [await a.to_file() for a in message.attachments]

            webhook = await self._get_webhook(message.channel)
            send_kwargs = {
                "content": new_content,
                "username": message.author.display_name,
                "avatar_url": message.author.display_avatar.url,
                "files": files,
            }
            if isinstance(message.channel, discord.Thread):
                send_kwargs["thread"] = message.channel

            await webhook.send(**send_kwargs)
            await message.delete()

            logger.debug(
                f"Fixed link(s) and reposted message in guild {message.guild.id}"
            )

        except discord.Forbidden:
            logger.warning(
                f"Missing permissions (Manage Messages/Manage Webhooks) in channel {message.channel.id}"
            )
        except discord.HTTPException as e:
            logger.error(f"Error reposting VxT message: {e}", exc_info=True)

    @commands.group(invoke_without_command=True)
    async def vxt(self, ctx: commands.Context):
        """VxT commands for managing social media embed fixing.

        Usage:
          !vxt status - Show if VxT is enabled in this server
        """
        await ctx.send("Use `!vxt status` to check if VxT is enabled")

    @vxt.command(name="status")
    async def vxt_status(self, ctx: commands.Context):
        """Show if VxT is enabled in this server.

        Usage: !vxt status
        """
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        guild_id = str(ctx.guild.id)
        server_settings = self.server_settings.get(guild_id)
        is_enabled = server_settings is not None

        if is_enabled:
            instagram_status = (
                "enabled" if server_settings.get("instagram_enabled") else "disabled"
            )
            tiktok_status = (
                "enabled" if server_settings.get("tiktok_enabled") else "disabled"
            )
            await ctx.message.reply(
                f"✅ VxT is **enabled** in {ctx.guild.name}\n"
                f"Twitter/X links will be automatically fixed.\n"
                f"Instagram: **{instagram_status}**, TikTok: **{tiktok_status}** "
                f"(toggle via `vxt.servers[].instagram_enabled`/`tiktok_enabled` in config.json)"
            )
        else:
            await ctx.message.reply(
                f"⚪ VxT is **disabled** in {ctx.guild.name}\n"
                f"To enable, add this server's guild ID ({guild_id}) to the `vxt.servers` list in config.json"
            )


def setup(bot):
    """Setup function to add the cog."""
    bot.add_cog(VxTCog(bot))
