"""Formatters for latepass cog commands."""

from lafcbot.formatters.base import BaseFormatter


class LatePassFormatter(BaseFormatter):
    """Formats latepass command responses."""

    def format_user_score(
        self,
        user_name: str,
        score: int,
        rank: int,
        is_self: bool = False,
    ) -> str:
        """
        Format individual user latepass score.

        Args:
            user_name: Display name of user
            score: Latepass score (can be negative)
            rank: User's rank (0 if no involvement)
            is_self: Whether this is the command author

        Returns:
            Formatted score message
        """
        if rank == 0:
            if is_self:
                return "You haven't been involved in any latepasses yet."
            else:
                return f"{user_name} hasn't been involved in any latepasses yet."

        score_text = f"{score:+d}"  # Format with + or - sign
        if is_self:
            return f"Your latepass score: {score_text} (#{rank})"
        else:
            return f"{user_name}: {score_text} (#{rank})"

    def format_leaderboard(
        self,
        scores: list[tuple[str, str, int]],  # (user_id, display_name, score)
        limit: int,
    ) -> str:
        """
        Format !latepass leaderboard output.

        Args:
            scores: List of (user_id, display_name, score) tuples
            limit: Number of entries to show

        Returns:
            Formatted leaderboard string
        """
        if not scores:
            return "No latepass scores yet!"

        lines = [f"**Latepass Leaderboard (Top {limit}):**", "```"]

        # Determine column widths
        max_name_len = max(len(name) for _, name, _ in scores)
        name_width = min(max_name_len + 2, 25)

        # Header
        header = self.format_table_row(
            ["#", "User", "Score"],
            [3, name_width, 6],
        )
        lines.append(header)
        lines.append("-" * len(header))

        # User rows
        for i, (_user_id, display_name, score) in enumerate(scores, 1):
            rank = str(i)
            score_text = f"{score:+d}"

            row = self.format_table_row(
                [rank, display_name, score_text],
                [3, name_width, 6],
            )
            lines.append(row)

        lines.append("```")
        return "\n".join(lines)

    def format_stats(
        self,
        total_reposts: int,
        unique_urls: int,
        avg_per_url: float,
    ) -> str:
        """
        Format !latepass stats output.

        Args:
            total_reposts: Total number of reposts
            unique_urls: Number of unique URLs reposted
            avg_per_url: Average reposts per URL

        Returns:
            Formatted stats string
        """
        lines = [
            "**Latepass Server Statistics:**",
            f"Total reposts: {total_reposts}",
            f"Unique URLs: {unique_urls}",
            f"Average reposts per URL: {avg_per_url:.2f}",
        ]
        return "\n".join(lines)

    def format_top_urls(
        self,
        urls_data: list[tuple[str, int, str]],  # (url, count, first_poster_name)
        limit: int,
    ) -> str:
        """
        Format !latepass top output.

        Args:
            urls_data: List of (url, repost_count, first_poster_name) tuples
            limit: Number of entries to show

        Returns:
            Formatted top URLs string
        """
        if not urls_data:
            return "No reposted URLs yet!"

        lines = [f"**Top {limit} Most Reposted URLs:**"]

        for i, (url, count, first_poster) in enumerate(urls_data, 1):
            # Truncate URL if too long
            display_url = url if len(url) <= 60 else url[:57] + "..."
            lines.append(f"{i}. {display_url}")
            lines.append(f"   Reposted {count} times (first by {first_poster})")

        response = "\n".join(lines)
        return self.truncate_for_discord(response)

    def format_viral_urls(
        self,
        urls_data: list[tuple[str, int, str]],  # (url, count, first_poster_name)
        min_reposts: int,
    ) -> str:
        """
        Format !latepass viral output.

        Args:
            urls_data: List of (url, repost_count, first_poster_name) tuples
            min_reposts: Minimum reposts threshold

        Returns:
            Formatted viral URLs string
        """
        if not urls_data:
            return f"No URLs with {min_reposts}+ reposts yet!"

        lines = [f"**Viral URLs ({min_reposts}+ reposts):**"]

        for i, (url, count, first_poster) in enumerate(urls_data, 1):
            # Truncate URL if too long
            display_url = url if len(url) <= 60 else url[:57] + "..."
            lines.append(f"{i}. {display_url}")
            lines.append(f"   Reposted {count} times (first by {first_poster})")

        response = "\n".join(lines)
        return self.truncate_for_discord(response)
