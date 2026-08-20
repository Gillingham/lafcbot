"""Tests for deals formatter."""

from dataclasses import dataclass

import pytest

from lafcbot.formatters.deals import DealsFormatter
from lafcbot.utils.config import load_timezone


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
def formatter():
    """Create a DealsFormatter instance."""
    return DealsFormatter(load_timezone())


@pytest.fixture
def sample_deal():
    """Create a sample deal."""
    return MockDeal(
        deal_id="test-deal",
        team_name="Test Team",
        restaurant_name="Test Restaurant",
        description="50% off all items",
        trigger_conditions="Team wins",
        redemption_instructions="Show this code: TEST123",
        status="active",
    )


def test_format_active_deals_returns_list(formatter, sample_deal):
    """Test that format_active_deals_with_redemption returns a list of blocks."""
    result = formatter.format_active_deals_with_redemption([sample_deal])

    assert isinstance(result, list)
    assert len(result) == 2  # Header + 1 deal
    assert "Active Deals Today (1)" in result[0]
    assert "Test Restaurant" in result[1]


def test_format_active_deals_multiple_deals(formatter, sample_deal):
    """Test formatting multiple deals returns separate blocks."""
    deal2 = MockDeal(
        deal_id="test-deal-2",
        team_name="Test Team 2",
        restaurant_name="Test Restaurant 2",
        description="Free fries",
        trigger_conditions="Team scores 3 goals",
        redemption_instructions="Show this code: FRIES456",
        status="active",
    )

    result = formatter.format_active_deals_with_redemption([sample_deal, deal2])

    assert isinstance(result, list)
    assert len(result) == 3  # Header + 2 deals
    assert "Active Deals Today (2)" in result[0]
    assert "Test Restaurant" in result[1]
    assert "Test Restaurant 2" in result[2]


def test_format_active_deals_no_deals(formatter):
    """Test formatting with no active deals."""
    result = formatter.format_active_deals_with_redemption([])

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0] == "No deals are active today"


def test_deal_block_contains_all_info(formatter, sample_deal):
    """Test that each deal block contains all the deal information."""
    result = formatter.format_active_deals_with_redemption([sample_deal])

    deal_block = result[1]
    assert "Test Restaurant" in deal_block
    assert "50% off all items" in deal_block
    assert "Test Team: Team wins" in deal_block
    assert "How to redeem" in deal_block
    assert "TEST123" in deal_block


def test_deal_block_without_optional_fields(formatter):
    """Test deal block when optional fields are missing."""
    minimal_deal = MockDeal(
        deal_id="minimal-deal",
        team_name="Test Team",
        restaurant_name="Minimal Restaurant",
        description="Basic deal",
        trigger_conditions=None,
        redemption_instructions=None,
        status="active",
    )

    result = formatter.format_active_deals_with_redemption([minimal_deal])

    deal_block = result[1]
    assert "Minimal Restaurant" in deal_block
    assert "Basic deal" in deal_block
    # Should not have trigger conditions or redemption if not provided
    assert "How to redeem" not in deal_block
