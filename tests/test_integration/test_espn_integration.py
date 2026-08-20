"""Integration tests that call the real ESPN API.

These tests verify that our code works with actual ESPN API responses
and will catch any breaking changes to the API.
"""

import pytest

from lafcbot.clients.espn_client import ESPNClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_espn_nba_scoreboard():
    """Test fetching NBA scoreboard from ESPN API."""
    async with ESPNClient() as client:
        league_name, games = await client.get_scoreboard("nba")

        assert league_name is not None, "Should get league name"
        assert league_name == "National Basketball Association"
        assert games is not None, "Should get games list"
        print(f"\n✓ Fetched NBA scoreboard: {league_name} with {len(games)} game(s)")

        if games:
            game = games[0]
            assert game.game_id
            assert game.away_team
            assert game.home_team
            assert game.status
            print(f"✓ Sample game: {game.away_team} @ {game.home_team} - {game.status}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_espn_wnba_scoreboard():
    """Test fetching WNBA scoreboard from ESPN API."""
    async with ESPNClient() as client:
        league_name, games = await client.get_scoreboard("wnba")

        assert league_name is not None, "Should get league name"
        assert "Women's National Basketball Association" in league_name
        assert games is not None, "Should get games list"
        print(f"\n✓ Fetched WNBA scoreboard: {league_name} with {len(games)} game(s)")

        if games:
            game = games[0]
            assert game.game_id
            assert game.away_team
            assert game.home_team
            assert game.status
            print(f"✓ Sample game: {game.away_team} @ {game.home_team} - {game.status}")

            if game.is_scheduled and game.scheduled_time:
                print(f"✓ Scheduled game time: {game.scheduled_time}")
            else:
                assert game.away_score is not None
                assert game.home_score is not None
                print(f"✓ Live/Final game score: {game.away_score} - {game.home_score}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_espn_mlb_scoreboard():
    """Test fetching MLB scoreboard from ESPN API."""
    async with ESPNClient() as client:
        league_name, games = await client.get_scoreboard("mlb")

        assert league_name is not None, "Should get league name"
        assert league_name == "Major League Baseball"
        assert games is not None, "Should get games list"
        print(f"\n✓ Fetched MLB scoreboard: {league_name} with {len(games)} game(s)")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_espn_nhl_scoreboard():
    """Test fetching NHL scoreboard from ESPN API."""
    async with ESPNClient() as client:
        league_name, games = await client.get_scoreboard("nhl")

        assert league_name is not None, "Should get league name"
        assert league_name == "National Hockey League"
        assert games is not None, "Should get games list"
        print(f"\n✓ Fetched NHL scoreboard: {league_name} with {len(games)} game(s)")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_espn_nfl_scoreboard():
    """Test fetching NFL scoreboard from ESPN API."""
    async with ESPNClient() as client:
        league_name, games = await client.get_scoreboard("nfl")

        assert league_name is not None, "Should get league name"
        assert league_name == "National Football League"
        assert games is not None, "Should get games list"
        print(f"\n✓ Fetched NFL scoreboard: {league_name} with {len(games)} game(s)")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_espn_f1_scoreboard():
    """Test fetching F1 scoreboard from ESPN API."""
    async with ESPNClient() as client:
        league_name, games = await client.get_scoreboard("f1")

        assert league_name is not None, "Should get league name"
        assert "Formula 1" in league_name
        assert games is not None, "Should get games list"
        print(f"\n✓ Fetched F1 scoreboard: {league_name} with {len(games)} game(s)")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_espn_all_sports():
    """Test that all configured sports can be fetched without errors."""
    async with ESPNClient() as client:
        results = {}
        for sport in ESPNClient.SPORT_PATHS.keys():
            league_name, games = await client.get_scoreboard(sport)
            results[sport] = (league_name, len(games))
            print(
                f"\n✓ {sport.upper()}: {league_name} - {len(games)} game(s) scheduled"
            )

        print("\n✓ All sports successfully fetched from ESPN API!")
        for sport, (league_name, count) in results.items():
            assert league_name is not None, f"{sport} should return a league name"
            print(f"  {sport.upper()}: {league_name} ({count} games)")
