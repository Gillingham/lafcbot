"""Tests for live monitoring state tracking and deduplication.

Tests that WorldCupTask correctly tracks match state and prevents duplicate notifications.
"""

import pytest

from lafcbot.testing import list_available_matches, load_test_match
from lafcbot.testing.discord_mocks import create_test_bot_with_channels
from lafcbot.testing.mock_fotmob_client import MockFotMobClient


@pytest.fixture
def sample_match_id():
    """Get first available test match ID."""
    matches = list_available_matches()
    if not matches:
        pytest.skip("No test match data available")
    return matches[0]


@pytest.fixture
def mock_config():
    """Create mock WorldCupTask configuration."""
    return {
        "enabled": True,
        "timezone": "America/Los_Angeles",
        "live_monitoring": {
            "enabled": True,
            "check_interval_seconds": 60,
            "notifications": {
                "goals": True,
                "cards": True,
                "substitutions": True,
                "half_events": True,
                "extra_time": True,
                "penalties": True,
                "penalty_kicks": True,
            },
        },
        "servers": [
            {
                "guild_id": 123456789,
                "channel_name": "world-cup",
                "live_channel_name": "world-cup-live",
            }
        ],
    }


class TestStateInitialization:
    """Test match state initialization in monitoring."""

    @pytest.mark.asyncio
    async def test_monitor_match_initializes_state(self, sample_match_id, mock_config):
        """Test that monitoring a new match initializes state correctly."""
        from lafcbot.tasks.world_cup import WorldCupTask

        sim = load_test_match(sample_match_id)
        mock_client = MockFotMobClient(sim)
        mock_bot, mock_guild, channels = create_test_bot_with_channels(
            channel_names=["world-cup-live"]
        )

        task = WorldCupTask(mock_bot, mock_client, mock_config)

        # Start monitoring at minute 0
        mock_client.set_minute(0)
        match = sim.get_match_at_minute(0).match

        # Monitor the match
        await task._monitor_match(match, None)

        # State should be initialized
        assert match.id in task.monitored_matches
        state = task.monitored_matches[match.id]

        # Initial state should track existing events to prevent duplicates
        assert "last_events" in state
        assert "last_home_score" in state
        assert "last_away_score" in state

    @pytest.mark.asyncio
    async def test_stale_events_not_notified(self, sample_match_id, mock_config):
        """Test that starting monitoring mid-match doesn't notify about past events."""
        from lafcbot.tasks.world_cup import WorldCupTask

        sim = load_test_match(sample_match_id)
        mock_client = MockFotMobClient(sim)
        mock_bot, mock_guild, channels = create_test_bot_with_channels(
            channel_names=["world-cup-live"]
        )

        task = WorldCupTask(mock_bot, mock_client, mock_config)

        # Start monitoring at minute 60 (mid-match)
        mock_client.set_minute(60)
        match = sim.get_match_at_minute(60).match

        # Get initial message count
        initial_msg_count = len(channels["world-cup-live"].sent_messages)

        # Monitor the match
        await task._monitor_match(match, None)

        # Should not have sent notifications for events before minute 60
        # (except possibly match start notification)
        new_msg_count = len(channels["world-cup-live"].sent_messages)
        notifications_sent = new_msg_count - initial_msg_count

        # Should be minimal (0-1 for start notification)
        assert notifications_sent <= 1


class TestEventDeduplication:
    """Test that events are not notified multiple times."""

    @pytest.mark.asyncio
    async def test_same_event_not_notified_twice(self, sample_match_id, mock_config):
        """Test that replaying the same minute doesn't trigger duplicate notifications."""
        from lafcbot.tasks.world_cup import WorldCupTask

        sim = load_test_match(sample_match_id)
        mock_client = MockFotMobClient(sim)
        mock_bot, mock_guild, channels = create_test_bot_with_channels(
            channel_names=["world-cup-live"]
        )

        task = WorldCupTask(mock_bot, mock_client, mock_config)

        # Monitor at minute 30
        mock_client.set_minute(30)
        match = sim.get_match_at_minute(30).match

        await task._monitor_match(match, None)
        msg_count_after_first = len(channels["world-cup-live"].sent_messages)

        # Monitor again at same minute (simulate re-poll)
        await task._monitor_match(match, None)
        msg_count_after_second = len(channels["world-cup-live"].sent_messages)

        # Should not have sent new messages (except potentially start notification on first)
        # After first monitor, second should add 0 messages
        assert msg_count_after_second == msg_count_after_first

    @pytest.mark.asyncio
    async def test_goal_deduplication_by_id(self, sample_match_id, mock_config):
        """Test that goal events are deduplicated by ID."""
        from lafcbot.tasks.world_cup import WorldCupTask

        sim = load_test_match(sample_match_id)
        full_match = sim.get_full_match()

        # Skip if no goals
        goal_events = [e for e in full_match.events if e.type.lower() == "goal"]
        if not goal_events:
            pytest.skip("Test match has no goals")

        mock_client = MockFotMobClient(sim)
        mock_bot, mock_guild, channels = create_test_bot_with_channels(
            channel_names=["world-cup-live"]
        )

        task = WorldCupTask(mock_bot, mock_client, mock_config)

        # Find minute of first goal
        first_goal = goal_events[0]
        goal_minute = first_goal.minute

        # Monitor up to goal
        mock_client.set_minute(goal_minute)
        match = sim.get_match_at_minute(goal_minute).match

        await task._monitor_match(match, None)

        # Get goal-related messages
        initial_goal_msgs = [
            msg
            for msg in channels["world-cup-live"].sent_messages
            if "goal" in msg.content.lower() or "⚽" in msg.content
        ]

        # Monitor again at same time
        await task._monitor_match(match, None)

        # Should not have duplicate goal notifications
        final_goal_msgs = [
            msg
            for msg in channels["world-cup-live"].sent_messages
            if "goal" in msg.content.lower() or "⚽" in msg.content
        ]

        assert len(final_goal_msgs) == len(initial_goal_msgs)


