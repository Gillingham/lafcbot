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
                    page_slug=match.page_slug
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

        # Format match line
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

        # Format venue and broadcast lines
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
