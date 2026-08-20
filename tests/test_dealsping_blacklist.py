"""Tests for dealsping blacklist functionality."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lafcbot.cogs.dealsping import DealsPingCog


@dataclass
class MockDeal:
    """Mock Deal for testing."""

    deal_id: str
    team_name: str
    restaurant_name: str
    description: str
    trigger_conditions: str | None
    redemption_instructions: str | None
    status: str
    redemption_link: str | None = None


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    return bot


@pytest.fixture
def sample_deals():
    """Create sample deals for testing."""
    return [
        MockDeal(
            deal_id="ono-hawaiian-bbq-lafc",
            team_name="LAFC",
            restaurant_name="Ono Hawaiian BBQ",
            description="Free drink with purchase",
            trigger_conditions="LAFC wins",
            redemption_instructions="Show this message",
            status="active",
        ),
        MockDeal(
            deal_id="doordash-lafc",
            team_name="LAFC",
            restaurant_name="DoorDash",
            description="20% off orders",
            trigger_conditions="LAFC scores 3+ goals",
            redemption_instructions="Use code LAFC20",
            status="active",
        ),
        MockDeal(
            deal_id="some-other-deal",
            team_name="Lakers",
            restaurant_name="Pizza Place",
            description="Free pizza",
            trigger_conditions="Lakers win",
            redemption_instructions="Show this code",
            status="active",
        ),
    ]


@pytest.mark.asyncio
async def test_blacklist_filters_deals_command(mock_bot, sample_deals):
    """Test that blacklisted deals are filtered from !deals command."""
    with patch("lafcbot.utils.config.load_config") as mock_config:
        # Configure with blacklist
        mock_config.return_value = {
            "dealsping": {
                "enabled": True,
                "scrape_time_hour": 8,
                "blacklist": ["ono-hawaiian-bbq-lafc"],
                "servers": [],
            }
        }

        # Create cog
        cog = DealsPingCog(mock_bot)

        # Verify blacklist was loaded
        assert "ono-hawaiian-bbq-lafc" in cog.blacklist
        assert len(cog.blacklist) == 1

        # Mock the client response
        cog.lahomewin_client.get_all_deals = AsyncMock(return_value=sample_deals)

        # Mock the context
        ctx = MagicMock()
        ctx.send = AsyncMock()

        # Call the deals command callback directly
        await cog.deals.callback(cog, ctx)

        # Verify send was called
        assert ctx.send.called

        # Get the sent message
        call_args = ctx.send.call_args_list
        sent_message = call_args[0][0][0]

        # Verify blacklisted deal is NOT in output
        assert "Ono Hawaiian BBQ" not in sent_message

        # Verify non-blacklisted deals ARE in output
        assert "DoorDash" in sent_message
        assert "Pizza Place" in sent_message


@pytest.mark.asyncio
async def test_blacklist_filters_deals_list_command(mock_bot, sample_deals):
    """Test that blacklisted deals are filtered from !deals list command."""
    with patch("lafcbot.utils.config.load_config") as mock_config:
        # Configure with multiple blacklisted deals
        mock_config.return_value = {
            "dealsping": {
                "enabled": True,
                "scrape_time_hour": 8,
                "blacklist": ["ono-hawaiian-bbq-lafc", "doordash-lafc"],
                "servers": [],
            }
        }

        # Create cog
        cog = DealsPingCog(mock_bot)

        # Verify blacklist was loaded
        assert len(cog.blacklist) == 2
        assert "ono-hawaiian-bbq-lafc" in cog.blacklist
        assert "doordash-lafc" in cog.blacklist

        # Mock the client response
        cog.lahomewin_client.get_all_deals = AsyncMock(return_value=sample_deals)

        # Mock the context
        ctx = MagicMock()
        ctx.send = AsyncMock()

        # Call the deals list command callback directly
        await cog.deals_list.callback(cog, ctx)

        # Verify send was called
        assert ctx.send.called

        # Get the sent message
        call_args = ctx.send.call_args_list
        sent_message = call_args[0][0][0]

        # Verify blacklisted deals are NOT in output
        assert "Ono Hawaiian BBQ" not in sent_message
        assert "DoorDash" not in sent_message

        # Verify non-blacklisted deal IS in output
        assert "Pizza Place" in sent_message


@pytest.mark.asyncio
async def test_empty_blacklist(mock_bot, sample_deals):
    """Test that empty blacklist shows all deals."""
    with patch("lafcbot.utils.config.load_config") as mock_config:
        # Configure with empty blacklist
        mock_config.return_value = {
            "dealsping": {
                "enabled": True,
                "scrape_time_hour": 8,
                "blacklist": [],
                "servers": [],
            }
        }

        # Create cog
        cog = DealsPingCog(mock_bot)

        # Verify blacklist is empty
        assert len(cog.blacklist) == 0

        # Mock the client response
        cog.lahomewin_client.get_all_deals = AsyncMock(return_value=sample_deals)

        # Mock the context
        ctx = MagicMock()
        ctx.send = AsyncMock()

        # Call the deals command callback directly
        await cog.deals.callback(cog, ctx)

        # Get the sent message
        call_args = ctx.send.call_args_list
        sent_message = call_args[0][0][0]

        # Verify all deals are in output
        assert "Ono Hawaiian BBQ" in sent_message
        assert "DoorDash" in sent_message
        assert "Pizza Place" in sent_message


@pytest.mark.asyncio
async def test_no_blacklist_config(mock_bot, sample_deals):
    """Test that missing blacklist config defaults to empty set."""
    with patch("lafcbot.utils.config.load_config") as mock_config:
        # Configure without blacklist field
        mock_config.return_value = {
            "dealsping": {
                "enabled": True,
                "scrape_time_hour": 8,
                "servers": [],
            }
        }

        # Create cog
        cog = DealsPingCog(mock_bot)

        # Verify blacklist defaults to empty set
        assert len(cog.blacklist) == 0
        assert isinstance(cog.blacklist, set)
