"""Integration tests that call the real FotMob API.

These tests verify that our code works with actual FotMob API responses
and will catch any breaking changes to the API.
"""

from zoneinfo import ZoneInfo

import pytest

from lafcbot.clients.fotmob.client import FotMobClient
from lafcbot.formatters.world_cup import WorldCupFormatter


@pytest.mark.integration
@pytest.mark.asyncio
async def test_matches_wc_command_integration():
    """Test the complete flow that !matches wc uses.

    This integration test:
    1. Fetches World Cup matches from FotMob API (like !matches wc does)
    2. Formats them with the WorldCupFormatter
    3. Verifies the output structure

    This ensures our code works with real FotMob API responses and will
    catch any breaking changes to the API structure.
    """
    # Create client and formatter (same as the bot uses)
    client = FotMobClient(match_output_path=None)
    formatter = WorldCupFormatter(timezone=ZoneInfo("America/Los_Angeles"))

    try:
        # Fetch World Cup matches (league_id 77 = World Cup)
        league_matches = await client.get_league_matches(league_id=77)

        # We might not get matches if there are none scheduled
        if not league_matches:
            pytest.skip("No World Cup matches currently scheduled")

        print(f"\n✓ Fetched {len(league_matches)} World Cup matches from FotMob API")

        # Take first match for detailed testing
        test_match = league_matches[0]
        print(
            f"\n✓ Testing with: {test_match.home_team.name} vs {test_match.away_team.name}"
        )

        # Test format_match_detailed (exercises the broadcast channel path)
        formatted = await formatter.format_match_detailed(test_match, client)

        assert formatted is not None
        assert formatted.match_line
        print(f"\n✓ Match line formatted: {formatted.match_line[:80]}...")

        # Check if we got venue info (not all matches have it)
        if formatted.venue_line:
            print(f"✓ Venue info present: {formatted.venue_line[:80]}...")
            assert "🏟️" in formatted.venue_line

        # Check if we got broadcast info (not all matches have it)
        if formatted.broadcast_line:
            print(f"✓ Broadcast info present: {formatted.broadcast_line[:80]}...")
            assert "📺" in formatted.broadcast_line
            # This is the code path that was being skipped!
            print("✓ BROADCAST CHANNEL PATH EXERCISED!")
        else:
            print("  (No broadcast info for this match)")

        # Test format_daily_matches_message (complete flow like !matches wc)
        from datetime import date

        responses = await formatter.format_daily_matches_message(
            matches=league_matches[:5],  # Test with first 5 matches
            display_date=date.today(),
            is_today=True,
            fotmob_client=client,
        )

        assert len(responses) > 0
        assert responses[0].startswith("**")
        print(f"\n✓ Daily message formatted: {len(responses)} message(s)")
        print(f"✓ First message preview: {responses[0][:100]}...")

        # Verify structure
        for response in responses:
            # Should have header
            assert "**" in response
            # Should have team names or "No matches" type message
            assert len(response) > 10

        print("\n✓ Integration test passed - our code works with real FotMob API!")

    finally:
        await client.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_match_details_with_broadcast_channels():
    """Test fetching match details that should include broadcast channels.

    This specifically tests the path that includes venue and broadcast info,
    which was previously only tested with mocked data.
    """
    client = FotMobClient(match_output_path=None)

    try:
        # Fetch World Cup matches (league_id 77)
        league_matches = await client.get_league_matches(league_id=77)

        if not league_matches:
            pytest.skip("No World Cup matches currently scheduled")

        # Find an upcoming match (more likely to have broadcast info)
        upcoming_match = None
        for match in league_matches:
            if not match.is_finished and not match.is_live:
                upcoming_match = match
                break

        if not upcoming_match:
            # Try to find any match with a page_slug (needed to get broadcast data)
            for match in league_matches[:10]:
                if match.page_slug:
                    upcoming_match = match
                    break

        if not upcoming_match:
            pytest.skip("No World Cup matches with page_slug found")

        print(
            f"\n✓ Testing broadcast channels for: {upcoming_match.home_team.name} vs {upcoming_match.away_team.name}"
        )

        # Fetch detailed match info
        details = None
        if upcoming_match.page_slug:
            details = await client.get_match_details(
                page_slug=upcoming_match.page_slug, force_refresh=True
            )
        elif upcoming_match.id:
            details = await client.get_match_details_authenticated(
                match_id=upcoming_match.id
            )

        if not details:
            pytest.skip("Could not fetch match details")

        # Check structure
        assert details.match is not None
        print("✓ Match details fetched")

        # Check venue (might not be present for all matches)
        if details.match.venue:
            assert details.match.venue.name
            print(f"✓ Venue: {details.match.venue.name}")

        # Check broadcast channels (might not be present for all matches)
        if details.broadcast_channels:
            assert len(details.broadcast_channels) > 0
            print(f"✓ Broadcast channels: {len(details.broadcast_channels)} found")

            # Check structure of broadcast channels
            for channel in details.broadcast_channels[:3]:
                assert channel.channel_name
                print(
                    f"  - {channel.channel_name} ({channel.country_name or 'Unknown'})"
                )

            # Test the format_broadcast_channels function with real data
            formatter = WorldCupFormatter(timezone=ZoneInfo("America/Los_Angeles"))
            broadcast_line = formatter.format_broadcast_channels(
                details.broadcast_channels
            )

            if broadcast_line:
                print(f"✓ Formatted broadcast line: {broadcast_line}")
                assert "📺" in broadcast_line
                print("✓ BROADCAST FORMATTING CODE PATH TESTED WITH REAL DATA!")
            else:
                print("  (No US broadcast channels found)")
        else:
            print("  (No broadcast channels in API response)")

    finally:
        await client.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fotmob_api_response_structure():
    """Verify FotMob API response structure hasn't changed.

    This test documents the expected API structure and will fail
    if FotMob makes breaking changes.
    """
    client = FotMobClient(match_output_path=None)

    try:
        # Test league matches endpoint
        league_matches = await client.get_league_matches(league_id=130)

        if not league_matches:
            pytest.skip("No World Cup matches currently scheduled")

        match = league_matches[0]

        # Verify expected Match object structure
        assert hasattr(match, "id")
        assert hasattr(match, "home_team")
        assert hasattr(match, "away_team")
        assert hasattr(match, "start_time")
        assert hasattr(match, "home_score")
        assert hasattr(match, "away_score")
        assert hasattr(match, "is_live")
        assert hasattr(match, "is_finished")

        print("\n✓ Match object structure validated")
        print(f"  - id: {match.id}")
        print(f"  - teams: {match.home_team.name} vs {match.away_team.name}")
        print(f"  - status: live={match.is_live}, finished={match.is_finished}")

        # If we can get detailed match info, verify its structure
        if match.page_slug or match.id:
            if match.page_slug:
                details = await client.get_match_details(
                    page_slug=match.page_slug, force_refresh=True
                )
            else:
                details = await client.get_match_details_authenticated(
                    match_id=match.id
                )

            if details:
                # Verify MatchDetails structure
                assert hasattr(details, "match")
                assert hasattr(details, "events")
                assert hasattr(details, "broadcast_channels")

                print("\n✓ MatchDetails object structure validated")
                print(f"  - events: {len(details.events)} events")
                print(
                    f"  - broadcast_channels: {len(details.broadcast_channels) if details.broadcast_channels else 0} channels"
                )

                # Verify event structure if any events exist
                if details.events:
                    event = details.events[0]
                    assert hasattr(event, "id")
                    assert hasattr(event, "type")
                    assert hasattr(event, "minute")
                    print("  - event structure validated")

    finally:
        await client.close()
