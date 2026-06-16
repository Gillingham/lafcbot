"""Formatters for sports scores (ESPN API)."""

from lafcbot.formatters.base import BaseFormatter


class SportsFormatter(BaseFormatter):
    """Formats sports scores from ESPN."""

    def format_game_score(
        self,
        home_team: str,
        away_team: str,
        home_score: int,
        away_score: int,
        status: str,
    ) -> str:
        """
        Format a single game score line.

        Args:
            home_team: Home team name
            away_team: Away team name
            home_score: Home team score
            away_score: Away team score
            status: Game status (e.g., "Final", "3rd Qtr", "Top 5th")

        Returns:
            Formatted game line
        """
        score_display = f"{home_score}-{away_score}"
        return f"{away_team} @ {home_team} - {score_display} ({status})"

    async def format_league_scores(
        self,
        league: str,
        games: list[dict],
    ) -> str:
        """
        Format !scores command output for any league as a single line.

        Args:
            league: League name (NBA, MLB, NHL, NFL, F1)
            games: List of game dictionaries with team and score info

        Returns:
            Formatted scores string (single line)
        """
        if not games:
            return f"No {league.upper()} games today."

        game_strings = []
        for game in games:
            home_team = game.get("home_team", "Unknown")
            away_team = game.get("away_team", "Unknown")
            home_score = game.get("home_score", 0)
            away_score = game.get("away_score", 0)
            status = game.get("status", "Unknown")

            # Check if this is a scheduled game (status looks like a date/time)
            if any(
                keyword in status
                for keyword in [
                    "Mon",
                    "Tue",
                    "Wed",
                    "Thu",
                    "Fri",
                    "Sat",
                    "Sun",
                    "AM",
                    "PM",
                ]
            ):
                # Scheduled game: Away @ Home (time)
                game_str = f"{away_team} @ {home_team} ({status})"
            else:
                # In-progress or final game: Away score @ Home score status
                game_str = (
                    f"{away_team} {away_score} @ {home_team} {home_score} {status}"
                )

            game_strings.append(game_str)

        output = f"{league}: {' | '.join(game_strings)}"
        return self.truncate_for_discord(output)

    def format_dodgers_game_result(
        self,
        opponent: str,
        dodgers_score: int,
        opponent_score: int,
        is_win: bool,
        is_home: bool,
    ) -> str:
        """
        Format Dodgers game notification for pandaping.

        Args:
            opponent: Opponent team name
            dodgers_score: Dodgers score
            opponent_score: Opponent score
            is_win: Whether Dodgers won
            is_home: Whether it was a home game

        Returns:
            Formatted game result message
        """
        result = "won" if is_win else "lost"
        location = "home" if is_home else "away"

        if is_home:
            game_display = f"Dodgers {dodgers_score}, {opponent} {opponent_score}"
        else:
            game_display = f"{opponent} {opponent_score}, Dodgers {dodgers_score}"

        return f"The Dodgers {result} their {location} game: {game_display}"
