"""Integration tests for scraping lahomewin.com."""

import pytest

from lafcbot.clients.lahomewin_client import LaHomeWinClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scrape_real_website():
    """Test scraping the real lahomewin.com website.

    This test makes a real HTTP request to verify our scraper works
    with the actual website structure.
    """
    async with LaHomeWinClient() as client:
        deals = await client.get_all_deals()

    # Basic assertions
    assert len(deals) > 0, "Should find at least one deal"

    # Check that all deals have required fields
    for deal in deals:
        assert deal.deal_id, f"Deal missing ID: {deal}"
        assert deal.restaurant_name, f"Deal missing restaurant name: {deal}"
        assert deal.team_name, f"Deal missing team name: {deal}"
        assert deal.status in [
            "active",
            "inactive",
            "off-season",
        ], f"Invalid status: {deal.status}"
        assert (
            deal.redemption_instructions
        ), f"Deal missing redemption instructions: {deal}"

    # Log all deal IDs for manual verification
    print("\nScraped deals:")
    for deal in sorted(deals, key=lambda d: d.deal_id):
        print(
            f"  - {deal.deal_id} ({deal.restaurant_name} - {deal.team_name}) [{deal.status}]"
        )

    # Check for known deals (these should exist on the website)
    deal_ids = [d.deal_id for d in deals]
    print(f"\nTotal deals found: {len(deal_ids)}")
    print(f"Active deals: {len([d for d in deals if d.status == 'active'])}")
    print(f"Inactive deals: {len([d for d in deals if d.status == 'inactive'])}")
    print(f"Off-season deals: {len([d for d in deals if d.status == 'off-season'])}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deal_id_consistency():
    """Test that deal IDs are consistent across multiple scrapes."""
    async with LaHomeWinClient() as client:
        # First scrape
        deals1 = await client.get_all_deals()
        deal_ids1 = {d.deal_id for d in deals1}

        # Clear cache and scrape again
        client._cached_deals = None
        client._cache_time = None

        deals2 = await client.get_all_deals()
        deal_ids2 = {d.deal_id for d in deals2}

    # Deal IDs should be identical
    assert deal_ids1 == deal_ids2, "Deal IDs changed between scrapes"
