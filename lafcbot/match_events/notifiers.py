"""Match event notification handling for Discord."""

import logging
from datetime import datetime, timedelta

from lafcbot.match_events.detectors import (
    get_card_color,
    get_var_cancellation_reason,
    is_penalty_goal,
)
from lafcbot.match_events.formatters import (
    format_cancelled_goal_notification,
    format_minute,
)
from lafcbot.utils.countries import get_country_flag
from lafcbot.utils.discord_helpers import send_to_guild_channels

logger = logging.getLogger(__name__)


class MatchNotifier:
    """Handles Discord notifications for match events."""

    def __init__(self, bot, config, timezone, server_configs=None):
        """
        Initialize the match notifier.

        Args:
            bot: Discord bot instance
            config: Configuration dict with channel names
            timezone: ZoneInfo timezone for time formatting
            server_configs: Optional list of server configurations for multi-server support
        """
        self.bot = bot
        self.config = config
        self.timezone = timezone
        self.server_configs = server_configs or []

    def _format_team_display(self, team_name: str) -> str:
        """
        Format team display with flag if available, otherwise just team name.

        Args:
            team_name: Name of the team

        Returns:
            Formatted string with flag and name, or just name
        """
        flag = get_country_flag(team_name)
        return f"{flag} {team_name}" if flag else team_name

    def _get_team_displays(self, match) -> tuple[str, str]:
        """
        Get formatted display strings for both teams.

        Args:
            match: Match object with home_team and away_team

        Returns:
            Tuple of (home_display, away_display)
        """
        home_display = self._format_team_display(match.home_team.name)
        # Keep flag on the right side for away team
        flag = get_country_flag(match.away_team.name)
        if flag:
            away_display = f"{match.away_team.name} {flag}"
        else:
            away_display = match.away_team.name
        return home_display, away_display

    def _get_scores(self, match) -> tuple[int, int]:
        """
        Get scores from match with 0 defaults.

        Args:
            match: Match object

        Returns:
            Tuple of (home_goals, away_goals)
        """
        return match.home_score or 0, match.away_score or 0

    def _get_live_channels(self) -> list[tuple[str, str]]:
        """
        Get list of (guild_id, channel_name) tuples for live monitoring channels.

        Returns:
            List of (guild_id, channel_name) tuples
        """
        channels = []
        for server_config in self.server_configs:
            guild_id = server_config.get("guild_id")
            live_name = server_config.get("live_channel_name")

            if guild_id and live_name:
                channels.append((guild_id, live_name))

        return channels

    def _format_lineup(self, team_lineup: dict, team_name: str) -> str:
        """
        Format a team's starting lineup and bench for display.

        Args:
            team_lineup: Dictionary with 'starters', 'subs', and 'formation' keys
            team_name: Name of the team

        Returns:
            Formatted string with formation, starters, and bench, or empty string if data missing
        """
        if not team_lineup:
            return ""

        # Position ID mapping (usualPlayingPositionId)
        position_map = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD"}

        formation = team_lineup.get("formation", "Unknown")
        starters = team_lineup.get("starters", [])
        subs = team_lineup.get("subs", [])

        if not starters:
            return ""

        # Format starters: "Name (POS)"
        starter_names = []
        for starter in starters[:11]:
            name = starter.get("name", "Unknown")
            pos_id = starter.get("usualPlayingPositionId", 0)
            pos = position_map.get(pos_id, "")
            starter_names.append(f"{name} ({pos})" if pos else name)

        # Format bench: "Name (POS)"
        bench_names = []
        for sub in subs:
            name = sub.get("name", "Unknown")
            pos_id = sub.get("usualPlayingPositionId", 0)
            pos = position_map.get(pos_id, "")
            bench_names.append(f"{name} ({pos})" if pos else name)

        result = f"**{team_name} ({formation}):**\n"
        result += "Starters: " + ", ".join(starter_names)
        if bench_names:
            result += "\nBench: " + ", ".join(bench_names)

        return result

    def _get_event_team_display(
        self,
        event,
        match,
        home_team: str,
        away_team: str,
        home_flag: str,
        away_flag: str,
    ) -> str:
        """
        Get formatted team display for an event.

        Args:
            event: Event object with team_id
            match: Match object
            home_team: Home team name
            away_team: Away team name
            home_flag: Home team flag emoji
            away_flag: Away team flag emoji

        Returns:
            Formatted team display string
        """
        is_home = event.team_id == match.home_team.id
        team_name = home_team if is_home else away_team
        team_flag = home_flag if is_home else away_flag
        return f"{team_flag} {team_name}" if team_flag else team_name

    def _format_goal_list(
        self,
        details,
        match,
        home_team: str,
        away_team: str,
        home_flag: str,
        away_flag: str,
    ) -> str:
        """
        Format goal events into a list string, ordered chronologically from earliest to latest.

        Args:
            details: MatchDetails object with events
            match: Match object
            home_team: Home team name
            away_team: Away team name
            home_flag: Home team flag emoji
            away_flag: Away team flag emoji

        Returns:
            Formatted goal list string, or empty string if no goals
        """
        goal_events = [e for e in details.events if e.type.lower() == "goal"]
        if not goal_events:
            return ""

        # Sort goals chronologically (earliest first)
        goal_events_sorted = sorted(
            goal_events, key=lambda e: (e.minute or 0, e.added_time or 0)
        )

        lines = ["**⚽ Goals:**"]
        for goal in goal_events_sorted:
            scorer = goal.player_name or "Unknown"
            minute_display = format_minute(goal)

            scoring_flag = (
                home_flag if goal.team_id == match.home_team.id else away_flag
            )
            scoring_team = (
                home_team if goal.team_id == match.home_team.id else away_team
            )

            goal_line = f"{minute_display} - "
            if scoring_flag:
                goal_line += f"{scoring_flag} {scorer}"
            else:
                goal_line += f"{scorer} ({scoring_team})"

            if goal.own_goal:
                goal_line += " (OG)"
            elif goal.assist_name:
                goal_line += f" ({goal.assist_name})"

            lines.append(goal_line)

        return "\n".join(lines)

    def _format_card_list(
        self,
        details,
        match,
        home_team: str,
        away_team: str,
        home_flag: str,
        away_flag: str,
    ) -> str:
        """
        Format card events into a list string, ordered chronologically from earliest to latest.

        Args:
            details: MatchDetails object with events
            match: Match object
            home_team: Home team name
            away_team: Away team name
            home_flag: Home team flag emoji
            away_flag: Away team flag emoji

        Returns:
            Formatted card list string, or empty string if no cards
        """
        from lafcbot.match_events.detectors import is_card_event

        card_events = [e for e in details.events if is_card_event(e)]
        if not card_events:
            return ""

        # Sort cards chronologically (earliest first)
        card_events_sorted = sorted(
            card_events, key=lambda e: (e.minute or 0, e.added_time or 0)
        )

        lines = ["**Cards:**"]
        for card in card_events_sorted:
            player = card.player_name or "Unknown"
            minute_display = format_minute(card)

            card_color = get_card_color(card)
            emoji = "🟥" if card_color == "red" else "🟨"

            team_display = self._get_event_team_display(
                card, match, home_team, away_team, home_flag, away_flag
            )

            card_line = f"{minute_display} - {emoji} {player} ({team_display})"
            lines.append(card_line)

        return "\n".join(lines)

    async def notify_match_start(self, details):
        """
        Send a notification when a match starts.

        Args:
            details: MatchDetails object with match info
        """
        match = details.match
        home_display, away_display = self._get_team_displays(match)

        kickoff_info = ""
        if match.start_time:
            start_time = match.start_time.astimezone(self.timezone)
            kickoff_info = f"\nKickoff: {start_time.strftime('%b %d, %I:%M %p %Z')}"

        # Format lineups if available
        lineup_section = ""
        if details.lineups:
            home_lineup = self._format_lineup(
                details.lineups.get("homeTeam", {}), match.home_team.name
            )
            away_lineup = self._format_lineup(
                details.lineups.get("awayTeam", {}), match.away_team.name
            )
            if home_lineup and away_lineup:
                lineup_section = f"\n\n{home_lineup}\n\n{away_lineup}"

        message = (
            f"🟢 **MATCH STARTED:** {home_display} vs {away_display}"
            f"{kickoff_info}"
            f"{lineup_section}"
        )

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            logger.info(
                f"Sending match start notification to {len(guild_channels)} channel(s)"
            )
            await send_to_guild_channels(self.bot, message, guild_channels)

            logger.info(
                f"Match start notification sent for {match.home_team.name} vs {match.away_team.name}"
            )

    async def notify_goal(self, channel, details, goal_event):
        """
        Send a goal notification to Discord.

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
            goal_event: Goal event object

        Returns:
            List of Discord message objects that were sent
        """
        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name

        home_display, away_display = self._get_team_displays(match)
        home_goals, away_goals = self._get_scores(match)

        # Determine which team scored
        scoring_team = (
            home_team if goal_event.team_id == match.home_team.id else away_team
        )
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        # Build message
        scorer = goal_event.player_name or "Unknown"
        minute_display = format_minute(goal_event)

        score_line = f"{home_display} {home_goals}-{away_goals} {away_display}"

        # Check if this is a penalty goal
        is_penalty = is_penalty_goal(goal_event)
        goal_emoji = "🥅" if is_penalty else "⚽"
        goal_type = "PENALTY GOAL!" if is_penalty else "GOAL!"

        message = f"{goal_emoji} **{goal_type}** {score_line}\n\n"

        # Get team display for the scoring team (with flag)
        is_home_scorer = goal_event.team_id == match.home_team.id
        scoring_team_display = (
            f"{home_flag} {home_team}"
            if home_flag and is_home_scorer
            else f"{away_flag} {away_team}"
            if away_flag and not is_home_scorer
            else scoring_team
        )

        if goal_event.own_goal:
            message += (
                f"**Own Goal:** {scorer} ({scoring_team_display}) {minute_display}"
            )
        else:
            message += f"**Scorer:** {scorer} ({scoring_team_display}) {minute_display}"
            if goal_event.assist_name:
                message += f"\n**Assist:** {goal_event.assist_name}"

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        sent_messages = []

        if guild_channels:
            logger.info(
                f"Sending goal notification to {len(guild_channels)} channel(s)"
            )
            sent_messages = await send_to_guild_channels(
                self.bot, message, guild_channels
            )

        return sent_messages

    async def update_goal_notification(self, details, goal_event, messages):
        """
        Update an existing goal notification with new scorer information.

        Args:
            details: MatchDetails object
            goal_event: Updated goal event object with new player_name
            messages: List of Discord message objects to update
        """
        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name

        home_display, away_display = self._get_team_displays(match)
        home_goals, away_goals = self._get_scores(match)

        # Determine which team scored
        scoring_team = (
            home_team if goal_event.team_id == match.home_team.id else away_team
        )
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        # Build updated message
        scorer = goal_event.player_name or "Unknown"
        minute_display = format_minute(goal_event)

        score_line = f"{home_display} {home_goals}-{away_goals} {away_display}"

        # Check if this is a penalty goal
        is_penalty = is_penalty_goal(goal_event)
        goal_emoji = "🥅" if is_penalty else "⚽"
        goal_type = "PENALTY GOAL!" if is_penalty else "GOAL!"

        message = f"{goal_emoji} **{goal_type}** {score_line}\n\n"

        # Get team display for the scoring team (with flag)
        is_home_scorer = goal_event.team_id == match.home_team.id
        scoring_team_display = (
            f"{home_flag} {home_team}"
            if home_flag and is_home_scorer
            else f"{away_flag} {away_team}"
            if away_flag and not is_home_scorer
            else scoring_team
        )

        if goal_event.own_goal:
            message += (
                f"**Own Goal:** {scorer} ({scoring_team_display}) {minute_display}"
            )
        else:
            message += f"**Scorer:** {scorer} ({scoring_team_display}) {minute_display}"
            if goal_event.assist_name:
                message += f"\n**Assist:** {goal_event.assist_name}"

        # Edit all messages
        updated_count = 0
        for msg in messages:
            try:
                await msg.edit(content=message)
                updated_count += 1
                logger.debug(f"Updated goal notification message {msg.id}")
            except Exception as e:
                logger.error(f"Failed to edit message {msg.id}: {e}")

        logger.info(
            f"Updated {updated_count}/{len(messages)} goal notifications with scorer: {scorer}"
        )

    async def notify_var_cancelled_goal(self, channel, details, var_event):
        """
        Send a VAR cancelled goal notification to Discord.

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
            var_event: VAR event object indicating goal cancellation
        """
        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        home_display, away_display = self._get_team_displays(match)
        home_goals, away_goals = self._get_scores(match)

        scorer = var_event.player_name or "Unknown"
        minute_display = format_minute(var_event)

        score_line = f"{home_display} {home_goals}-{away_goals} {away_display}"

        team_display = self._get_event_team_display(
            var_event, match, home_team, away_team, home_flag, away_flag
        )

        # Extract cancellation reason from VAR decision
        reason = get_var_cancellation_reason(var_event)

        message = format_cancelled_goal_notification(
            scorer=scorer,
            team_display=team_display,
            minute_display=minute_display,
            score_line=score_line,
            reason=reason,
        )

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            logger.info(
                f"Sending VAR cancelled goal notification to {len(guild_channels)} channel(s)"
            )
            await send_to_guild_channels(self.bot, message, guild_channels)

    async def notify_var_card_removed(self, channel, details, var_event):
        """
        Send a VAR card removed notification to Discord.

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
            var_event: VAR event object indicating card removal
        """
        from lafcbot.match_events.detectors import get_var_decision_values

        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        player = var_event.player_name or "Unknown"
        minute_display = format_minute(var_event)

        team_display = self._get_event_team_display(
            var_event, match, home_team, away_team, home_flag, away_flag
        )

        # Get VAR decision details
        values = get_var_decision_values(var_event)
        card_type = values[0] if values else "Card"

        message = f"📺 **VAR:** {card_type} cancelled for {player} ({team_display}) {minute_display}"

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            logger.info(
                f"Sending VAR card removed notification to {len(guild_channels)} channel(s)"
            )
            await send_to_guild_channels(self.bot, message, guild_channels)

    async def notify_var_penalty_awarded(self, channel, details, var_event):
        """
        Send a VAR penalty awarded notification to Discord.

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
            var_event: VAR event object indicating penalty awarded
        """
        from lafcbot.match_events.detectors import get_var_decision_values

        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        minute_display = format_minute(var_event)

        team_display = self._get_event_team_display(
            var_event, match, home_team, away_team, home_flag, away_flag
        )

        # Get VAR decision details
        values = get_var_decision_values(var_event)
        reason = values[1] if len(values) > 1 else None

        message = f"📺 **VAR: PENALTY AWARDED** to {team_display} {minute_display}"
        if reason:
            message += f"\nReason: {reason}"

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            logger.info(
                f"Sending VAR penalty awarded notification to {len(guild_channels)} channel(s)"
            )
            await send_to_guild_channels(self.bot, message, guild_channels)

    async def notify_var_card_given(self, channel, details, var_event):
        """
        Send a VAR card given notification to Discord.

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
            var_event: VAR event object indicating card given
        """
        from lafcbot.match_events.detectors import (
            get_var_decision_keys,
        )

        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        player = var_event.player_name or "Unknown"
        minute_display = format_minute(var_event)

        team_display = self._get_event_team_display(
            var_event, match, home_team, away_team, home_flag, away_flag
        )

        # Determine card type from decision keys
        keys = get_var_decision_keys(var_event)
        if "var_red_card_given" in keys:
            card_type = "Red Card"
        else:
            card_type = "Yellow Card"

        message = f"📺 **VAR: {card_type} given** to {player} ({team_display}) {minute_display}"

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            logger.info(
                f"Sending VAR card given notification to {len(guild_channels)} channel(s)"
            )
            await send_to_guild_channels(self.bot, message, guild_channels)

    async def notify_var_penalty_cancelled(self, channel, details, var_event):
        """
        Send a VAR penalty cancelled notification to Discord.

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
            var_event: VAR event object indicating penalty cancelled
        """
        from lafcbot.match_events.detectors import get_var_decision_values

        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        minute_display = format_minute(var_event)

        team_display = self._get_event_team_display(
            var_event, match, home_team, away_team, home_flag, away_flag
        )

        # Get VAR decision details
        values = get_var_decision_values(var_event)
        reason = values[1] if len(values) > 1 else None

        message = f"📺 **VAR: PENALTY CANCELLED** for {team_display} {minute_display}"
        if reason:
            message += f"\nReason: {reason}"

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            logger.info(
                f"Sending VAR penalty cancelled notification to {len(guild_channels)} channel(s)"
            )
            await send_to_guild_channels(self.bot, message, guild_channels)

    async def notify_var_penalty_retake(self, channel, details, var_event):
        """
        Send a VAR penalty retake notification to Discord.

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
            var_event: VAR event object indicating penalty should be retaken
        """
        from lafcbot.match_events.detectors import get_var_decision_values

        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        minute_display = format_minute(var_event)

        team_display = self._get_event_team_display(
            var_event, match, home_team, away_team, home_flag, away_flag
        )

        # Get VAR decision details
        values = get_var_decision_values(var_event)
        decision_text = values[0] if values else "Penalty to be retaken"

        message = f"📺 **VAR: {decision_text}** for {team_display} {minute_display}"

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            logger.info(
                f"Sending VAR penalty retake notification to {len(guild_channels)} channel(s)"
            )
            await send_to_guild_channels(self.bot, message, guild_channels)

    async def notify_var_unknown(self, channel, details, var_event):
        """
        Send a notification for unknown VAR decision types (for logging/discovery).

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
            var_event: VAR event object with unknown decision type
        """
        from lafcbot.match_events.detectors import (
            get_var_decision_keys,
            get_var_decision_values,
        )

        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        player = var_event.player_name or ""
        minute_display = format_minute(var_event)

        # Get team display for the VAR event
        team_display = self._get_event_team_display(
            var_event, match, home_team, away_team, home_flag, away_flag
        )

        keys = get_var_decision_keys(var_event)
        values = get_var_decision_values(var_event)

        # Log for debugging
        logger.warning(
            f"Unknown VAR decision type detected in {match.home_team.name} vs {match.away_team.name}: "
            f"keys={keys}, values={values}, player={player}, team={team_display}"
        )

        # Build notification message
        decision_text = ", ".join(values) if values else "Unknown"

        # Build message with team and optional player
        if player:
            message = (
                f"📺 **VAR Review** {minute_display}\n"
                f"Player: {player} ({team_display})\n"
                f"Decision: {decision_text}"
            )
        else:
            message = (
                f"📺 **VAR Review** {minute_display}\n"
                f"Team: {team_display}\n"
                f"Decision: {decision_text}"
            )

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            await send_to_guild_channels(self.bot, message, guild_channels)

    async def notify_card(self, channel, details, card_event):
        """
        Send a yellow or red card notification to Discord.

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
            card_event: Card event object
        """
        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        card_color = get_card_color(card_event)
        emoji = "🟥" if card_color == "red" else "🟨"
        card_title = "Red Card" if card_color == "red" else "Yellow Card"

        player = card_event.player_name or "Unknown"
        minute_display = format_minute(card_event)

        team_display = self._get_event_team_display(
            card_event, match, home_team, away_team, home_flag, away_flag
        )

        message = (
            f"{emoji} **{card_title}:** {player} {minute_display} for {team_display}"
        )

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            logger.info(
                f"Sending {card_title} notification to {len(guild_channels)} channel(s)"
            )
            await send_to_guild_channels(self.bot, message, guild_channels)

    async def notify_substitution(self, channel, details, sub_event):
        """
        Send a substitution notification to Discord.

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
            sub_event: Substitution event object
        """
        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        player_out = sub_event.player_name or "Unknown"
        player_in = getattr(sub_event, "assist_name", None)
        minute_display = format_minute(sub_event)

        team_display = self._get_event_team_display(
            sub_event, match, home_team, away_team, home_flag, away_flag
        )

        emoji = "🔁"
        if player_in:
            message = f"{emoji} **Substitution:** {player_in} on for {player_out} ({team_display}) {minute_display}"
        else:
            message = f"{emoji} **Substitution:** {player_out} ({team_display}) {minute_display}"

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            await send_to_guild_channels(self.bot, message, guild_channels)

    async def notify_half_event(self, channel, details, half_event):
        """
        Send a half-time or full-time notification to Discord.

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
            half_event: Half-time/full-time event object
        """
        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        # Get the half type from the event (HT or FT)
        half_type = half_event.half_type or ("FT" if half_event.minute >= 90 else "HT")

        home_display, away_display = self._get_team_displays(match)
        home_goals, away_goals = self._get_scores(match)

        score_line = f"{home_display} {home_goals}-{away_goals} {away_display}"

        if half_type == "HT":
            emoji = "⏸️"
            title = "HALF-TIME"
        else:
            emoji = "🏁"
            title = "FULL-TIME"

        message = f"{emoji} **{title}:** {score_line}"

        # Add goals and cards for half-time
        if half_type == "HT":
            goal_list = self._format_goal_list(
                details, match, home_team, away_team, home_flag, away_flag
            )
            if goal_list:
                message += f"\n\n{goal_list}"

            card_list = self._format_card_list(
                details, match, home_team, away_team, home_flag, away_flag
            )
            if card_list:
                message += f"\n\n{card_list}"

        # Add winner/result for full-time
        if half_type == "FT":
            winner_display = f"{home_flag} " if home_flag else ""
            winner_display += f"**{home_team} wins!**"
            loser_display = f"{away_flag} " if away_flag else ""
            loser_display += f"**{away_team} wins!**"

            if home_goals > away_goals:
                message += f"\n\n{winner_display}"
            elif away_goals > home_goals:
                message += f"\n\n{loser_display}"
            else:
                message += "\n\n**Match ends in a draw!**"

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            logger.info(
                f"Sending {half_type} notification to {len(guild_channels)} channel(s)"
            )
            await send_to_guild_channels(self.bot, message, guild_channels)

    async def notify_extra_time(self, channel, details):
        """
        Send an extra time notification.

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
        """
        match = details.match
        home_display, away_display = self._get_team_displays(match)
        home_goals, away_goals = self._get_scores(match)

        message = (
            f"⏱️ **EXTRA TIME:** {home_display} {home_goals}-{away_goals} "
            f"{away_display}\n\nThe match is going to extra time!"
        )

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            logger.info(
                f"Sending extra time notification to {len(guild_channels)} channel(s)"
            )
            await send_to_guild_channels(self.bot, message, guild_channels)

    async def notify_penalties(self, channel, details):
        """
        Send a penalty shootout notification.

        Args:
            channel: Discord channel to send to (unused in multi-server mode)
            details: MatchDetails object
        """
        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name

        home_display, away_display = self._get_team_displays(match)
        home_goals, away_goals = self._get_scores(match)

        message = (
            f"🎯 **PENALTY SHOOTOUT:** {home_display} vs {away_display}\n\n"
            f"After Extra Time: {home_team} {home_goals}-{away_goals} {away_team}\n"
            f"The match will be decided on penalties!"
        )

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            logger.info(
                f"Sending penalty shootout notification to {len(guild_channels)} channel(s)"
            )
            await send_to_guild_channels(self.bot, message, guild_channels)

    async def notify_match_summary(self, details, stale_threshold, was_monitored=False):
        """
        Send post-match summary with highlights and goal clips.

        Args:
            details: MatchDetails object
            stale_threshold: timedelta for checking if match ended too long ago
            was_monitored: If True, skip staleness check (we were tracking it live)
        """
        # Check if match ended too long ago to send summary
        # Skip this check if we were actively monitoring (we know it just finished for us)
        if not was_monitored and details.match.start_time and details.events:
            start_time = details.match.start_time.astimezone(self.timezone)

            # Find the last event minute to estimate when the match actually ended
            last_event_minute = max(
                (
                    e.minute + (e.added_time or 0)
                    for e in details.events
                    if e.minute is not None
                ),
                default=90,
            )

            # Add buffer for post-match activities
            estimated_end_time = start_time + timedelta(minutes=last_event_minute + 10)
            now = datetime.now(self.timezone)
            age_since_end = now - estimated_end_time

            if age_since_end > stale_threshold:
                logger.info(
                    f"Skipping post-match summary for {details.match.home_team.name} vs {details.match.away_team.name} "
                    f"(age since end: {age_since_end.total_seconds():.1f}s, "
                    f"threshold: {stale_threshold.total_seconds():.1f}s)"
                )
                return
        elif was_monitored:
            logger.debug(
                f"Sending post-match summary for {details.match.home_team.name} vs {details.match.away_team.name} "
                f"(was actively monitored, skipping staleness check)"
            )

        match = details.match
        home_team = match.home_team.name
        away_team = match.away_team.name
        home_flag = get_country_flag(home_team)
        away_flag = get_country_flag(away_team)

        home_display, away_display = self._get_team_displays(match)
        home_goals, away_goals = self._get_scores(match)

        # Build message
        lines = [
            f"🏁 **FINAL:** {home_display} {home_goals}-{away_goals} {away_display}\n"
        ]

        # Add penalty result if applicable
        if details.penalties:
            lines.append(
                f"**Penalties:** {home_team} {details.penalties.home_score}-{details.penalties.away_score} {away_team}\n"
            )

        # Add goals
        goal_list = self._format_goal_list(
            details, match, home_team, away_team, home_flag, away_flag
        )
        if goal_list:
            lines.append(goal_list)
            lines.append("")

        # Add cards
        card_list = self._format_card_list(
            details, match, home_team, away_team, home_flag, away_flag
        )
        if card_list:
            lines.append(card_list)
            lines.append("")

        # Add official highlights if available
        if details.highlight:
            lines.append(
                f"📺 **Official Highlights:** [Watch]({details.highlight.url})"
            )

        message = "\n".join(lines)

        # Send to all configured live channels
        guild_channels = self._get_live_channels()
        if guild_channels:
            logger.info(f"Sending match summary to {len(guild_channels)} channel(s)")
            await send_to_guild_channels(self.bot, message, guild_channels)

            logger.info(f"Sent match summary for {home_team} vs {away_team}")
