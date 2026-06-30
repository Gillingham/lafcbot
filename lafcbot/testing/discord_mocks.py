"""Mock Discord objects for testing notifications without actual Discord sends.

This module provides mock implementations of Discord bot, channel, message, and
guild objects that track method calls for assertion in tests.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockMessage:
    """Mock discord.Message object.

    Tracks edit() calls for testing message updates (e.g., goal scorer changes).
    """

    content: str
    id: int = 0
    channel: Any = None
    embeds: list = field(default_factory=list)
    edit_history: list[str] = field(default_factory=list)

    async def edit(self, content: str = None, **kwargs):
        """Mock message edit.

        Args:
            content: New message content
            **kwargs: Additional edit parameters (ignored)
        """
        if content:
            self.edit_history.append(self.content)
            self.content = content


@dataclass
class MockChannel:
    """Mock discord.TextChannel object.

    Tracks send() calls for testing notification delivery.
    """

    name: str
    id: int = 0
    guild: Any = None
    sent_messages: list[MockMessage] = field(default_factory=list)
    _message_id_counter: int = 1

    async def send(self, content: str = None, **kwargs) -> MockMessage:
        """Mock channel send.

        Args:
            content: Message content
            **kwargs: Additional send parameters (embeds, etc.)

        Returns:
            MockMessage that was "sent"
        """
        message = MockMessage(
            content=content or "",
            id=self._message_id_counter,
            channel=self,
            embeds=kwargs.get("embeds", []),
        )
        self._message_id_counter += 1
        self.sent_messages.append(message)
        return message

    def get_messages_by_content(self, substring: str) -> list[MockMessage]:
        """Find messages containing a substring.

        Args:
            substring: Text to search for

        Returns:
            List of messages containing the substring
        """
        return [msg for msg in self.sent_messages if substring in msg.content]


@dataclass
class MockGuild:
    """Mock discord.Guild object.

    Provides channel lookup for testing multi-channel notifications.
    """

    name: str
    id: int
    channels: dict[str, MockChannel] = field(default_factory=dict)

    def get_channel_by_name(self, channel_name: str) -> MockChannel | None:
        """Get channel by name.

        Args:
            channel_name: Channel name to lookup

        Returns:
            MockChannel if found, None otherwise
        """
        return self.channels.get(channel_name)

    async def fetch_channel(self, channel_id: int) -> MockChannel | None:
        """Mock fetch channel by ID.

        Args:
            channel_id: Channel ID

        Returns:
            First channel matching the ID, or None
        """
        for channel in self.channels.values():
            if channel.id == channel_id:
                return channel
        return None


class MockBot:
    """Mock discord.Bot object.

    Provides guild/channel management for testing notification delivery.
    """

    def __init__(self):
        """Initialize mock bot."""
        self.guilds: dict[int, MockGuild] = {}
        self._is_ready = True

    def add_guild(self, guild: MockGuild):
        """Add a guild to the bot.

        Args:
            guild: MockGuild to add
        """
        self.guilds[guild.id] = guild

    def get_guild(self, guild_id: int) -> MockGuild | None:
        """Get guild by ID.

        Args:
            guild_id: Guild ID

        Returns:
            MockGuild if found, None otherwise
        """
        return self.guilds.get(guild_id)

    async def wait_until_ready(self):
        """Mock wait until ready (no-op)."""
        if not self._is_ready:
            await asyncio.sleep(0.001)  # Minimal delay for realism

    def get_all_sent_messages(self) -> list[tuple[str, str, MockMessage]]:
        """Get all messages sent across all guilds/channels.

        Returns:
            List of (guild_name, channel_name, message) tuples
        """
        messages = []
        for guild in self.guilds.values():
            for channel in guild.channels.values():
                for message in channel.sent_messages:
                    messages.append((guild.name, channel.name, message))
        return messages

    def get_messages_by_content(self, substring: str) -> list[MockMessage]:
        """Find all messages containing a substring across all channels.

        Args:
            substring: Text to search for

        Returns:
            List of messages containing the substring
        """
        messages = []
        for guild in self.guilds.values():
            for channel in guild.channels.values():
                messages.extend(channel.get_messages_by_content(substring))
        return messages


def create_test_bot_with_channels(
    guild_id: int = 123456789,
    guild_name: str = "Test Server",
    channel_names: list[str] = None,
) -> tuple[MockBot, MockGuild, dict[str, MockChannel]]:
    """Create a mock bot with guild and channels for testing.

    Convenience function for quickly setting up test fixtures.

    Args:
        guild_id: Guild ID to use
        guild_name: Guild name
        channel_names: List of channel names to create (default: ["test-channel"])

    Returns:
        Tuple of (bot, guild, channels_dict)
    """
    if channel_names is None:
        channel_names = ["test-channel"]

    bot = MockBot()

    guild = MockGuild(name=guild_name, id=guild_id)

    channels = {}
    for i, name in enumerate(channel_names, start=1):
        channel = MockChannel(name=name, id=i, guild=guild)
        guild.channels[name] = channel
        channels[name] = channel

    bot.add_guild(guild)

    return bot, guild, channels
