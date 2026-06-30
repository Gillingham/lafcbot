"""Formatters for World Cup daily match notifications."""

from dataclasses import dataclass
from datetime import date

from lafcbot.formatters.base import BaseFormatter
from lafcbot.utils.countries import get_country_flag, get_country_rank


@dataclass
class FormattedMatch:
    """Container for formatted match lines."""

    match_line: str  # "🇺🇸 USA (#11) vs 🇲🇽 Mexico (#13) - Jun 19, 06:00 PM PT"
    venue_line: str | None  # "  🏟️ SoFi Stadium, Los Angeles"
    broadcast_line: str | None  # "  📺 FOX, Telemundo"

    def format(self) -> str:
        """
        Return as multi-line string with blank line separator.

        Returns:
            Formatted string with all lines and blank separator
        """
        lines = [self.match_line]
        if self.venue_line:
            lines.append(self.venue_line)
        if self.broadcast_line:
            lines.append(self.broadcast_line)
        lines.append("")  # Blank line between matches
        return "\n".join(lines)


class WorldCupFormatter(BaseFormatter):
    """Formats World Cup daily match notifications."""

    def _get_penalty_round_info(self, penalty_kicks):
        """
        Analyze penalty kicks to determine round information.

        Args:
            penalty_kicks: List of PenaltyKick objects

        Returns:
            Tuple of (current_round, is_sudden_death, home_kick_count, away_kick_count)
        """
        if not penalty_kicks:
            return 0, False, 0, 0

        home_kicks = [pk for pk in penalty_kicks if pk.is_home]
        away_kicks = [pk for pk in penalty_kicks if not pk.is_home]

        home_count = len(home_kicks)
        away_count = len(away_kicks)
        max_kicks_per_team = max(home_count, away_count)

        is_sudden_death = max_kicks_per_team > 5
        current_round = max_kicks_per_team

        return current_round, is_sudden_death, home_count, away_count

    def format_penalty_shootout_cards(
        self, penalty_kicks, home_team_name, away_team_name, is_live=False
    ):
        """
        Format penalty shootout as card-style visualization with emojis.

        Args:
            penalty_kicks: List of PenaltyKick objects
            home_team_name: Name of home team
            away_team_name: Name of away team
            is_live: If True, show blank squares for upcoming kicks in rounds 1-5

        Returns:
            Formatted string with penalty visualization (single line)
        """
        if not penalty_kicks:
            return ""

        from lafcbot.utils.countries import get_country_flag

        _, is_sudden_death, home_count, away_count = self._get_penalty_round_info(
            penalty_kicks
        )

        # Build kick lists for each team
        home_kicks_display = []
        away_kicks_display = []

        # Get actual kicks taken
        for pk in penalty_kicks:
            emoji = "🟩" if pk.scored else "🟥"

            if pk.is_home:
                home_kicks_display.append(emoji)
            else:
                away_kicks_display.append(emoji)

        # Add blank squares for upcoming kicks (only in rounds 1-5 if live)
        if is_live and not is_sudden_death:
            # Fill up to 5 kicks for each team
            for _ in range(home_count, 5):
                home_kicks_display.append("⬜")
            for _ in range(away_count, 5):
                away_kicks_display.append("⬜")

        # Get country flags
        home_flag = get_country_flag(home_team_name)
        away_flag = get_country_flag(away_team_name)

        # Build the single-line display
        home_part = " ".join(home_kicks_display)
        away_part = " ".join(away_kicks_display)

        home_display = f"{home_flag} {home_part}" if home_flag else home_part
        away_display = f"{away_flag} {away_part}" if away_flag else away_part

        return f"{home_display} | {away_display}"

    def format_team_with_flag_and_rank(self, team_name: str) -> str:
        """
        Format team name with flag emoji and world ranking.

        Args:
            team_name: Team name (e.g., "United States")

        Returns:
            Formatted string (e.g., "🇺🇸 United States (#11)")
        """
        flag = get_country_flag(team_name)
        rank = get_country_rank(team_name)

        if flag:
            rank_text = f" (#{rank})" if rank is not None else ""
            return f"{flag} {team_name}{rank_text}"
        return team_name

    def format_venue_info(self, venue) -> str:
        """
        Format venue information line.

        Args:
            venue: Venue object with name, city attributes

        Returns:
            Formatted string (e.g., "  🏟️ Venue Name, City")
        """
        venue_parts = [f"  🏟️ {venue.name}"]
        if venue.city:
            venue_parts.append(venue.city)
        return ", ".join(venue_parts)

    def format_broadcast_channels(self, channels: list) -> str | None:
        """
        Format US broadcast channels line.

        Args:
            channels: List of BroadcastChannel objects

        Returns:
            Formatted string (e.g., "  📺 FOX, Telemundo") or None if no US channels
        """
        us_channels = [
            ch.channel_name
            for ch in channels
            if ch.country_name and "USA" in ch.country_name.upper()
        ]
        if us_channels:
            return f"  📺 {', '.join(us_channels)}"
        return None

    def format_match_simple(self, match) -> FormattedMatch:
        """
        Format match with basic info only (no API calls).

        Args:
            match: Match object

        Returns:
            FormattedMatch with only match_line populated
        """
        home_name = match.home_team.name
        away_name = match.away_team.name

        home_display = self.format_team_with_flag_and_rank(home_name)
        away_display = self.format_team_with_flag_and_rank(away_name)

        # Format score or status
        if match.is_live:
            time_display = match.match_time_display or "LIVE"
            score_part = f"{match.home_score}-{match.away_score} ({time_display})"
            match_line = f"{home_display} vs {away_display} - {score_part}"
        elif match.is_finished:
            score_part = f"{match.home_score}-{match.away_score} (FT)"
            match_line = f"{home_display} vs {away_display} - {score_part}"
        elif match.start_time:
            match_time = match.start_time.astimezone(self.timezone)
            time_str = match_time.strftime("%b %d, %I:%M %p PT")
            match_line = f"{home_display} vs {away_display} - {time_str}"
        else:
            match_line = f"{home_display} vs {away_display}"

        return FormattedMatch(
            match_line=match_line, venue_line=None, broadcast_line=None
        )

    async def format_match_detailed(self, match, fotmob_client) -> FormattedMatch:
        """
        Format match with venue/broadcast info (makes async API call).

        Args:
            match: Match object
            fotmob_client: FotMob client for fetching details

        Returns:
            FormattedMatch with all lines populated
            (or None for venue/broadcast on error)
        """
        venue_info = None
        us_broadcast_channels = []
        details = None

        # Fetch detailed match info
        if match.page_slug:
            try:
                details = await fotmob_client.get_match_details(
                    page_slug=match.page_slug, force_refresh=True
                )
            except Exception:
                # Fall back to simple formatting on API error
                details = None
        elif match.id:
            # Try fetching by match_id if no page_slug available
            try:
                details = await fotmob_client.get_match_details_authenticated(
                    match_id=match.id
                )
                if details:
                    if details.match.venue:
                        venue_info = details.match.venue
                    if details.broadcast_channels:
                        us_broadcast_channels = [
                            ch.channel_name
                            for ch in details.broadcast_channels
                            if ch.country_name and "USA" in ch.country_name.upper()
                        ]
            except Exception:
                # Fall back to simple formatting on API error
                details = None

        # Use detailed match info if available (has more up-to-date status)
        match_to_display = details.match if details else match

        # Format match line
        home_name = match_to_display.home_team.name
        away_name = match_to_display.away_team.name

        home_display = self.format_team_with_flag_and_rank(home_name)
        away_display = self.format_team_with_flag_and_rank(away_name)

        # Format score or status
        if match_to_display.is_live:
            time_display = match_to_display.match_time_display or "LIVE"
            score_part = f"{match_to_display.home_score}-{match_to_display.away_score} ({time_display})"
            match_line = f"{home_display} vs {away_display} - {score_part}"
        elif match_to_display.is_finished:
            # Determine winner (check penalties first if scores are tied)
            home_won = False
            away_won = False
            penalty_card_line = None

            if details and details.penalties:
                # Match went to penalties - use "Pen" instead of "FT"
                score_part = (
                    f"{match_to_display.home_score}-{match_to_display.away_score} (Pen)"
                )

                # Check if we have detailed penalty kick data for card visualization
                if details.penalty_kicks:
                    # Use card visualization instead of text score
                    penalty_card_line = self.format_penalty_shootout_cards(
                        details.penalty_kicks, home_name, away_name, is_live=False
                    )
                else:
                    # Fallback to text format if no kick details
                    pen_score = (
                        f"{details.penalties.home_score}-{details.penalties.away_score}"
                    )
                    score_part += f" ({pen_score} pens)"

                home_won = details.penalties.home_score > details.penalties.away_score
                away_won = details.penalties.away_score > details.penalties.home_score
            else:
                # Regular time winner - use "FT"
                score_part = (
                    f"{match_to_display.home_score}-{match_to_display.away_score} (FT)"
                )
                home_won = match_to_display.home_score > match_to_display.away_score
                away_won = match_to_display.away_score > match_to_display.home_score

            # Bold the winner's name
            if home_won:
                home_display = f"**{home_display}**"
            elif away_won:
                away_display = f"**{away_display}**"

            match_line = f"{home_display} vs {away_display} - {score_part}"

            # Add penalty card line if available
            if penalty_card_line:
                match_line += f"\n{penalty_card_line}"
        elif match_to_display.start_time:
            match_time = match_to_display.start_time.astimezone(self.timezone)
            time_str = match_time.strftime("%b %d, %I:%M %p PT")
            match_line = f"{home_display} vs {away_display} - {time_str}"
        else:
            match_line = f"{home_display} vs {away_display}"

        # Format venue and broadcast lines (only for upcoming/live matches)
        venue_line = None
        broadcast_line = None
        if not match_to_display.is_finished:
            venue_line = self.format_venue_info(venue_info) if venue_info else None
            broadcast_line = (
                self.format_broadcast_channels(details.broadcast_channels)
                if details and us_broadcast_channels
                else None
            )

        return FormattedMatch(
            match_line=match_line,
            venue_line=venue_line,
            broadcast_line=broadcast_line,
        )

    async def format_daily_matches_message(
        self,
        matches: list,
        display_date: date,
        is_today: bool,
        fotmob_client,
        is_later_today: bool = False,
        is_now: bool = False,
    ) -> list[str]:
        """
        Format complete daily matches message (ready to send to Discord).

        Args:
            matches: List of Match objects to format
            display_date: Date being displayed
            is_today: Whether this is today's matches or future
            fotmob_client: FotMob client for fetching details
            is_later_today: Whether showing matches later today (changes header)
            is_now: Whether showing live matches now (changes header)

        Returns:
            List of formatted message strings (split at 2000 char boundaries if needed)
        """
        # Build header
        if is_now:
            date_header = "Matches Happening Now"
        elif is_later_today:
            date_header = "Matches Later Today"
        elif is_today:
            date_header = "Today's Matches"
        else:
            date_str = display_date.strftime("%A, %b %d")
            date_header = f"Next Matches - {date_str}"

        lines = [f"**{date_header}:**"]

        # Format all matches with detailed info
        for match in matches:
            formatted = await self.format_match_detailed(match, fotmob_client)
            lines.append(formatted.match_line)
            if formatted.venue_line:
                lines.append(formatted.venue_line)
            if formatted.broadcast_line:
                lines.append(formatted.broadcast_line)
            # Add blank line between matches
            lines.append("")

        response = "\n".join(lines)
        return self.split_for_discord(response)

    def format_no_matches_message(self) -> str:
        """
        Format message when no matches are scheduled.

        Returns:
            No matches message
        """
        return "No World Cup matches scheduled."
