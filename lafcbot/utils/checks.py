"""Discord command checks and decorators."""

import functools

from discord.ext import commands


def guild_only_with_message():
    """Check that command is run in a guild, with custom error message.

    Returns:
        Discord check decorator that validates guild context.
    """

    async def predicate(ctx):
        if not ctx.guild:
            await ctx.message.reply("This command only works in servers.")
            return False
        return True

    return commands.check(predicate)


def require_fotmob_client():
    """Decorator to ensure FotMob client is initialized before command runs.

    This decorator checks that self.fotmob_client exists and is not None.
    If the client is not initialized, sends an error message to the user.

    Returns:
        Function decorator for Discord commands.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, ctx: commands.Context, *args, **kwargs):
            if self.fotmob_client is None:
                await ctx.send(
                    "FotMob client not initialized. Please wait for bot to fully start."
                )
                return
            return await func(self, ctx, *args, **kwargs)

        return wrapper

    return decorator
