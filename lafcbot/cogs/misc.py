"""Miscellaneous Discord commands for fun."""

import random
import re

from discord.ext import commands


class MiscCog(commands.Cog):
    """Cog for miscellaneous fun commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def wut(self, ctx: commands.Context):
        """Responds with wut."""
        await ctx.send("wut")

    @commands.command()
    async def dice(self, ctx: commands.Context, notation: str):
        """Roll dice in NdM format, e.g. `1d20`, `4d6`, or with modifier `2d8+3`.

        Usage: `!dice 3d6` -> rolls three 6-sided dice and returns the total and individual rolls.
        """
        pattern = r"^\s*(\d{1,3})d(\d{1,4})([+-]\d+)?\s*$"
        m = re.match(pattern, notation)
        if not m:
            await ctx.send(
                "Invalid notation. Use NdM or NdM+K, e.g. `1d20` or `4d6+2`."
            )
            return

        count = int(m.group(1))
        sides = int(m.group(2))
        mod = int(m.group(3) or 0)

        # safety limits
        if count < 1 or count > 200:
            await ctx.send("Number of dice must be between 1 and 200.")
            return
        if sides < 2 or sides > 10000:
            await ctx.send("Number of sides must be between 2 and 10000.")
            return

        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + mod

        # Format response
        rolls_str = ", ".join(str(r) for r in rolls)
        mod_str = f"{mod:+d}" if mod else ""
        await ctx.message.reply(
            f"Rolled {notation}: [{rolls_str}] {mod_str} = **{total}**"
        )

    @commands.command(name="8ball")
    async def eightball(self, ctx: commands.Context, *, _question: str):
        """Ask the magic 8-ball a question and receive a mystical answer.

        Usage: `!8ball Will it rain tomorrow?`
        """
        responses = [
            # Positive responses
            "It is certain.",
            "It is decidedly so.",
            "Without a doubt.",
            "Yes definitely.",
            "You may rely on it.",
            "As I see it, yes.",
            "Most likely.",
            "Outlook good.",
            "Yes.",
            "Signs point to yes.",
            # Non-committal responses
            "Reply hazy, try again.",
            "Ask again later.",
            "Better not tell you now.",
            "Cannot predict now.",
            "Concentrate and ask again.",
            # Negative responses
            "Don't count on it.",
            "My reply is no.",
            "My sources say no.",
            "Outlook not so good.",
            "Very doubtful.",
        ]

        answer = random.choice(responses)
        await ctx.message.reply(f"🎱 {answer}")


def setup(bot):
    """Setup function to add the cog."""
    bot.add_cog(MiscCog(bot))
