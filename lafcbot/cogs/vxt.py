"""VxT cog for fixing social media embeds via delete + webhook repost."""

import io
import logging
import re

import discord
from discord.ext import commands

from lafcbot.clients.instagram_client import InstagramClient, InstagramPost, MediaSlide
from lafcbot.utils.video import process_video
from lafcbot.utils.video_cache import VideoCache

logger = logging.getLogger(__name__)

WEBHOOK_NAME = "VxT"

INSTAGRAM_COLOR = 0xE1306C

# Keep the caption short, closer to a social-card summary than a full post.
MAX_CAPTION_LENGTH = 300

# Instagram posts are scraped directly via Instagram's embed endpoint so we
# can build a rich card with caption/stats and full carousel support - capped
# at Discord's 10-attachments-per-message limit for extra carousel slides.
MAX_CAROUSEL_SLIDES = 10

# Maximum raw video size to download before attempting compression/clipping (100 MB).
MAX_RAW_VIDEO_DOWNLOAD_SIZE = 100 * 1024 * 1024

DOMAIN_MAP = {
    "twitter.com": "fxtwitter.com",
    "x.com": "fxtwitter.com",
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

    def __init__(self, bot, video_cache: VideoCache | None = None):
        self.bot = bot
        self._webhook_cache: dict[int, discord.Webhook] = {}
        self.instagram_client = InstagramClient()
        self.video_cache = video_cache or VideoCache()

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
        self, match: re.Match, enabled_domains: set[str], filesize_limit: int
    ) -> tuple[str, list[discord.File], list[discord.Embed], str]:
        """Rebuild a matched URL with its embed-fixing domain substituted in,
        leaving the URL untouched if its domain isn't enabled for this guild.

        For Instagram, scrapes the post directly via Instagram's embed endpoint
        and returns a rich embed plus any extra files (carousel slides).

        The 4th return value is caption/stats text to append after the full
        message rather than splice in place of the link - the link stays
        inline so any surrounding message text isn't clobbered.

        Falls back gracefully:
        - If the post couldn't be scraped, the original URL is left untouched
          so Discord can attempt its own preview.
        - If the primary video is too large to attach, an embed card with the
          thumbnail is still shown so the post isn't completely bare.
        """
        domain = match.group(1).lower()
        if domain not in enabled_domains:
            return match.group(0), [], [], ""
        rest = match.group(2) or ""

        if domain == "instagram.com":
            post_match = INSTAGRAM_POST_PATH.match(rest)
            if not post_match:
                # Not a /p/ or /reel/ link (e.g. a profile page) - nothing
                # for us to fix, so leave it untouched.
                return match.group(0), [], [], ""

            shortcode = post_match.group(1)
            post = await self.instagram_client.get_post(shortcode)
            if post:
                shown_slides = post.slides[:MAX_CAROUSEL_SLIDES]
                # Angle-bracket the link so Discord doesn't also generate its
                # own preview from the raw URL - we provide richer content.
                link = f"<{match.group(0)}>"
                if len(post.slides) > MAX_CAROUSEL_SLIDES:
                    link += f" (showing {len(shown_slides)}/{len(post.slides)} slides)"

                files, is_clipped = await self._carousel_files(
                    shown_slides, filesize_limit, shortcode=shortcode
                )

                if files is not None and shown_slides[0].is_video:
                    # The attached video already renders as its own native
                    # player; an embed on top could only show a static
                    # thumbnail, which would just duplicate it. Put the
                    # caption/stats as plain text instead, appended after the
                    # full message rather than inline with the link.
                    text = self._format_caption_text(post, is_clipped=is_clipped)
                    return link, files, [], text

                # Show an embed card. If the first slide's video was too large
                # to attach (files is None), we still build the card with its
                # thumbnail so the post isn't left completely bare.
                embed = self._build_embed(post)
                return link, files or [], [embed], ""

            # Scraping failed - leave the original URL untouched so the message
            # is unchanged and Discord can attempt its own preview.
            logger.debug(
                f"Instagram scrape failed for {match.group(0)!r}, leaving URL untouched"
            )
            return match.group(0), [], [], ""

        return f"https://{DOMAIN_MAP[domain]}{rest}", [], [], ""

    async def _carousel_files(
        self,
        shown_slides: list[MediaSlide],
        filesize_limit: int,
        shortcode: str | None = None,
    ) -> tuple[list[discord.File] | None, bool]:
        """Download the files needed alongside the embed card: the first
        slide's video (if it's a video - the embed can only show a static
        thumbnail for it), plus any remaining carousel slides.

        Uses video_cache to avoid re-downloading/re-transcoding previously seen
        videos, and process_video to compress or clip oversized videos to fit
        within filesize_limit.

        Returns (files, is_clipped). Returns (None, False) if the first slide
        is a video that could not be downloaded or processed to fit within
        filesize_limit - callers fall back to the thumbnail embed card.
        Oversized non-primary slides that fail to fit are skipped.
        """
        files = []
        is_clipped = False
        max_video_download = max(MAX_RAW_VIDEO_DOWNLOAD_SIZE, filesize_limit)

        first = shown_slides[0]
        if first.is_video:
            cached = None
            if shortcode:
                cached = await self.video_cache.get(
                    shortcode=shortcode, slide_index=1, max_size=filesize_limit
                )

            if cached is not None:
                video_data, is_clipped = cached
                files.append(
                    discord.File(io.BytesIO(video_data), filename="slide_1.mp4")
                )
            else:
                raw_data = await self.instagram_client.download(
                    first.url, max_size=max_video_download
                )
                if raw_data is None:
                    return None, False

                result = await process_video(raw_data, max_size=filesize_limit)
                if result is None:
                    return None, False

                video_data, is_clipped = result
                if shortcode:
                    await self.video_cache.set(
                        shortcode=shortcode,
                        slide_index=1,
                        max_size=filesize_limit,
                        data=video_data,
                        is_clipped=is_clipped,
                    )
                files.append(
                    discord.File(io.BytesIO(video_data), filename="slide_1.mp4")
                )

        for i, slide in enumerate(shown_slides[1:], start=2):
            if slide.is_video:
                cached = None
                if shortcode:
                    cached = await self.video_cache.get(
                        shortcode=shortcode, slide_index=i, max_size=filesize_limit
                    )

                if cached is not None:
                    video_data, _ = cached
                    files.append(
                        discord.File(io.BytesIO(video_data), filename=f"slide_{i}.mp4")
                    )
                else:
                    raw_data = await self.instagram_client.download(
                        slide.url, max_size=max_video_download
                    )
                    if raw_data is None:
                        continue
                    result = await process_video(raw_data, max_size=filesize_limit)
                    if result is None:
                        continue
                    video_data, slide_clipped = result
                    if shortcode:
                        await self.video_cache.set(
                            shortcode=shortcode,
                            slide_index=i,
                            max_size=filesize_limit,
                            data=video_data,
                            is_clipped=slide_clipped,
                        )
                    files.append(
                        discord.File(io.BytesIO(video_data), filename=f"slide_{i}.mp4")
                    )
            else:
                data = await self.instagram_client.download(
                    slide.url, max_size=filesize_limit
                )
                if data is None:
                    continue
                files.append(discord.File(io.BytesIO(data), filename=f"slide_{i}.jpg"))

        return files, is_clipped

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
    def _format_caption_text(post: InstagramPost, is_clipped: bool = False) -> str:
        """Format author/caption/stats as plain text, for posts whose video
        attachment already needs its own native player (no embed on top).
        """
        lines = []

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

        if is_clipped:
            lines.append("*(preview - full video exceeds Discord file size limit)*")

        return "\n".join(lines)

    async def _process_content(
        self, content: str, enabled_domains: set[str], filesize_limit: int
    ) -> tuple[str, list[discord.File], list[discord.Embed]]:
        """Rewrite all matched links in a message's content, awaiting the
        per-match domain replacement (which may need to hit the network),
        and collect any extra files/embeds (e.g. an Instagram post's slides
        and card).
        """
        pieces = []
        extra_files = []
        embeds = []
        trailing_texts = []
        last_end = 0
        for match in self.url_pattern.finditer(content):
            pieces.append(content[last_end : match.start()])
            (
                replacement,
                files,
                match_embeds,
                trailing_text,
            ) = await self._replace_domain(match, enabled_domains, filesize_limit)
            pieces.append(replacement)
            extra_files.extend(files)
            embeds.extend(match_embeds)
            if trailing_text:
                trailing_texts.append(trailing_text)
            last_end = match.end()
        pieces.append(content[last_end:])

        new_content = "".join(pieces)
        if trailing_texts:
            new_content += "\n" + "\n\n".join(trailing_texts)
        return new_content, extra_files, embeds

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
            message.content, enabled_domains, message.guild.filesize_limit
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

        if server_settings is not None:
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
