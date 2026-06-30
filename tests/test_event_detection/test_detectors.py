"""Tests for event detection logic.

Tests event classification functions using real match data.
"""

import pytest

from lafcbot.match_events.detectors import (
    get_card_color,
    is_card_event,
    is_half_event,
    is_substitution_event,
    normalize_half_type,
)
from lafcbot.testing import list_available_matches, load_test_match


@pytest.fixture
def sample_match_id():
    """Get first available test match ID."""
    matches = list_available_matches()
    if not matches:
        pytest.skip("No test match data available")
    return matches[0]


class TestGoalDetection:
    """Test goal event detection."""

    def test_goal_events_have_type_goal(self, sample_match_id):
        """Test that goal events are properly identified."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        goal_events = [e for e in details.events if e.type.lower() == "goal"]

        # Each goal event should have required fields
        for goal in goal_events:
            assert goal.id is not None
            assert goal.minute >= 0
            # Team ID should be set
            assert goal.team_id is not None

    def test_own_goal_detection(self, sample_match_id):
        """Test own goal flag detection."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        goal_events = [e for e in details.events if e.type.lower() == "goal"]

        # Check that own_goal flag exists
        for goal in goal_events:
            assert isinstance(goal.own_goal, bool)


class TestCardDetection:
    """Test card event detection."""

    def test_is_card_event(self, sample_match_id):
        """Test card event detection function."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        for event in details.events:
            if "card" in event.type.lower():
                assert is_card_event(event)

    def test_get_card_color(self, sample_match_id):
        """Test card color extraction."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        card_events = [e for e in details.events if is_card_event(e)]

        for card in card_events:
            color = get_card_color(card)
            assert color in ("yellow", "red", "card")


class TestSubstitutionDetection:
    """Test substitution event detection."""

    def test_is_substitution_event(self, sample_match_id):
        """Test substitution detection function."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        for event in details.events:
            if "sub" in event.type.lower() or event.type.lower() == "substitution":
                result = is_substitution_event(event)
                # Should be True if event has player data
                if event.player_name or event.assist_name:
                    assert result is True

    def test_substitution_player_names(self, sample_match_id):
        """Test substitution events have player data."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        sub_events = [e for e in details.events if is_substitution_event(e)]

        for sub in sub_events:
            # Substitution should have at least one player name
            assert sub.player_name or sub.assist_name


class TestHalfEventDetection:
    """Test half-time and full-time event detection."""

    def test_is_half_event(self, sample_match_id):
        """Test half event detection function."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        for event in details.events:
            if event.type.lower() == "half":
                assert is_half_event(event)

    def test_normalize_half_type(self, sample_match_id):
        """Test half type normalization for deduplication."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        half_events = [e for e in details.events if is_half_event(e)]

        for event in half_events:
            normalized = normalize_half_type(event)
            assert normalized in ("HT", "FT")

    def test_half_events_at_expected_minutes(self, sample_match_id):
        """Test half events occur at expected minutes."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        half_events = [e for e in details.events if is_half_event(e)]

        for event in half_events:
            # HT typically around minute 45, FT around minute 90
            if event.half_type == "HT":
                assert 44 <= event.minute <= 50  # Allow for added time
            elif event.half_type == "FT":
                assert event.minute >= 90


class TestEventProgression:
    """Test event detection through match progression."""

    def test_events_appear_chronologically(self, sample_match_id):
        """Test events appear in chronological order as match progresses."""
        sim = load_test_match(sample_match_id)

        # Get events at minute 30
        early = sim.get_match_at_minute(30)
        early_event_count = len(early.events)

        # Get events at minute 60
        late = sim.get_match_at_minute(60)
        late_event_count = len(late.events)

        # Later time should have >= events
        assert late_event_count >= early_event_count

    def test_goal_count_matches_score(self, sample_match_id):
        """Test that goal events match the match score."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        # Count goal events (excluding own goals)
        home_goals = sum(
            1
            for e in details.events
            if e.type.lower() == "goal"
            and not e.own_goal
            and e.team_id == details.match.home_team.id
        )
        away_goals = sum(
            1
            for e in details.events
            if e.type.lower() == "goal"
            and not e.own_goal
            and e.team_id == details.match.away_team.id
        )

        # Add own goals (credited to opposite team)
        home_own_goals = sum(
            1
            for e in details.events
            if e.type.lower() == "goal"
            and e.own_goal
            and e.team_id == details.match.away_team.id
        )
        away_own_goals = sum(
            1
            for e in details.events
            if e.type.lower() == "goal"
            and e.own_goal
            and e.team_id == details.match.home_team.id
        )

        home_total = home_goals + home_own_goals
        away_total = away_goals + away_own_goals

        # Scores should match (unless match has penalty shootout as well)
        if not details.penalties:
            assert home_total == details.match.home_score
            assert away_total == details.match.away_score


class TestEventDeduplication:
    """Test event deduplication logic."""

    def test_event_ids_unique(self, sample_match_id):
        """Test that goal/card events have unique IDs."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        # Goal and card events should have unique IDs
        goal_card_events = [
            e
            for e in details.events
            if e.type.lower() in ("goal", "card") and e.id != 0
        ]

        if goal_card_events:
            event_ids = [e.id for e in goal_card_events]
            assert len(event_ids) == len(set(event_ids)), "Duplicate event IDs found"
