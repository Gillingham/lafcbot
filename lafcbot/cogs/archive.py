"""Archive cog for linking archive.ph copies of recently shared links."""

import logging
import re

import discord
from discord.ext import commands

from lafcbot.clients.archive_client import ArchiveClient

logger = logging.getLogger(__name__)

ARCHIVE_COLOR = 0x6D6D6D

URL_PATTERN = re.compile(r"https?://\S+")

HISTORY_SEARCH_LIMIT = 50

# Discord enforces a 256-character maximum on embed titles.
EMBED_TITLE_MAX = 256


class ArchiveCog(commands.Cog):
    """Cog for archiving the most recently linked page in a channel via archive.ph."""

    def __init__(self, bot):
        self.bot = bot
        self.archive_client = ArchiveClient()

    async def _find_last_link(self, channel, before: discord.Message) -> str | None:
        """Search backward from `before` for the most recent message containing a URL."""
        async for message in channel.history(limit=HISTORY_SEARCH_LIMIT, before=before):
            match = URL_PATTERN.search(message.content)
            if match:
                return match.group(0)
        return None

    @staticmethod
    def _truncate_title(title: str) -> str:
        """Truncate a string to Discord's embed title limit, adding an ellipsis if needed."""
        if len(title) <= EMBED_TITLE_MAX:
            return title
        return title[: EMBED_TITLE_MAX - 1] + "…"

    @commands.command()
    async def archive(self, ctx: commands.Context, *, link: str | None = None):
        """Archive a link via archive.ph - either given directly, or the most
        recently linked page in this channel if none is given.

        Usage:
          !archive
          !archive <link>
        """
        if link is not None:
            match = URL_PATTERN.search(link)
            url = match.group(0) if match else None
            if url is None:
                await ctx.send("That doesn't look like a link.")
                return
        else:
            url = await self._find_last_link(ctx.channel, before=ctx.message)
            if url is None:
                await ctx.send("No recent link found to archive.")
                return

        archive_url = await self.archive_client.get_archive_url(url)
        metadata = await self.archive_client.get_page_metadata(url)

        raw_title = (metadata.title if metadata else None) or url
        embed = discord.Embed(
            title=self._truncate_title(raw_title),
            url=archive_url,
            description=metadata.description if metadata else None,
            color=ARCHIVE_COLOR,
        )
        if metadata and metadata.site_name:
            embed.set_author(name=metadata.site_name)
        if metadata and metadata.image_url:
            embed.set_image(url=metadata.image_url)
        embed.set_footer(text="archive.is")

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            logger.warning(
                f"Missing permissions to delete message in channel {ctx.channel.id}"
            )

        await ctx.send(embed=embed)


def setup(bot):
    """Setup function to add the cog."""
    bot.add_cog(ArchiveCog(bot))
