#!/usr/bin/env python3
"""Standalone script to list all deal IDs from lahomewin.com.

This is useful for discovering deal IDs that can be added to the blacklist
or configured in deal_routes.

Usage:
    uv run python scripts/list_deal_ids.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path so we can import lafcbot
sys.path.insert(0, str(Path(__file__).parent.parent))

from lafcbot.clients.lahomewin_client import LaHomeWinClient


async def main():
    """Fetch and display all deals with their IDs."""
    print("Fetching deals from lahomewin.com...\n")

    async with LaHomeWinClient() as client:
        deals = await client.get_all_deals()

        if not deals:
            print("No deals found!")
            return

        print(f"Found {len(deals)} total deals\n")
        print("=" * 80)

        # Group deals by status
        active_deals = [d for d in deals if d.status == "active"]
        inactive_deals = [d for d in deals if d.status == "inactive"]
        offseason_deals = [d for d in deals if d.status == "off-season"]

        # Display active deals
        if active_deals:
            print("\n🟢 ACTIVE DEALS")
            print("-" * 80)
            for deal in active_deals:
                print(f"ID: {deal.deal_id}")
                print(f"   Restaurant: {deal.restaurant_name}")
                print(f"   Team: {deal.team_name}")
                print(f"   Description: {deal.description}")
                if deal.trigger_conditions:
                    print(f"   Conditions: {deal.trigger_conditions}")
                print()

        # Display inactive deals
        if inactive_deals:
            print("\n⚪ INACTIVE DEALS")
            print("-" * 80)
            for deal in inactive_deals:
                print(f"ID: {deal.deal_id}")
                print(f"   Restaurant: {deal.restaurant_name}")
                print(f"   Team: {deal.team_name}")
                print(f"   Description: {deal.description}")
                print()

        # Display off-season deals
        if offseason_deals:
            print("\n🔵 OFF-SEASON DEALS")
            print("-" * 80)
            for deal in offseason_deals:
                print(f"ID: {deal.deal_id}")
                print(f"   Restaurant: {deal.restaurant_name}")
                print(f"   Team: {deal.team_name}")
                print(f"   Description: {deal.description}")
                print()

        # Summary of just IDs for easy copy-paste
        print("\n" + "=" * 80)
        print("DEAL IDs (for config.json):")
        print("-" * 80)
        all_deal_ids = sorted([d.deal_id for d in deals])
        for deal_id in all_deal_ids:
            print(f'  "{deal_id}",')

        print("\nTo add to blacklist, copy IDs into config.json:")
        print('  "blacklist": ["deal-id-1", "deal-id-2"]')


if __name__ == "__main__":
    asyncio.run(main())
