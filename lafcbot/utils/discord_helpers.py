"""Discord utility functions for channel operations."""

import logging

import discord

logger = logging.getLogger(__name__)


def find_channel_by_name(bot, channel_name: str):
    """
    Find a Discord channel by name across all guilds.

    Args:
        bot: Discord bot instance with guilds attribute
        channel_name: Name of the channel to find

    Returns:
        Channel object if found, None otherwise
    """
    for guild in bot.guilds:
        channel = discord.utils.get(guild.channels, name=channel_name)
        if channel:
            return channel
    return None


async def send_to_channels(bot, message: str, channel_names: list[str]):
    """
    Send a message to one or more Discord channels.

    Handles deduplication if multiple channel names refer to the same channel ID.

    Args:
        bot: Discord bot instance with guilds attribute
        message: Message text to send
        channel_names: List of channel names to send to
    """
    sent_channel_ids = set()
    for channel_name in channel_names:
        if not channel_name:
            logger.debug("Skipping empty channel name")
            continue

        channel = find_channel_by_name(bot, channel_name)
        if not channel:
            logger.warning(f"Channel '{channel_name}' not found in any guild")
            continue

        if channel.id in sent_channel_ids:
            logger.debug(f"Channel {channel_name} already has this message, skipping")
            continue

        try:
            await channel.send(message)
            sent_channel_ids.add(channel.id)
            logger.debug(f"Message sent to channel #{channel_name}")
        except Exception as e:
            logger.error(f"Failed to send message to channel {channel_name}: {e}")


async def send_to_guild_channels(
    bot, message: str, guild_channels: list[tuple[str, str]]
):
    """
    Send a message to specific guild+channel combinations.

    Targets specific guilds by ID instead of searching all guilds by channel name.
    Useful for multi-server deployments where different servers may have different channel names.

    Args:
        bot: Discord bot instance with guilds attribute
        message: Message text to send
        guild_channels: List of (guild_id, channel_name) tuples

    Returns:
        List of Discord message objects that were successfully sent
    """
    sent_channel_ids = set()
    sent_messages = []

    for guild_id, channel_name in guild_channels:
        if not guild_id or not channel_name:
            logger.debug("Skipping empty guild_id or channel_name")
            continue

        guild = bot.get_guild(int(guild_id))
        if not guild:
            logger.warning(f"Guild {guild_id} not found (bot not in this server?)")
            continue

        channel = discord.utils.get(guild.text_channels, name=channel_name)
        if not channel:
            logger.warning(
                f"Channel #{channel_name} not found in guild {guild.name} ({guild_id})"
            )
            continue

        if channel.id in sent_channel_ids:
            logger.debug(f"Channel #{channel_name} already has this message, skipping")
            continue

        try:
            msg = await channel.send(message)
            sent_messages.append(msg)
            sent_channel_ids.add(channel.id)
            logger.debug(f"Message sent to #{channel_name} in {guild.name}")
        except Exception as e:
            logger.error(
                f"Failed to send message to #{channel_name} in guild {guild.name}: {e}"
            )

    return sent_messages
