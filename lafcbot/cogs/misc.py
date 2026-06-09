"""Miscellaneous Discord commands for fun."""

import json
import random
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from discord.ext import commands

from lafcbot.clients.espn_client import ESPNClient
from lafcbot.clients.open_meteo_client import OpenMeteoClient
from lafcbot.db import get_user, set_user_weather_location


class MiscCog(commands.Cog):
    """Cog for miscellaneous fun commands."""

    def __init__(self, bot):
        self.bot = bot
        self.weather_client = OpenMeteoClient()
        self.espn_client = ESPNClient()
        # Load timezone from config
        self.timezone = self._load_timezone()

    def _load_timezone(self) -> ZoneInfo:
        """Load timezone from config.json."""
        config_path = Path(__file__).parent.parent.parent / "config.json"
        try:
            with open(config_path) as f:
                config = json.load(f)
                tz_name = config.get("timezone", "America/Los_Angeles")
                return ZoneInfo(tz_name)
        except Exception as e:
            print(f"Error loading timezone from config: {e}, using default")
            return ZoneInfo("America/Los_Angeles")

    @commands.command()
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
        try:
            league_name, games = await self.espn_client.get_scoreboard(league)

            if not league_name:
                await ctx.message.reply(
                    f"Failed to fetch scores for {league.upper()}. Please try again later."
                )
                return

            if not games:
                await ctx.message.reply(f"No games found for {league_name} today.")
                return

            # Format games as single line
            game_strings = []
            for game in games:
                if game.is_scheduled and game.scheduled_time:
                    # For scheduled games, show time without scores
                    local_time = game.scheduled_time.astimezone(self.timezone)
                    time_str = local_time.strftime("%a %-m/%-d %-I:%M %p")
                    game_str = f"{game.away_team} @ {game.home_team} ({time_str})"
                else:
                    # For in-progress or final games, show scores and status
                    game_str = f"{game.away_team} {game.away_score} @ {game.home_team} {game.home_score} {game.status}"
                game_strings.append(game_str)

            output = f"{league_name}: {' | '.join(game_strings)}"
            await ctx.message.reply(output)

        except Exception as e:
            import traceback

            await ctx.message.reply(f"Error fetching scores: {e}")
            print(traceback.format_exc())

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

    @commands.command()
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
                location = prefs["last_weather_location"]
            else:
                await ctx.send(
                    "Please specify a location (e.g., `!weather Seattle` or `!weather 90210`). "
                    "I'll remember it for next time!"
                )
                return

        # Fetch weather data
        try:
            weather = await self.weather_client.get_current_weather(location)

            if weather is None:
                await ctx.send(
                    f"Could not find weather data for '{location}'. "
                    "Please check the location and try again."
                )
                return

            # Save location preference for this user
            await set_user_weather_location(user_id, location)

            # Format weather response in compact format
            # Example: Pasadena, CA, US: 72F overcast; feels 71F; humidity 63%; wind WSW 8 mph; AQI 64 moderate; Today 79F/59F, 0% rain
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

        except Exception as e:
            import traceback

            await ctx.send(f"Error fetching weather: {e}")
            print(traceback.format_exc())


def setup(bot):
    """Setup function to add the cog."""
    bot.add_cog(MiscCog(bot))
