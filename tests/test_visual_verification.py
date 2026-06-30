"""Visual verification test for formatters and event detection.

Run this test to see actual formatted output for all event types.
This helps verify that formatters produce the expected visual output.

Usage:
    uv run pytest tests/test_visual_verification.py -v -s

The -s flag shows print output for visual inspection.
"""

from zoneinfo import ZoneInfo

import pytest

from lafcbot.formatters.world_cup import WorldCupFormatter
from lafcbot.match_events.detectors import (
    get_card_color,
    is_card_event,
    is_half_event,
    is_substitution_event,
    is_var_event,
)
from lafcbot.testing import list_available_matches, load_test_match


@pytest.fixture
def formatter():
    """Create WorldCupFormatter with PT timezone."""
    return WorldCupFormatter(timezone=ZoneInfo("America/Los_Angeles"))


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")


def print_subsection(title: str):
    """Print a subsection header."""
    print(f"\n{'-' * 80}")
    print(f"  {title}")
    print(f"{'-' * 80}")


class TestVisualVerification:
    """Visual verification tests - run with -s flag to see output."""

    def test_match_overview(self):
        """Display overview of available test matches."""
        print_section("AVAILABLE TEST MATCHES")

        matches = list_available_matches()
        print(f"\nTotal matches available: {len(matches)}")
        print("\nFirst 10 matches:")

        for match_id in matches[:10]:
            try:
                sim = load_test_match(match_id)
                full = sim.get_full_match()
                print(
                    f"  {match_id}: {full.match.home_team.name} vs {full.match.away_team.name} "
                    f"({full.match.home_score}-{full.match.away_score})"
                )
            except Exception as e:
                print(f"  {match_id}: Error loading - {e}")

    def test_match_progression(self, formatter):
        """Display match state at different time points."""
        print_section("MATCH TIME PROGRESSION")

        # Use first available match
        matches = list_available_matches()
        if not matches:
            pytest.skip("No test matches available")

        match_id = matches[0]
        sim = load_test_match(match_id)
        full = sim.get_full_match()

        print(
            f"\nMatch: {full.match.home_team.name} vs {full.match.away_team.name} (ID: {match_id})"
        )
        print(f"Total events: {len(full.events)}")

        # Test different time points
        time_points = [0, 15, 30, 45, 60, 75, 90, 105, 120]

        for minute in time_points:
            details = sim.get_match_at_minute(minute)
            formatted = formatter.format_match_simple(details.match)

            print(f"\n  Minute {minute}:")
            print(f"    Status: {details.match.status}")
            print(f"    Score: {details.match.home_score}-{details.match.away_score}")
            print(f"    Time display: {details.match.match_time_display}")
            print(f"    Events so far: {len(details.events)}")
            print(f"    Formatted: {formatted.match_line}")

    def test_team_formatting(self, formatter):
        """Display team name formatting with flags and rankings."""
        print_section("TEAM NAME FORMATTING")

        # Use first match
        matches = list_available_matches()
        if not matches:
            pytest.skip("No test matches available")

        sim = load_test_match(matches[0])
        full = sim.get_full_match()

        print_subsection("Home Team")
        home_formatted = formatter.format_team_with_flag_and_rank(
            full.match.home_team.name
        )
        print(f"  Original: {full.match.home_team.name}")
        print(f"  Formatted: {home_formatted}")

        print_subsection("Away Team")
        away_formatted = formatter.format_team_with_flag_and_rank(
            full.match.away_team.name
        )
        print(f"  Original: {full.match.away_team.name}")
        print(f"  Formatted: {away_formatted}")

        print_subsection("Sample Countries")
        countries = ["United States", "Mexico", "Brazil", "Germany", "England"]
        for country in countries:
            formatted = formatter.format_team_with_flag_and_rank(country)
            print(f"  {country}: {formatted}")

    def test_goal_events(self):
        """Display all goal events from matches."""
        print_section("GOAL EVENTS")

        matches = list_available_matches()
        goal_count = 0

        for match_id in matches[:10]:  # Check first 10 matches
            try:
                sim = load_test_match(match_id)
                full = sim.get_full_match()

                goal_events = [e for e in full.events if e.type.lower() == "goal"]

                if goal_events:
                    print_subsection(
                        f"{full.match.home_team.name} vs {full.match.away_team.name}"
                    )

                    for goal in goal_events:
                        goal_count += 1
                        minute_str = f"{goal.minute}'"
                        if goal.added_time:
                            minute_str = f"{goal.minute}+{goal.added_time}'"

                        goal_type = ""
                        if goal.own_goal:
                            goal_type = " (OWN GOAL)"
                        elif goal.assist_name:
                            goal_type = f" (assist: {goal.assist_name})"

                        team = (
                            full.match.home_team.name
                            if goal.team_id == full.match.home_team.id
                            else full.match.away_team.name
                        )

                        print(
                            f"  ⚽ {minute_str} - {goal.player_name or 'Unknown'} ({team}){goal_type}"
                        )

            except Exception:
                continue

        print(f"\nTotal goals found across matches: {goal_count}")

    def test_card_events(self):
        """Display all card events from matches."""
        print_section("CARD EVENTS")

        matches = list_available_matches()
        card_count = 0

        for match_id in matches[:10]:
            try:
                sim = load_test_match(match_id)
                full = sim.get_full_match()

                card_events = [e for e in full.events if is_card_event(e)]

                if card_events:
                    print_subsection(
                        f"{full.match.home_team.name} vs {full.match.away_team.name}"
                    )

                    for card in card_events:
                        card_count += 1
                        minute_str = f"{card.minute}'"
                        if card.added_time:
                            minute_str = f"{card.minute}+{card.added_time}'"

                        card_color = get_card_color(card)
                        emoji = "🟨" if card_color == "yellow" else "🟥"

                        team = (
                            full.match.home_team.name
                            if card.team_id == full.match.home_team.id
                            else full.match.away_team.name
                        )

                        print(
                            f"  {emoji} {minute_str} - {card.player_name or 'Unknown'} ({team}) - {card_color.upper()}"
                        )

            except Exception:
                continue

        print(f"\nTotal cards found across matches: {card_count}")

    def test_substitution_events(self):
        """Display all substitution events from matches."""
        print_section("SUBSTITUTION EVENTS")

        matches = list_available_matches()
        sub_count = 0

        for match_id in matches[:10]:
            try:
                sim = load_test_match(match_id)
                full = sim.get_full_match()

                sub_events = [e for e in full.events if is_substitution_event(e)]

                if sub_events:
                    print_subsection(
                        f"{full.match.home_team.name} vs {full.match.away_team.name}"
                    )

                    for sub in sub_events:
                        sub_count += 1
                        minute_str = f"{sub.minute}'"
                        if sub.added_time:
                            minute_str = f"{sub.minute}+{sub.added_time}'"

                        player_out = sub.player_name or "Unknown"
                        player_in = sub.assist_name or "Unknown"

                        team = (
                            full.match.home_team.name
                            if sub.team_id == full.match.home_team.id
                            else full.match.away_team.name
                        )

                        print(
                            f"  🔄 {minute_str} - {player_in} ON for {player_out} ({team})"
                        )

            except Exception:
                continue

        print(f"\nTotal substitutions found across matches: {sub_count}")

    def test_half_events(self):
        """Display half-time and full-time events from matches."""
        print_section("HALF-TIME / FULL-TIME EVENTS")

        matches = list_available_matches()
        half_count = 0

        for match_id in matches[:10]:
            try:
                sim = load_test_match(match_id)
                full = sim.get_full_match()

                half_events = [e for e in full.events if is_half_event(e)]

                if half_events:
                    print_subsection(
                        f"{full.match.home_team.name} vs {full.match.away_team.name}"
                    )

                    for half in half_events:
                        half_count += 1
                        minute_str = f"{half.minute}'"

                        half_type = half.half_type or "Unknown"
                        emoji = "⏸️" if half_type == "HT" else "⏹️"

                        print(f"  {emoji} {minute_str} - {half_type}")

            except Exception:
                continue

        print(f"\nTotal half/full-time events found: {half_count}")

    def test_var_events(self):
        """Display VAR events from matches."""
        print_section("VAR EVENTS")

        matches = list_available_matches()
        var_count = 0

        for match_id in matches[:20]:  # Check more matches for VAR
            try:
                sim = load_test_match(match_id)
                full = sim.get_full_match()

                var_events = [e for e in full.events if is_var_event(e)]

                if var_events:
                    print_subsection(
                        f"{full.match.home_team.name} vs {full.match.away_team.name}"
                    )

                    for var in var_events:
                        var_count += 1
                        minute_str = f"{var.minute}'"
                        if var.added_time:
                            minute_str = f"{var.minute}+{var.added_time}'"

                        print(f"  📹 {minute_str} - VAR: {var.description or 'Check'}")
                        if var.var_decision:
                            print(f"      Decision: {var.var_decision}")

            except Exception:
                continue

        print(f"\nTotal VAR events found: {var_count}")
        if var_count == 0:
            print("(No VAR events found in available test data)")

    def test_penalty_shootout_formatting(self, formatter):
        """Display penalty shootout formatting if available."""
        print_section("PENALTY SHOOTOUT FORMATTING")

        matches = list_available_matches()
        penalty_count = 0

        for match_id in matches:
            try:
                sim = load_test_match(match_id)
                full = sim.get_full_match()

                if full.penalty_kicks and len(full.penalty_kicks) > 0:
                    penalty_count += 1
                    print_subsection(
                        f"{full.match.home_team.name} vs {full.match.away_team.name}"
                    )

                    # Format penalty shootout cards
                    card_result = formatter.format_penalty_shootout_cards(
                        full.penalty_kicks,
                        full.match.home_team.name,
                        full.match.away_team.name,
                        is_live=False,
                    )

                    print("  Penalty Shootout Cards:")
                    print(f"  {card_result}")

                    if full.penalties:
                        print(
                            f"  Final Score: {full.penalties.home_score}-{full.penalties.away_score}"
                        )

                    print("\n  Individual Kicks:")
                    for pk in full.penalty_kicks:
                        result = "SCORED ⚽" if pk.scored else "MISSED ❌"
                        team = "Home" if pk.is_home else "Away"
                        print(f"    {team} - {pk.player_name}: {result}")

            except Exception:
                continue

        if penalty_count == 0:
            print("\nNo penalty shootouts found in available test data")
            print("Testing with empty penalty data:")
            result = formatter.format_penalty_shootout_cards(
                penalty_kicks=[],
                home_team_name="Test Home",
                away_team_name="Test Away",
                is_live=False,
            )
            print(f"  Empty result: '{result}' (should be empty string)")

    def test_venue_and_broadcast(self, formatter):
        """Display venue and broadcast information formatting."""
        print_section("VENUE & BROADCAST INFORMATION")

        matches = list_available_matches()
        venue_count = 0
        broadcast_count = 0

        for match_id in matches[:10]:
            try:
                sim = load_test_match(match_id)
                full = sim.get_full_match()

                has_info = False

                if full.match.venue:
                    venue_count += 1
                    has_info = True

                if full.broadcast_channels:
                    broadcast_count += 1
                    has_info = True

                if has_info:
                    print_subsection(
                        f"{full.match.home_team.name} vs {full.match.away_team.name}"
                    )

                    if full.match.venue:
                        venue_formatted = formatter.format_venue_info(full.match.venue)
                        print(f"  Venue: {venue_formatted}")

                    if full.broadcast_channels:
                        broadcast_formatted = formatter.format_broadcast_channels(
                            full.broadcast_channels
                        )
                        if broadcast_formatted:
                            print(f"  Broadcast: {broadcast_formatted}")
                        else:
                            print("  Broadcast: (No US channels)")

            except Exception:
                continue

        print(f"\nMatches with venue info: {venue_count}")
        print(f"Matches with broadcast info: {broadcast_count}")

    def test_complete_match_summary(self, formatter):
        """Display complete formatted output for a match."""
        print_section("COMPLETE MATCH SUMMARY")

        matches = list_available_matches()
        if not matches:
            pytest.skip("No test matches available")

        # Find a match with multiple event types
        best_match = None
        max_events = 0

        for match_id in matches[:10]:
            try:
                sim = load_test_match(match_id)
                full = sim.get_full_match()
                event_count = len(full.events)

                if event_count > max_events:
                    max_events = event_count
                    best_match = (match_id, sim, full)
            except Exception:
                continue

        if not best_match:
            pytest.skip("Could not find suitable test match")

        match_id, sim, full = best_match

        print(f"\nMatch ID: {match_id}")
        print(f"Teams: {full.match.home_team.name} vs {full.match.away_team.name}")
        print(f"Final Score: {full.match.home_score}-{full.match.away_score}")
        print(f"Status: {full.match.status}")
        print(f"Total Events: {len(full.events)}")

        # Format match line
        print_subsection("Match Line")
        formatted = formatter.format_match_simple(full.match)
        print(f"  {formatted.match_line}")

        # Display all events chronologically
        print_subsection("Event Timeline")

        for event in full.events[:20]:  # Show first 20 events
            minute_str = f"{event.minute}'"
            if event.added_time:
                minute_str = f"{event.minute}+{event.added_time}'"

            emoji_map = {
                "goal": "⚽",
                "card": "🟨" if event.card_color == "yellow" else "🟥",
                "substitution": "🔄",
                "half": "⏸️",
                "var": "📹",
            }

            emoji = emoji_map.get(event.type.lower(), "📝")
            player_info = f" - {event.player_name}" if event.player_name else ""

            print(f"  {minute_str} {emoji} {event.type.upper()}{player_info}")

        if len(full.events) > 20:
            print(f"  ... and {len(full.events) - 20} more events")

    def test_score_progression(self):
        """Display how scores change throughout a match."""
        print_section("SCORE PROGRESSION")

        matches = list_available_matches()
        if not matches:
            pytest.skip("No test matches available")

        # Find a match with goals
        for match_id in matches[:10]:
            try:
                sim = load_test_match(match_id)
                full = sim.get_full_match()

                goal_events = [e for e in full.events if e.type.lower() == "goal"]

                if len(goal_events) >= 2:  # At least 2 goals
                    print_subsection(
                        f"{full.match.home_team.name} vs {full.match.away_team.name}"
                    )

                    # Track score progression
                    home_score = 0
                    away_score = 0

                    print(f"  Starting Score: {home_score}-{away_score}")

                    for goal in goal_events:
                        minute_str = f"{goal.minute}'"
                        if goal.added_time:
                            minute_str = f"{goal.minute}+{goal.added_time}'"

                        # Update scores
                        if not goal.own_goal:
                            if goal.team_id == full.match.home_team.id:
                                home_score += 1
                            elif goal.team_id == full.match.away_team.id:
                                away_score += 1
                        else:
                            # Own goal
                            if goal.team_id == full.match.home_team.id:
                                away_score += 1
                            elif goal.team_id == full.match.away_team.id:
                                home_score += 1

                        scorer_team = (
                            full.match.home_team.name
                            if goal.team_id == full.match.home_team.id
                            else full.match.away_team.name
                        )

                        og_flag = " (OG)" if goal.own_goal else ""

                        print(
                            f"  {minute_str} - {goal.player_name or 'Unknown'} ({scorer_team}){og_flag}"
                        )
                        print(f"            Score: {home_score}-{away_score}")

                    print(f"\n  Final Score: {home_score}-{away_score}")
                    break  # Only show one match

            except Exception:
                continue

    @pytest.mark.asyncio
    async def test_bot_daily_message_format(self, formatter):
        """Display the ACTUAL format used by the bot for daily messages.

        This uses the same format_daily_matches_message() method that
        WorldCupTask uses to send daily match updates to Discord.
        """
        print_section("BOT'S ACTUAL DAILY MESSAGE FORMAT")

        matches = list_available_matches()
        if not matches:
            pytest.skip("No test matches available")

        # Load a few matches
        match_list = []
        for match_id in matches[:3]:
            try:
                sim = load_test_match(match_id)
                full = sim.get_full_match()
                match_list.append(full.match)
            except Exception:
                continue

        if not match_list:
            pytest.skip("Could not load test matches")

        print_subsection("Simulating Bot's Daily Notification")

        # Create a mock FotMob client for the formatter
        from datetime import date
        from unittest.mock import AsyncMock, MagicMock

        mock_client = MagicMock()
        mock_client.get_match_details = AsyncMock(return_value=None)
        mock_client.get_match_details_authenticated = AsyncMock(return_value=None)

        # Format using the ACTUAL bot method
        responses = await formatter.format_daily_matches_message(
            matches=match_list,
            display_date=date.today(),
            is_today=True,
            fotmob_client=mock_client,
        )

        print("\nNumber of message chunks:", len(responses))
        print("\n" + "=" * 80)

        for i, response in enumerate(responses, 1):
            if len(responses) > 1:
                print(f"\n--- Message Chunk {i}/{len(responses)} ---")
            print(response)
            print("=" * 80)

        print("\n✓ This is the EXACT format the bot sends to Discord")

    @pytest.mark.asyncio
    async def test_bot_match_detailed_format(self, formatter):
        """Display the ACTUAL detailed match format used by the bot.

        This uses format_match_detailed() which is called internally
        by format_daily_matches_message().
        """
        print_section("BOT'S DETAILED MATCH FORMAT")

        matches = list_available_matches()
        if not matches:
            pytest.skip("No test matches available")

        # Load first match
        sim = load_test_match(matches[0])
        full = sim.get_full_match()

        print_subsection(f"{full.match.home_team.name} vs {full.match.away_team.name}")

        # Create mock client that returns our test data
        from lafcbot.testing.mock_fotmob_client import MockFotMobClient

        mock_client = MockFotMobClient(sim)
        mock_client.set_minute(90)  # Get full match

        # Format using the ACTUAL bot method
        formatted = await formatter.format_match_detailed(full.match, mock_client)

        print("\nMatch Line:")
        print(f"  {formatted.match_line}")

        if formatted.venue_line:
            print("\nVenue:")
            print(f"  {formatted.venue_line}")

        if formatted.broadcast_line:
            print("\nBroadcast:")
            print(f"  {formatted.broadcast_line}")

        print("\nFormatted Complete:")
        print(formatted.format())

        print("\n✓ This is the EXACT format the bot uses for match details")

    @pytest.mark.asyncio
    async def test_bot_live_event_notifications(self):
        """Display the ACTUAL notification formats for live match events.

        This shows exactly what the bot sends to Discord when goals,
        cards, substitutions, etc. happen during a live match.
        """
        print_section("BOT'S LIVE EVENT NOTIFICATION FORMATS")

        matches = list_available_matches()
        if not matches:
            pytest.skip("No test matches available")

        # Find a match with various event types
        from lafcbot.match_events.notifiers import MatchNotifier
        from lafcbot.testing.discord_mocks import create_test_bot_with_channels
        from lafcbot.testing.mock_fotmob_client import MockFotMobClient

        for match_id in matches[:5]:
            try:
                sim = load_test_match(match_id)
                full = sim.get_full_match()

                # Check if match has interesting events
                goal_events = [e for e in full.events if e.type.lower() == "goal"]
                card_events = [e for e in full.events if is_card_event(e)]
                sub_events = [e for e in full.events if is_substitution_event(e)]

                if not (goal_events or card_events or sub_events):
                    continue

                print_subsection(
                    f"{full.match.home_team.name} vs {full.match.away_team.name}"
                )

                # Set up notifier with mock bot
                mock_bot, guild, channels = create_test_bot_with_channels(
                    channel_names=["world-cup-live"]
                )
                mock_client = MockFotMobClient(sim)
                mock_client.set_minute(90)

                config = {
                    "timezone": "America/Los_Angeles",
                    "servers": [
                        {
                            "guild_id": guild.id,
                            "live_channel_name": "world-cup-live",
                        }
                    ],
                }

                from zoneinfo import ZoneInfo

                notifier = MatchNotifier(
                    mock_bot,
                    config,
                    ZoneInfo("America/Los_Angeles"),
                    [config["servers"][0]],
                )

                # Show GOAL notifications
                if goal_events:
                    print("\n  GOAL Notifications:")
                    for goal in goal_events[:2]:  # Show first 2 goals
                        channels["world-cup-live"].sent_messages.clear()
                        await notifier.notify_goal(None, full, goal)
                        if channels["world-cup-live"].sent_messages:
                            msg = channels["world-cup-live"].sent_messages[0].content
                            print(f"\n{msg}")
                            print("  " + "-" * 76)

                # Show CARD notifications
                if card_events:
                    print("\n  CARD Notifications:")
                    for card in card_events[:2]:  # Show first 2 cards
                        channels["world-cup-live"].sent_messages.clear()
                        await notifier.notify_card(None, full, card)
                        if channels["world-cup-live"].sent_messages:
                            msg = channels["world-cup-live"].sent_messages[0].content
                            print(f"\n{msg}")
                            print("  " + "-" * 76)

                # Show SUBSTITUTION notifications
                if sub_events:
                    print("\n  SUBSTITUTION Notifications:")
                    for sub in sub_events[:2]:  # Show first 2 subs
                        channels["world-cup-live"].sent_messages.clear()
                        await notifier.notify_substitution(None, full, sub)
                        if channels["world-cup-live"].sent_messages:
                            msg = channels["world-cup-live"].sent_messages[0].content
                            print(f"\n{msg}")
                            print("  " + "-" * 76)

                print(
                    "\n✓ These are the EXACT formats the bot sends during live matches"
                )
                break  # Only show one match

            except Exception as e:
                print(f"\nError processing match {match_id}: {e}")
                continue


# Run this test file with: uv run pytest tests/test_visual_verification.py -v -s
