"""Error handling utilities for commands."""

import functools
import traceback

from discord.ext import commands


def handle_api_errors(resource_name: str):
    """Decorator for consistent API error handling in commands.

    Args:
        resource_name: Name of the resource being fetched (e.g., "matches", "standings").

    Returns:
        Function decorator that wraps command execution with error handling.

    Example:
        @commands.command()
        @handle_api_errors("matches")
        async def matches(self, ctx, *, league: str | None = None):
            # Command logic without try/except
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, ctx: commands.Context, *args, **kwargs):
            try:
                return await func(self, ctx, *args, **kwargs)
            except Exception as e:
                await ctx.send(f"Error fetching {resource_name}: {e}")
                print(f"Error in {func.__name__}: {e}")
                print(traceback.format_exc())

        return wrapper

    return decorator
