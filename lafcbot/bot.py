import logging
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

from lafcbot.utils.config import load_config


def setup_logging(config: dict):
    """Configure logging based on config."""
    log_level_str = config.get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    # We want the configured level to apply only to our "lafcbot" namespace.
    # Configure root handler at NOTSET so individual loggers control emission.
    logging.basicConfig(
        level=logging.NOTSET,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Apply the configured level only to lafcbot.* loggers
    app_logger = logging.getLogger("lafcbot")
    app_logger.setLevel(log_level)

    # Keep discord.py logger quiet (only show warnings and errors)
    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.WARNING)

    # Keep aiosqlite log output quiet as well
    aiosqlite_logger = logging.getLogger("aiosqlite")
    aiosqlite_logger.setLevel(logging.WARNING)

    # Log the configuration from our module logger
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured: lafcbot={log_level_str}")


# Load config and configure logging
config = load_config()
setup_logging(config)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
world_cup_task = None
_ready_once = False  # Tracks whether on_ready setup has already run to avoid dupe instances

@bot.event
async def on_ready():
    global world_cup_task, _ready_once

    print(f"Logged in as: {bot.user} (ID: {bot.user.id})")
    print("Connected guilds:")
    for g in bot.guilds:
        # use guild.member_count to avoid iterating members (no privileged intent required)
        print(f"- {g.name} (ID: {g.id}) — {g.member_count} members")
    print("------")

    # Added to avoid duplicate instances being created on reconnect
    if _ready_once:
        # on_ready fires again on every gateway reconnect; only run setup once.
        print("on_ready fired again (reconnect) — skipping re-initialization")
        return
    _ready_once = True

    # Initialize database
    try:
        from lafcbot.db import init_db

        await init_db()
    except Exception as e:
        print(f"Failed to initialize database: {e}")

    # Load cogs
    try:
        bot.load_extension("lafcbot.cogs.soccer")
        print("Loaded soccer cog")
    except Exception as e:
        print(f"Failed to load soccer cog: {e}")

    try:
        bot.load_extension("lafcbot.cogs.misc")
        print("Loaded misc cog")
    except Exception as e:
        print(f"Failed to load misc cog: {e}")

    try:
        bot.load_extension("lafcbot.cogs.latepass")
        print("Loaded latepass cog")
    except Exception as e:
        print(f"Failed to load latepass cog: {e}")

    try:
        bot.load_extension("lafcbot.cogs.pandaping")
        print("Loaded pandaping cog")
    except Exception as e:
        print(f"Failed to load pandaping cog: {e}")

    # Load config and start World Cup task if enabled
    wc_config = config.get("world_cup", {})

    # Add root-level timezone to wc_config if not already present
    if "timezone" not in wc_config and "timezone" in config:
        wc_config["timezone"] = config["timezone"]

    if wc_config.get("enabled", False):
        from lafcbot.tasks.world_cup import WorldCupTask

        # Get fotmob_client from the soccer cog
        soccer_cog = bot.get_cog("SoccerCog")
        if soccer_cog:
            world_cup_task = WorldCupTask(bot, soccer_cog.fotmob_client, wc_config)
            world_cup_task.start()
            print("Started World Cup task")
        else:
            print("Could not start World Cup task: SoccerCog not loaded")
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
    if soccer_cog and soccer_cog.fotmob_client:
        await soccer_cog.fotmob_client.close()

    misc_cog = bot.get_cog("MiscCog")
    if misc_cog and misc_cog.weather_client:
        await misc_cog.weather_client.close()


def main():
    # Load environment variables from .env file
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
