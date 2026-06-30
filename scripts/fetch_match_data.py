#!/usr/bin/env python3
"""Fetch match data from FotMob and save to test_data directory."""

import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import lafcbot
sys.path.insert(0, str(Path(__file__).parent.parent))

from lafcbot.clients.fotmob.client import FotMobClient


async def fetch_match_data(match_id: int, output_dir: Path):
    """
    Fetch match data from FotMob and save to test_data directory.

    Args:
        match_id: The FotMob match ID to fetch
        output_dir: Directory to save the match data
    """
    import json

    # Create client without output path (we'll save manually)
    client = FotMobClient(match_output_path=None)

    try:
        print(f"Fetching match {match_id}...")

        # Fetch match details using authenticated endpoint
        data = await client.get_match_details_authenticated(
            match_id=match_id, force_refresh=True
        )

        if not data:
            print(f"ERROR: Failed to fetch match {match_id}")
            return False

        # Now fetch the raw JSON data to save
        # Use the same authenticated endpoint
        from lafcbot.clients.fotmob.client import generate_xmas_token

        api_path = f"/api/data/matchDetails?matchId={match_id}"
        url = f"https://www.fotmob.com{api_path}"
        xmas_token = generate_xmas_token(api_path)

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "x-mas": xmas_token,
        }

        # Fetch raw JSON
        async with client._session.get(url, headers=headers) as response:
            if response.status != 200:
                print(f"ERROR: HTTP {response.status} when fetching raw data")
                return False

            raw_data = await response.json()

        # Save to file
        output_file = output_dir / f"match_{match_id}_dump.json"
        with open(output_file, "w") as f:
            json.dump(raw_data, f, indent=2)

        # Print match info
        match = data.match
        print(f"✓ Fetched and saved match {match_id}")
        print(f"  {match.home_team.name} vs {match.away_team.name}")
        print(f"  Score: {match.home_score}-{match.away_score}")
        print(f"  Finished: {match.is_finished}")
        print(f"  Events: {len(data.events)}")
        if data.penalties:
            print(
                f"  Penalties: {data.penalties.home_score}-{data.penalties.away_score}"
            )
        if data.penalty_kicks:
            print(f"  Penalty kicks: {len(data.penalty_kicks)} recorded")

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        await client.close()


async def main():
    parser = argparse.ArgumentParser(description="Fetch match data from FotMob")
    parser.add_argument("match_ids", nargs="+", type=int, help="Match IDs to fetch")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "test_data",
        help="Output directory (default: test_data/)",
    )

    args = parser.parse_args()

    # Create output directory if needed
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output directory: {args.output_dir}")
    print(f"Fetching {len(args.match_ids)} match(es)...\n")

    success_count = 0
    for match_id in args.match_ids:
        if await fetch_match_data(match_id, args.output_dir):
            success_count += 1
        print()

    print(f"\nCompleted: {success_count}/{len(args.match_ids)} successful")


if __name__ == "__main__":
    asyncio.run(main())
