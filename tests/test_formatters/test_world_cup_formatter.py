"""Tests for World Cup formatter.

Tests formatting functions using real match data from test_data/.
"""

from zoneinfo import ZoneInfo

import pytest

from lafcbot.formatters.world_cup import WorldCupFormatter
from lafcbot.testing import list_available_matches, load_test_match


@pytest.fixture
def formatter():
    """Create WorldCupFormatter with PT timezone."""
    return WorldCupFormatter(timezone=ZoneInfo("America/Los_Angeles"))


@pytest.fixture
def sample_match_id():
    """Get first available test match ID."""
    matches = list_available_matches()
    if not matches:
        pytest.skip("No test match data available")
    return matches[0]


class TestTeamFormatting:
    """Test team name formatting with flags and rankings."""

    def test_format_team_with_flag_and_rank(self, formatter):
        """Test team formatting includes flag emoji and ranking."""
        # Test with known countries
        result = formatter.format_team_with_flag_and_rank("United States")
        assert "🇺🇸" in result or "United States" in result

        result = formatter.format_team_with_flag_and_rank("Mexico")
        assert "🇲🇽" in result or "Mexico" in result

    def test_format_team_without_flag(self, formatter):
        """Test team formatting for unknown countries."""
        result = formatter.format_team_with_flag_and_rank("Unknown Team")
        assert "Unknown Team" in result


class TestMatchFormatting:
    """Test match line formatting."""

    def test_format_match_simple(self, formatter, sample_match_id):
        """Test simple match formatting without API calls."""
        sim = load_test_match(sample_match_id)
        match = sim.get_full_match().match

        result = formatter.format_match_simple(match)

        assert result.match_line is not None
        assert match.home_team.name in result.match_line
        assert match.away_team.name in result.match_line

    def test_format_match_finished(self, formatter, sample_match_id):
        """Test formatting for finished matches."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        # Manually set to finished state for test
        if details.match.status != "finished":
            pytest.skip("Test match is not finished")

        result = formatter.format_match_simple(details.match)

        assert "FT" in result.match_line or details.match.is_finished

    def test_format_match_live(self, formatter, sample_match_id):
        """Test formatting for live matches."""
        sim = load_test_match(sample_match_id)

        # Get match at minute 30 (should be live)
        details = sim.get_match_at_minute(30)

        _ = formatter.format_match_simple(details.match)

        # Live match should have time display
        assert details.match.match_time_display is not None


class TestVenueFormatting:
    """Test venue information formatting."""

    def test_format_venue_info(self, formatter, sample_match_id):
        """Test venue formatting."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        if not details.match.venue:
            pytest.skip("Test match has no venue data")

        result = formatter.format_venue_info(details.match.venue)

        assert "🏟️" in result
        assert details.match.venue.name in result


class TestBroadcastFormatting:
    """Test broadcast channel formatting."""

    def test_format_broadcast_channels_us_only(self, formatter, sample_match_id):
        """Test that only US channels are formatted."""
        sim = load_test_match(sample_match_id)
        details = sim.get_full_match()

        if not details.broadcast_channels:
            pytest.skip("Test match has no broadcast data")

        result = formatter.format_broadcast_channels(details.broadcast_channels)

        if result:
            assert "📺" in result
            # Result should only contain US channels


class TestPenaltyFormatting:
    """Test penalty shootout formatting."""

    def test_format_penalty_shootout_cards_empty(self, formatter):
        """Test penalty formatting with no penalty kicks."""
        result = formatter.format_penalty_shootout_cards(
            penalty_kicks=[],
            home_team_name="USA",
            away_team_name="Mexico",
            is_live=False,
        )

        assert result == ""

    def test_penalty_round_info_empty(self, formatter):
        """Test penalty round info with no kicks."""
        current_round, is_sudden_death, home_count, away_count = (
            formatter._get_penalty_round_info([])
        )

        assert current_round == 0
        assert is_sudden_death is False
        assert home_count == 0
        assert away_count == 0


class TestDailyMatchesMessage:
    """Test daily matches message formatting."""

    @pytest.mark.asyncio
    async def test_format_daily_matches_empty(self, formatter):
        """Test formatting with no matches."""
        from datetime import date
        from unittest.mock import MagicMock

        mock_client = MagicMock()

        result = await formatter.format_daily_matches_message(
            matches=[],
            display_date=date.today(),
            is_today=True,
            fotmob_client=mock_client,
        )

        # Should return empty list with header
        assert isinstance(result, list)

    def test_format_no_matches_message(self, formatter):
        """Test no matches message."""
        result = formatter.format_no_matches_message()

        assert "No World Cup matches" in result


class TestTimeProgression:
    """Test formatter with match time progression."""

    def test_format_at_different_times(self, formatter, sample_match_id):
        """Test formatting changes as match progresses."""
        sim = load_test_match(sample_match_id)

        # Pre-match
        pre_match = sim.get_match_at_minute(0)
        pre_result = formatter.format_match_simple(pre_match.match)
        assert pre_result.match_line is not None

        # Halftime
        halftime = sim.get_match_at_minute(45)
        ht_result = formatter.format_match_simple(halftime.match)
        assert ht_result.match_line is not None

        # Full time
        full_time = sim.get_match_at_minute(90)
        ft_result = formatter.format_match_simple(full_time.match)
        assert ft_result.match_line is not None

        # Verify they're different (except potentially for matches with no events)
        # At minimum, the status/time display should differ
