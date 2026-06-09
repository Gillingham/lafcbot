"""Database operations for lafcbot."""

from datetime import UTC, datetime
from pathlib import Path

import aiosqlite


class Database:
    """Database manager for user preferences."""

    _db_path = None

    @classmethod
    def set_db_path(cls, path: Path):
        """Set the database file path."""
        cls._db_path = path

    @classmethod
    def get_db_path(cls) -> Path:
        """Get the database file path."""
        if cls._db_path is None:
            raise RuntimeError("Database path not set. Call set_db_path() first.")
        return cls._db_path


async def init_db(db_path: Path | None = None):
    """Initialize the database and create tables if they don't exist.

    Args:
        db_path: Path to the database file. If None, uses project_root/lafcbot.db
    """
    if db_path is None:
        project_root = Path(__file__).parent.parent
        db_path = project_root / "lafcbot.db"

    Database.set_db_path(db_path)

    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user (
                    user_id TEXT PRIMARY KEY,
                    last_weather_location TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS posted_urls (
                    url TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    posted_at TEXT NOT NULL,
                    repost_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (url, guild_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS latepass_score (
                    user_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                )
                """
            )
            await db.commit()
        print(f"Database initialized at {db_path}")
    except Exception as e:
        print(f"Error initializing database: {e}")
        raise


async def get_user(user_id: str) -> dict | None:
    """Retrieve user data.

    Args:
        user_id: Discord user ID

    Returns:
        Dictionary with user data or None if not found
    """
    try:
        db_path = Database.get_db_path()
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM user WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None
    except Exception as e:
        print(f"Error retrieving user preference for {user_id}: {e}")
        return None


async def set_user_weather_location(user_id: str, location: str):
    """Save or update user's weather location preference.

    Args:
        user_id: Discord user ID
        location: Weather location string (city name or ZIP code)
    """
    try:
        now = datetime.now(UTC).isoformat()
        db_path = Database.get_db_path()
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                INSERT INTO user (user_id, last_weather_location, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    last_weather_location = excluded.last_weather_location,
                    updated_at = excluded.updated_at
                """,
                (user_id, location, now, now),
            )
            await db.commit()
    except Exception as e:
        print(f"Error saving user preference for {user_id}: {e}")
        raise


async def get_posted_url(url: str, guild_id: str) -> dict | None:
    """Check if a URL has been posted before in a guild.

    Args:
        url: The URL to check
        guild_id: Discord guild (server) ID

    Returns:
        Dictionary with post information or None if URL hasn't been posted
    """
    try:
        db_path = Database.get_db_path()
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM posted_urls WHERE url = ? AND guild_id = ?",
                (url, guild_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None
    except Exception as e:
        print(f"Error checking URL {url} in guild {guild_id}: {e}")
        return None


async def save_posted_url(
    url: str,
    guild_id: str,
    channel_id: str,
    user_id: str,
    username: str,
    message_id: str,
):
    """Save a posted URL to the database.

    Args:
        url: The URL that was posted
        guild_id: Discord guild (server) ID
        channel_id: Discord channel ID
        user_id: Discord user ID who posted it
        username: Username of the poster
        message_id: Discord message ID
    """
    try:
        now = datetime.now(UTC).isoformat()
        db_path = Database.get_db_path()
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO posted_urls
                (url, guild_id, channel_id, user_id, username, message_id, posted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (url, guild_id, channel_id, user_id, username, message_id, now),
            )
            await db.commit()
    except Exception as e:
        print(f"Error saving URL {url}: {e}")
        raise


async def get_latepass_score(user_id: str, guild_id: str) -> int:
    """Get a user's latepass score for a guild.

    Args:
        user_id: Discord user ID
        guild_id: Discord guild (server) ID

    Returns:
        User's latepass score (0 if no record exists)
    """
    try:
        db_path = Database.get_db_path()
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT score FROM latepass_score WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0]
                return 0
    except Exception as e:
        print(f"Error retrieving latepass score for {user_id} in {guild_id}: {e}")
        return 0


async def update_latepass_score(user_id: str, guild_id: str, delta: int):
    """Update a user's latepass score.

    Args:
        user_id: Discord user ID
        guild_id: Discord guild (server) ID
        delta: Amount to change score by (positive or negative)
    """
    try:
        db_path = Database.get_db_path()
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                INSERT INTO latepass_score (user_id, guild_id, score)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    score = score + excluded.score
                """,
                (user_id, guild_id, delta),
            )
            await db.commit()
    except Exception as e:
        print(f"Error updating latepass score for {user_id} in {guild_id}: {e}")
        raise


async def increment_repost_count(url: str, guild_id: str):
    """Increment the repost count for a URL.

    Args:
        url: The URL that was reposted
        guild_id: Discord guild (server) ID
    """
    try:
        db_path = Database.get_db_path()
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                UPDATE posted_urls
                SET repost_count = repost_count + 1
                WHERE url = ? AND guild_id = ?
                """,
                (url, guild_id),
            )
            await db.commit()
    except Exception as e:
        print(f"Error incrementing repost count for {url}: {e}")
        raise


async def get_latepass_leaderboard(guild_id: str, limit: int = 10) -> list[dict]:
    """Get the latepass leaderboard for a guild.

    Args:
        guild_id: Discord guild (server) ID
        limit: Maximum number of entries to return (default 10)

    Returns:
        List of dictionaries with user_id, score, and rank
    """
    try:
        db_path = Database.get_db_path()
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT user_id, score FROM latepass_score
                WHERE guild_id = ?
                ORDER BY score DESC, user_id ASC
                LIMIT ?
                """,
                (guild_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                leaderboard = []
                for rank, row in enumerate(rows, start=1):
                    leaderboard.append(
                        {
                            "user_id": row["user_id"],
                            "score": row["score"],
                            "rank": rank,
                        }
                    )
                return leaderboard
    except Exception as e:
        print(f"Error getting latepass leaderboard for guild {guild_id}: {e}")
        return []


async def get_latepass_stats(guild_id: str) -> dict:
    """Get overall latepass statistics for a guild.

    Args:
        guild_id: Discord guild (server) ID

    Returns:
        Dictionary with various statistics
    """
    try:
        db_path = Database.get_db_path()
        async with aiosqlite.connect(db_path) as db:
            # Total unique URLs posted
            async with db.execute(
                "SELECT COUNT(*) FROM posted_urls WHERE guild_id = ?",
                (guild_id,),
            ) as cursor:
                row = await cursor.fetchone()
                total_urls = row[0] if row else 0

            # Total reposts
            async with db.execute(
                "SELECT SUM(repost_count) FROM posted_urls WHERE guild_id = ?",
                (guild_id,),
            ) as cursor:
                row = await cursor.fetchone()
                total_reposts = row[0] if row and row[0] else 0

            # Most reposted URL
            async with db.execute(
                """
                SELECT url, repost_count, username FROM posted_urls
                WHERE guild_id = ? AND repost_count > 0
                ORDER BY repost_count DESC
                LIMIT 1
                """,
                (guild_id,),
            ) as cursor:
                row = await cursor.fetchone()
                most_reposted = (
                    {
                        "url": row[0],
                        "count": row[1],
                        "username": row[2],
                    }
                    if row
                    else None
                )

            # Total users with scores
            async with db.execute(
                "SELECT COUNT(*) FROM latepass_score WHERE guild_id = ?",
                (guild_id,),
            ) as cursor:
                row = await cursor.fetchone()
                total_users = row[0] if row else 0

            return {
                "total_urls": total_urls,
                "total_reposts": total_reposts,
                "most_reposted": most_reposted,
                "total_users": total_users,
            }
    except Exception as e:
        print(f"Error getting latepass stats for guild {guild_id}: {e}")
        return {
            "total_urls": 0,
            "total_reposts": 0,
            "most_reposted": None,
            "total_users": 0,
        }


async def get_top_reposted_urls(guild_id: str, limit: int = 10) -> list[dict]:
    """Get the most reposted URLs in a guild.

    Args:
        guild_id: Discord guild (server) ID
        limit: Maximum number of URLs to return (default 10)

    Returns:
        List of dictionaries with URL, repost_count, username, and posted_at
    """
    try:
        db_path = Database.get_db_path()
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT url, repost_count, username, posted_at FROM posted_urls
                WHERE guild_id = ? AND repost_count > 0
                ORDER BY repost_count DESC, posted_at DESC
                LIMIT ?
                """,
                (guild_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error getting top reposted URLs for guild {guild_id}: {e}")
        return []


async def get_viral_urls(guild_id: str, min_reposts: int = 10) -> list[dict]:
    """Get viral URLs (highly reposted) in a guild.

    Args:
        guild_id: Discord guild (server) ID
        min_reposts: Minimum number of reposts to be considered viral (default 10)

    Returns:
        List of dictionaries with URL, repost_count, username, and posted_at
    """
    try:
        db_path = Database.get_db_path()
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT url, repost_count, username, posted_at FROM posted_urls
                WHERE guild_id = ? AND repost_count >= ?
                ORDER BY repost_count DESC, posted_at DESC
                """,
                (guild_id, min_reposts),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error getting viral URLs for guild {guild_id}: {e}")
        return []


async def get_latepass_rank(user_id: str, guild_id: str) -> tuple[int, int]:
    """Get a user's rank in the latepass leaderboard for a guild.

    Args:
        user_id: Discord user ID
        guild_id: Discord guild (server) ID

    Returns:
        Tuple of (score, rank) where rank is 1-indexed position
        Returns (0, 0) if user has no score record
    """
    try:
        db_path = Database.get_db_path()
        async with aiosqlite.connect(db_path) as db:
            # Get all scores for the guild, ordered by score descending
            async with db.execute(
                """
                SELECT user_id, score FROM latepass_score
                WHERE guild_id = ?
                ORDER BY score DESC, user_id ASC
                """,
                (guild_id,),
            ) as cursor:
                rows = await cursor.fetchall()

                # Find the user's rank
                for rank, (uid, score) in enumerate(rows, start=1):
                    if uid == user_id:
                        return (score, rank)

                # User not found in rankings
                return (0, 0)
    except Exception as e:
        print(f"Error getting latepass rank for {user_id} in {guild_id}: {e}")
        return (0, 0)
