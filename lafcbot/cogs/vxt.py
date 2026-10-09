"""VxT cog for fixing social media embeds via delete + webhook repost."""

import io
import logging
import re

import discord
from discord.ext import commands

from lafcbot.clients.instagram_client import InstagramClient, InstagramPost, MediaSlide

logger = logging.getLogger(__name__)

WEBHOOK_NAME = "VxT"

INSTAGRAM_COLOR = 0xE1306C

# Keep the caption short, closer to a social-card summary than a full post.
MAX_CAPTION_LENGTH = 300

# kkinstagram can't render a rich card or multi-image/video carousels (its
# /p/ route just 302s to a single representative image), so instead we scrape
# the post ourselves and build the card directly - capped at Discord's
# 10-attachments-per-message limit for any extra carousel slides.
MAX_CAROUSEL_SLIDES = 10

DOMAIN_MAP = {
    "twitter.com": "fxtwitter.com",
    "x.com": "fxtwitter.com",
    "instagram.com": "kkinstagram.com",
    "tiktok.com": "tnktok.com",
}

# Matches /p/{shortcode} and /reel/{shortcode}, with or without a leading
# /{username}/ segment. Instagram's embed endpoint treats both the same way,
# keyed only on the shortcode.
INSTAGRAM_POST_PATH = re.compile(r"^/(?:[^/?#]+/)?(?:p|reels?)/([A-Za-z0-9_-]+)")


class VxTCog(commands.Cog):
    """Cog for detecting social media links, deleting the message, and
    reposting it via a webhook with the embed-fixing domain substituted in.
    """

    def __init__(self, bot):
        self.bot = bot
        self._webhook_cache: dict[int, discord.Webhook] = {}
        self.instagram_client = InstagramClient()

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

    async def _replace_domain(
        self, match: re.Match, enabled_domains: set[str]
    ) -> tuple[str, list[discord.File], list[discord.Embed]]:
        """Rebuild a matched URL with its embed-fixing domain substituted in,
        leaving the URL untouched if its domain isn't enabled for this guild.

        For Instagram, scrapes the post ourselves and returns a rich embed
        plus any extra files to attach (kkinstagram can only show a single
        plain image/video, with no caption/stats). Falls back to the plain
        kkinstagram link if the post couldn't be scraped.
        """
        domain = match.group(1).lower()
        if domain not in enabled_domains:
            return match.group(0), [], []
        rest = match.group(2) or ""

        if domain == "instagram.com":
            post_match = INSTAGRAM_POST_PATH.match(rest)
            if not post_match:
                # Not a /p/ or /reel/ link (e.g. a profile page) - nothing
                # for us to fix, so leave it untouched.
                return match.group(0), [], []

            post = await self.instagram_client.get_post(post_match.group(1))
            if post:
                shown_slides = post.slides[:MAX_CAROUSEL_SLIDES]
                files = await self._carousel_files(shown_slides)

                # Angle-bracket the link so Discord doesn't also generate
                # its own preview from the raw URL - we already provide
                # richer content below.
                link = f"<{match.group(0)}>"
                if len(post.slides) > MAX_CAROUSEL_SLIDES:
                    link += f" (showing {len(shown_slides)}/{len(post.slides)} slides)"

                if shown_slides[0].is_video:
                    # The attached video already renders as its own
                    # native player; an embed on top could only show a
                    # static thumbnail, which would just duplicate it.
                    # Put the caption/stats as plain text instead.
                    text = self._format_caption_text(link, post)
                    return text, files, []

                embed = self._build_embed(post)
                return link, files, [embed]

        return f"https://{DOMAIN_MAP[domain]}{rest}", [], []

    async def _carousel_files(
        self, shown_slides: list[MediaSlide]
    ) -> list[discord.File]:
        """Download the files needed alongside the embed card: the first
        slide's video (if it's a video - the embed can only show a static
        thumbnail for it), plus any remaining carousel slides.
        """
        files = []

        first = shown_slides[0]
        if first.is_video:
            data = await self.instagram_client.download(first.url)
            if data is not None:
                files.append(discord.File(io.BytesIO(data), filename="slide_1.mp4"))

        for i, slide in enumerate(shown_slides[1:], start=2):
            data = await self.instagram_client.download(slide.url)
            if data is None:
                continue
            ext = "mp4" if slide.is_video else "jpg"
            files.append(discord.File(io.BytesIO(data), filename=f"slide_{i}.{ext}"))

        return files

    @staticmethod
    def _truncate_caption(caption: str | None) -> str | None:
        if not caption:
            return None
        caption = caption.strip()
        if len(caption) > MAX_CAPTION_LENGTH:
            caption = caption[:MAX_CAPTION_LENGTH].rstrip() + "…"
        return caption

    @staticmethod
    def _build_embed(post: InstagramPost) -> discord.Embed:
        """Build an fxtwitter-style card: author, caption, likes/comments
        footer, and the first slide's image (hotlinked, not re-uploaded).
        """
        embed = discord.Embed(
            description=VxTCog._truncate_caption(post.caption), color=INSTAGRAM_COLOR
        )

        if post.username:
            embed.set_author(
                name=f"@{post.username}",
                icon_url=post.avatar_url,
                url=f"https://www.instagram.com/{post.username}/",
            )

        stats = []
        if post.like_count is not None:
            stats.append(f"❤️ {post.like_count:,}")
        if post.comment_count is not None:
            stats.append(f"💬 {post.comment_count:,}")
        embed.set_footer(text="  ".join(stats) if stats else "Instagram")

        if post.slides:
            embed.set_image(url=post.slides[0].thumbnail_url)

        return embed

    @staticmethod
    def _format_caption_text(link: str, post: InstagramPost) -> str:
        """Format author/caption/stats as plain text, for posts whose video
        attachment already needs its own native player (no embed on top).
        """
        lines = [link]

        stats = []
        if post.username:
            stats.append(f"**@{post.username}**")
        if post.like_count is not None:
            stats.append(f"❤️ {post.like_count:,}")
        if post.comment_count is not None:
            stats.append(f"💬 {post.comment_count:,}")
        if stats:
            lines.append(" · ".join(stats))

        caption = VxTCog._truncate_caption(post.caption)
        if caption:
            lines.append(caption)

        return "\n".join(lines)

    async def _process_content(
        self, content: str, enabled_domains: set[str]
    ) -> tuple[str, list[discord.File], list[discord.Embed]]:
        """Rewrite all matched links in a message's content, awaiting the
        per-match domain replacement (which may need to hit the network),
        and collect any extra files/embeds (e.g. an Instagram post's slides
        and card).
        """
        pieces = []
        extra_files = []
        embeds = []
        last_end = 0
        for match in self.url_pattern.finditer(content):
            pieces.append(content[last_end : match.start()])
            replacement, files, match_embeds = await self._replace_domain(
                match, enabled_domains
            )
            pieces.append(replacement)
            extra_files.extend(files)
            embeds.extend(match_embeds)
            last_end = match.end()
        pieces.append(content[last_end:])
        return "".join(pieces), extra_files, embeds

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

        if not self.url_pattern.search(message.content):
            return

        enabled_domains = self._enabled_domains(guild_id)
        new_content, extra_files, embeds = await self._process_content(
            message.content, enabled_domains
        )
        if new_content == message.content and not extra_files and not embeds:
            return

        try:
            files = [await a.to_file() for a in message.attachments] + extra_files

            webhook = await self._get_webhook(message.channel)
            send_kwargs = {
                "content": new_content,
                "username": message.author.display_name,
                "avatar_url": message.author.display_avatar.url,
                "files": files,
                "embeds": embeds,
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
