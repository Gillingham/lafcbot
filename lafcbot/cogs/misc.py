"""Miscellaneous Discord commands for fun."""

import random
import re

from discord.ext import commands

from lafcbot.clients.espn_client import ESPNClient
from lafcbot.clients.open_meteo_client import OpenMeteoClient
from lafcbot.db import get_user, set_user_weather_location
from lafcbot.utils.config import load_timezone
from lafcbot.utils.errors import handle_api_errors


class MiscCog(commands.Cog):
    """Cog for miscellaneous fun commands."""

    def __init__(self, bot):
        self.bot = bot
        self.weather_client = OpenMeteoClient()
        self.espn_client = ESPNClient()
        self.timezone = load_timezone()

        # Initialize formatters
        from lafcbot.formatters.misc import MiscFormatter
        from lafcbot.formatters.sports import SportsFormatter
        from lafcbot.formatters.weather import WeatherFormatter

        self.misc_formatter = MiscFormatter(self.timezone)
        self.sports_formatter = SportsFormatter(self.timezone)
        self.weather_formatter = WeatherFormatter(self.timezone)

    @commands.command()
    @handle_api_errors("scores")
    async def scores(self, ctx: commands.Context, league: str | None = None):
        """Show today's scores for a sports league in a single concise line.

        Usage: !scores <league>
        Available leagues: nba, mlb, nhl, nfl, f1

        Examples:
          !scores              - Show available leagues
          !scores mlb          - Major League Baseball scores
          !scores nba          - NBA scores
          !scores nhl          - NHL scores
          !scores nfl          - NFL scores
          !scores f1           - Formula 1 results
        """
        available = "nba, mlb, nhl, nfl, f1"

        # No league specified - show available leagues
        if league is None:
            await ctx.message.reply(f"Available leagues: {available}")
            return

        # Normalize league to lowercase
        league = league.lower()

        # Check if league is valid
        if league not in ESPNClient.SPORT_PATHS:
            await ctx.message.reply(
                f"Unknown league '{league}'. Available leagues: {available}"
            )
            return

        # Fetch scoreboard
        league_name, games = await self.espn_client.get_scoreboard(league)

        if not league_name:
            await ctx.message.reply(
                f"Failed to fetch scores for {league.upper()}. Please try again later."
            )
            return

        if not games:
            await ctx.message.reply(f"No games found for {league_name} today.")
            return

        # Convert games to simple format for formatter
        games_data = []
        for game in games:
            if game.is_scheduled and game.scheduled_time:
                local_time = game.scheduled_time.astimezone(self.timezone)
                time_str = local_time.strftime("%a %-m/%-d %-I:%M %p")
                status = time_str
                games_data.append(
                    {
                        "away_team": game.away_team,
                        "home_team": game.home_team,
                        "away_score": 0,
                        "home_score": 0,
                        "status": status,
                    }
                )
            else:
                games_data.append(
                    {
                        "away_team": game.away_team,
                        "home_team": game.home_team,
                        "away_score": game.away_score or 0,
                        "home_score": game.home_score or 0,
                        "status": game.status or "Unknown",
                    }
                )

        # Use formatter
        response = await self.sports_formatter.format_league_scores(
            league_name, games_data
        )
        await ctx.message.reply(response)

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

        # Format response using MiscFormatter
        response = self.misc_formatter.format_dice_roll(notation, rolls, mod, total)
        await ctx.message.reply(response)

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
        response = self.misc_formatter.format_8ball_response(answer)
        await ctx.message.reply(response)

    @commands.command()
    @handle_api_errors("weather")
    async def weather(self, ctx: commands.Context, *, location: str | None = None):
        """Get current weather conditions for a location.

        Usage:
          !weather Seattle           - Get weather for Seattle
          !weather London, UK        - Get weather for London
          !weather 90210            - Get weather by ZIP code
          !weather                  - Get weather for your saved location

        The bot will remember your last location so you can just use !weather next time.
        """

        user_id = str(ctx.author.id)

        # If no location provided, try to get from user preferences
        if location is None:
            prefs = await get_user(user_id)
            if prefs and prefs.get("last_weather_location"):
                location = str(prefs["last_weather_location"])
            else:
                await ctx.send(
                    "Please specify a location (e.g., `!weather Seattle` or `!weather 90210`). "
                    "I'll remember it for next time!"
                )
                return

        # Fetch weather data
        weather = await self.weather_client.get_current_weather(location)

        if weather is None:
            await ctx.send(
                f"Could not find weather data for '{location}'. "
                "Please check the location and try again."
            )
            return

        # Save location preference for this user
        await set_user_weather_location(user_id, location)

        # Format weather response in compact format (keep original complex format)
        parts = [
            f"{weather.location}: {weather.temperature_f:.0f}F {weather.conditions.lower()}",
            f"feels {weather.feels_like_f:.0f}F",
            f"humidity {weather.humidity}%",
            f"wind {weather.wind_direction_text()} {weather.wind_speed_mph:.0f} mph",
        ]

        # Add AQI if available
        if weather.air_quality_index is not None:
            parts.append(
                f"AQI {weather.air_quality_index} {weather.air_quality_category}"
            )

        # Add daily forecast
        parts.append(
            f"Today {weather.temp_max_f:.0f}F/{weather.temp_min_f:.0f}F, {weather.precipitation_probability}% rain"
        )

        response = "; ".join(parts)
        await ctx.message.reply(response)


def setup(bot):
    """Setup function to add the cog."""
    bot.add_cog(MiscCog(bot))
