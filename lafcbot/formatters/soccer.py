"""Formatters for soccer cog commands."""

from datetime import date
from functools import cache

from lafcbot.formatters.base import BaseFormatter

# Team name overrides by league - maps full names to shortened versions
TEAM_NAME_OVERRIDES = {
    "mls": {
        "Inter Miami CF": "Inter Miami",
        "LA Galaxy": "Galaxy",
    },
}


class SoccerFormatter(BaseFormatter):
    """Formats soccer command responses."""

    @staticmethod
    @cache
    def clean_team_name(name: str, league_key: str) -> str:
        """Remove unnecessary suffixes from team names based on league context."""
        # Check for league-specific team name overrides
        if league_key in TEAM_NAME_OVERRIDES:
            if name in TEAM_NAME_OVERRIDES[league_key]:
                return TEAM_NAME_OVERRIDES[league_key][name]

        # Remove suffix patterns
        if league_key == "nwsl" and name.endswith(" (W)"):
            return name[:-4]

        return name

    def _shorten_team_name(self, team_name: str, league_key: str) -> str:
        """
        Shorten team name based on league-specific overrides.

        Args:
            team_name: Full team name
            league_key: League key (e.g., "mls")

        Returns:
            Shortened team name or original if no override
        """
        overrides = TEAM_NAME_OVERRIDES.get(league_key.lower(), {})
        return overrides.get(team_name, team_name)

    def format_match_line(
        self,
        match,
        league_key: str,
        show_date: bool = False,
        show_league: bool = False,
    ) -> str:
        """
        Format a single match line.

        Args:
            match: Match object
            league_key: League key for team name overrides
            show_date: Whether to include date in output
            show_league: Whether to include league name

        Returns:
            Formatted match line string
        """
        home_name = self.clean_team_name(match.home_team.name, league_key)
        away_name = self.clean_team_name(match.away_team.name, league_key)

        # Format score or status
        if match.is_live:
            time_display = match.match_time_display or "LIVE"
            score_part = f"{match.home_score}-{match.away_score} ({time_display})"
        elif match.is_finished:
            score_part = f"{match.home_score}-{match.away_score} (FT)"
        elif match.start_time:
            match_time = match.start_time.astimezone(self.timezone)
            if show_date:
                time_str = match_time.strftime("%b %d, %I:%M %p PT")
            else:
                time_str = match_time.strftime("%I:%M %p PT")
            score_part = time_str
        else:
            score_part = "TBD"

        # Build match line
        match_line = f"{home_name} vs {away_name} - {score_part}"

        # Add league if requested
        if show_league and match.league_name:
            match_line = f"[{match.league_name}] {match_line}"

        return match_line

    async def format_matches_list(
        self,
        matches: list,
        league_name: str,
        target_date: date,
        is_today: bool,
        is_tomorrow: bool,
        league_key: str,
    ) -> str:
        """
        Format !matches command output.

        Args:
            matches: List of Match objects
            league_name: Display name of league
            target_date: Date being displayed
            is_today: Whether showing today's matches
            is_tomorrow: Whether showing tomorrow's matches
            league_key: League key for team name overrides

        Returns:
            Formatted matches list string
        """
        # Build header
        if is_today:
            header = f"**{league_name} - Today's Matches:**"
        elif is_tomorrow:
            header = f"**{league_name} - Tomorrow's Matches:**"
        else:
            date_str = target_date.strftime("%A, %B %d")
            header = f"**{league_name} - {date_str}:**"

        lines = [header]

        if not matches:
            lines.append("No matches scheduled.")
            return "\n".join(lines)

        # Format each match
        for match in matches:
            match_line = self.format_match_line(
                match, league_key, show_date=False, show_league=False
            )
            lines.append(match_line)

        response = "\n".join(lines)
        return self.truncate_for_discord(response)

    async def format_standings_table(
        self,
        standings_data: list,
        league_name: str,
        league_key: str,
    ) -> str:
        """
        Format !standings command output with table.

        Args:
            standings_data: List of team standings dictionaries
            league_name: Display name of league
            league_key: League key for team name overrides

        Returns:
            Formatted standings table string
        """
        if not standings_data:
            return f"No standings available for {league_name}."

        lines = [f"**{league_name} Standings:**", "```"]

        # Fixed team width (matches original)
        TEAM_WIDTH = 13

        def fmt_team_name(name: str, max_len: int = TEAM_WIDTH) -> str:
            """Clean, strip, collapse spaces, and truncate team names."""
            name = " ".join(str(name).strip().split())  # Collapse multi-spaces
            if len(name) > max_len:
                return name[: max_len - 1] + "…"  # Truncate with ellipsis
            return name

        # Calculate maximum width needed for each numeric column from actual data
        max_p = max(
            (len(str(team.get("played", 0))) for team in standings_data), default=1
        )
        max_w = max(
            (len(str(team.get("wins", 0))) for team in standings_data), default=1
        )
        max_d = max(
            (len(str(team.get("draws", 0))) for team in standings_data), default=1
        )
        max_l = max(
            (len(str(team.get("losses", 0))) for team in standings_data), default=1
        )
        max_gd = max(
            (len(str(team.get("goal_diff", 0))) for team in standings_data), default=2
        )
        max_pts = max(
            (len(str(team.get("points", 0))) for team in standings_data), default=3
        )

        # Ensure minimum widths for column headers
        w_p = max(max_p, 1)
        w_w = max(max_w, 1)
        w_d = max(max_d, 1)
        w_l = max(max_l, 1)
        w_gd = max(max_gd, 2)
        w_pts = max(max_pts, 3)

        # Header with dynamic widths
        lines.append(
            f"{'#':<3}{'Team':<{TEAM_WIDTH}} {'P':>{w_p}} {'W':>{w_w}} {'D':>{w_d}} {'L':>{w_l}} {'GD':>{w_gd}} {'Pts':>{w_pts}}"
        )

        # Separator with + at column boundaries
        boundary_positions = [
            3 + TEAM_WIDTH,  # After Team
            3 + TEAM_WIDTH + 1 + w_p,  # Before W
            3 + TEAM_WIDTH + 1 + w_p + 1 + w_w,  # Before D
            3 + TEAM_WIDTH + 1 + w_p + 1 + w_w + 1 + w_d,  # Before L
            3 + TEAM_WIDTH + 1 + w_p + 1 + w_w + 1 + w_d + 1 + w_l,  # Before GD
            3
            + TEAM_WIDTH
            + 1
            + w_p
            + 1
            + w_w
            + 1
            + w_d
            + 1
            + w_l
            + 1
            + w_gd,  # Before Pts
        ]
        sep_length = (
            3
            + TEAM_WIDTH
            + 1
            + w_p
            + 1
            + w_w
            + 1
            + w_d
            + 1
            + w_l
            + 1
            + w_gd
            + 1
            + w_pts
        )
        sep = "".join(
            "+" if i in boundary_positions else "-" for i in range(sep_length)
        )
        lines.append(sep)

        # Team rows
        for team in standings_data:
            rank = team.get("rank", 0)
            name = team.get("name", "Unknown")
            name = self.clean_team_name(
                name, league_key
            )  # Apply overrides & suffix removal
            name = fmt_team_name(name)  # Collapse spaces & truncate

            played = team.get("played", 0)
            wins = team.get("wins", 0)
            draws = team.get("draws", 0)
            losses = team.get("losses", 0)
            gd_val = team.get("goal_diff", 0)
            # Format goal diff with + for positive values
            gd = f"+{gd_val}" if gd_val > 0 else str(gd_val)
            pts = team.get("points", 0)

            # Format line with dynamic widths (match original f-string alignment)
            line = f"{rank:<3}{name:<{TEAM_WIDTH}} {played:>{w_p}} {wins:>{w_w}} {draws:>{w_d}} {losses:>{w_l}} {gd:>{w_gd}} {pts:>{w_pts}}"
            lines.append(line)

        lines.append("```")
        response = "\n".join(lines)
        return self.truncate_for_discord(response)

    async def format_match_details(
        self,
        match_details,
        league_key: str,
    ) -> str:
        """
        Format !match command output with goals and highlights.

        Args:
            match_details: MatchDetails object
            league_key: League key for team name overrides

        Returns:
            Formatted match details string
        """
        match = match_details.match
        home_name = self.clean_team_name(match.home_team.name, league_key)
        away_name = self.clean_team_name(match.away_team.name, league_key)

        lines = [f"**{home_name} vs {away_name}**"]

        # Score and status
        if match.is_finished:
            lines.append(f"Final Score: {match.home_score}-{match.away_score}")
        elif match.is_live:
            time_display = match.match_time_display or "LIVE"
            score_display = f"{match.home_score}-{match.away_score}"
            lines.append(f"Score: {score_display} ({time_display})")
        else:
            if match.start_time:
                match_time = match.start_time.astimezone(self.timezone)
                time_str = match_time.strftime("%b %d, %I:%M %p PT")
                lines.append(f"Kickoff: {time_str}")

        # Venue
        if match.venue:
            venue_str = match.venue.name
            if match.venue.city:
                venue_str += f", {match.venue.city}"
            lines.append(f"Venue: {venue_str}")

        # Goals
        goal_events = [e for e in match_details.events if e.type.lower() == "goal"]
        if goal_events:
            lines.append("\n**Goals:**")
            for goal in goal_events:
                if not goal.added_time:
                    minute_str = f"{goal.minute}'"
                else:
                    minute_str = f"{goal.minute}+{goal.added_time}'"
                goal_line = f"{minute_str} - {goal.player_name or 'Unknown'}"
                if goal.own_goal:
                    goal_line += " (OG)"
                elif goal.assist_name:
                    goal_line += f" ({goal.assist_name})"
                lines.append(goal_line)

        response = "\n".join(lines)
        return self.truncate_for_discord(response)

    async def format_player_stats(
        self,
        stats_data: list,
        stat_type: str,
        league_name: str,
    ) -> str:
        """
        Format !stats command output (goals/assists).

        Args:
            stats_data: List of player stat dictionaries
            stat_type: "goals" or "assists"
            league_name: Display name of league

        Returns:
            Formatted player stats string
        """
        if not stats_data:
            return f"No {stat_type} stats available for {league_name}."

        stat_label = stat_type.capitalize()
        lines = [f"**{league_name} - Top {stat_label}:**", "```"]

        # Determine column widths
        max_player_len = max(len(p.get("player_name", "")) for p in stats_data)
        max_team_len = max(len(p.get("team_name", "")) for p in stats_data)
        player_width = min(max_player_len + 2, 25)
        team_width = min(max_team_len + 2, 25)

        # Header
        header = self.format_table_row(
            ["#", "Player", "Team", stat_label],
            [3, player_width, team_width, 6],
        )
        lines.append(header)
        lines.append("-" * len(header))

        # Player rows
        for i, player in enumerate(stats_data, 1):
            rank = str(i)
            name = player.get("player_name", "Unknown")
            team = player.get("team_name", "Unknown")
            stat_val = str(player.get(stat_type, 0))

            row = self.format_table_row(
                [rank, name, team, stat_val],
                [3, player_width, team_width, 6],
            )
            lines.append(row)

        lines.append("```")
        response = "\n".join(lines)
        return self.truncate_for_discord(response)