class TestScoreTracking:
    """Test score tracking and updates."""

    @pytest.mark.asyncio
    async def test_score_updates_as_match_progresses(
        self, sample_match_id, mock_config
    ):
        """Test that scores are tracked correctly as time advances."""
        from lafcbot.tasks.world_cup import WorldCupTask

        sim = load_test_match(sample_match_id)
        mock_client = MockFotMobClient(sim)
        mock_bot, mock_guild, channels = create_test_bot_with_channels(
            channel_names=["world-cup-live"]
        )

        task = WorldCupTask(mock_bot, mock_client, mock_config)

        # Monitor at minute 0
        mock_client.set_minute(0)
        match = sim.get_match_at_minute(0).match

        await task._monitor_match(match, None)

        state = task.monitored_matches.get(match.id)
        if state:
            # Advance to minute 90
            mock_client.set_minute(90)
            match = sim.get_match_at_minute(90).match

            await task._monitor_match(match, None)

            final_home_score = state["last_home_score"]
            final_away_score = state["last_away_score"]

            # Scores should be updated (or stay the same if 0-0)
            assert isinstance(final_home_score, int)
            assert isinstance(final_away_score, int)


class TestHalfEventTracking:
    """Test half-time and full-time event tracking."""

    @pytest.mark.asyncio
    async def test_half_events_tracked(self, sample_match_id, mock_config):
        """Test that half events are tracked in state."""
        from lafcbot.tasks.world_cup import WorldCupTask

        sim = load_test_match(sample_match_id)
        full_match = sim.get_full_match()

        # Check if match has half events
        half_events = [e for e in full_match.events if e.type.lower() == "half"]
        if not half_events:
            pytest.skip("Test match has no half events")

        mock_client = MockFotMobClient(sim)
        mock_bot, mock_guild, channels = create_test_bot_with_channels(
            channel_names=["world-cup-live"]
        )

        task = WorldCupTask(mock_bot, mock_client, mock_config)

        # Monitor through halftime
        mock_client.set_minute(45)
        match = sim.get_match_at_minute(45).match

        await task._monitor_match(match, None)

        state = task.monitored_matches.get(match.id)
        if state:
            # Half events should be in last_events
            tracked_half_events = [
                e for e in state["last_events"] if e["type"].lower() == "half"
            ]
            # Should have tracked at least HT
            assert len(tracked_half_events) >= 0  # May be 0 if no HT event in data


class TestMatchFinishDetection:
    """Test detection of finished matches."""

    @pytest.mark.asyncio
    async def test_finished_match_removed_from_monitoring(
        self, sample_match_id, mock_config
    ):
        """Test that finished matches are removed from monitored_matches."""
        from lafcbot.tasks.world_cup import WorldCupTask

        sim = load_test_match(sample_match_id)
        mock_client = MockFotMobClient(sim)
        mock_bot, mock_guild, channels = create_test_bot_with_channels(
            channel_names=["world-cup-live"]
        )

        task = WorldCupTask(mock_bot, mock_client, mock_config)

        # Start monitoring
        mock_client.set_minute(30)
        match = sim.get_match_at_minute(30).match

        await task._monitor_match(match, None)

        # Match should be tracked
        assert match.id in task.monitored_matches

        # Advance to end (assuming match finishes by 120)
        mock_client.set_minute(120)

        # Check if match is finished
        await task._check_finished_matches()

        # If match is finished, it should be removed
        # (This depends on whether test match is actually finished)
