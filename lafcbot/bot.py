import json
import logging
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv


def load_config() -> dict:
    """Load configuration from config.json."""
    config_path = Path(__file__).parent.parent / "config.json"
    try:
        with open(config_path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: {config_path} not found, using defaults")
        return {
            "world_cup": {
                "enabled": False,
                "channel_name": "world-cup",
                "daily_time_hour": 8,
                "timezone": "America/Los_Angeles",
            },
            "channel_leagues": {},
        }
    except json.JSONDecodeError as e:
        print(f"Error parsing config.json: {e}")
        return {"world_cup": {"enabled": False}, "channel_leagues": {}}


def setup_logging(config: dict):
    """Configure logging based on config."""
    log_level_str = config.get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logging.basicConfig(
        level=logging.NOTSET,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logging.getLogger("lafcbot").setLevel(log_level)
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured: lafcbot={log_level_str}")


config = load_config()
setup_logging(config)

world_cup_task = None


class LAFCBot(commands.Bot):
    async def setup_hook(self):
        """Runs once before the bot connects to Discord."""
        # Initialize database
        try:
            from lafcbot.db import init_db

            await init_db()
        except Exception as e:
            print(f"Failed to initialize database: {e}")

        # Load cogs
        extensions = [
            "lafcbot.cogs.soccer",
            "lafcbot.cogs.misc",
            "lafcbot.cogs.latepass",
            "lafcbot.cogs.pandaping",
        ]

        for extension in extensions:
            try:
                await self.load_extension(extension)
                print(f"Loaded {extension}")
            except Exception as e:
                print(f"Failed to load {extension}: {e}")


intents = discord.Intents.default()
intents.message_content = True

bot = LAFCBot(command_prefix="!", intents=intents)
bot.world_cup_started = False


@bot.event
async def on_ready():
    global world_cup_task

    print(f"Logged in as: {bot.user} (ID: {bot.user.id})")
    print("Connected guilds:")
    for g in bot.guilds:
        print(f"- {g.name} (ID: {g.id}) — {g.member_count} members")
    print("------")

    # Prevent this from running multiple times after reconnects
    if bot.world_cup_started:
        return

    wc_config = config.get("world_cup", {})

    if "timezone" not in wc_config and "timezone" in config:
        wc_config["timezone"] = config["timezone"]

    if wc_config.get("enabled", False):
        try:
            from lafcbot.tasks.world_cup import WorldCupTask

            soccer_cog = bot.get_cog("SoccerCog")

            if soccer_cog:
                world_cup_task = WorldCupTask(bot, soccer_cog.fotmob_client, wc_config)
                world_cup_task.start()
                bot.world_cup_started = True
                print("Started World Cup task")
            else:
                print("Could not start World Cup task: SoccerCog not loaded")
        except Exception as e:
            print(f"Could not start World Cup task: {e}")
    else:
        print("World Cup daily task is disabled in config")


@bot.command()
async def ping(ctx: commands.Context):
    """Responds with Pong and latency in ms."""
    await ctx.send(f"Pong! {round(bot.latency * 1000)}ms")


@bot.command()
@commands.is_owner()
async def servers(ctx: commands.Context):
    """DMs the command caller the list of guilds the bot is in."""
    lines = [f"{g.name} (ID: {g.id}) — {g.member_count} members" for g in bot.guilds]
    content = "\n".join(lines) or "Not in any guilds"

    try:
        await ctx.author.send(content)
    except Exception:
        await ctx.send("Could not send DM; check your privacy settings.")


async def shutdown():
    """Clean shutdown of async resources."""
    global world_cup_task

    if world_cup_task:
        world_cup_task.stop()

    soccer_cog = bot.get_cog("SoccerCog")
    if soccer_cog and getattr(soccer_cog, "fotmob_client", None):
        await soccer_cog.fotmob_client.close()

    misc_cog = bot.get_cog("MiscCog")
    if misc_cog and getattr(misc_cog, "weather_client", None):
        await misc_cog.weather_client.close()


def main():
    load_dotenv()

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("Error: DISCORD_TOKEN environment variable not set.")
        sys.exit(1)

    try:
        bot.run(token)
    finally:
        import asyncio

        asyncio.run(shutdown())


if __name__ == "__main__":
    main()