import json
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands


def load_config() -> dict:
    """Load configuration from config.json."""
    # Navigate up from lafcbot/bot.py to project root
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


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
world_cup_task = None


@bot.event
async def on_ready():
    global world_cup_task

    print(f"Logged in as: {bot.user} (ID: {bot.user.id})")
    print("Connected guilds:")
    for g in bot.guilds:
        # use guild.member_count to avoid iterating members (no privileged intent required)
        print(f"- {g.name} (ID: {g.id}) — {g.member_count} members")
    print("------")

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

    # Load config and start World Cup task if enabled
    config = load_config()
    wc_config = config.get("world_cup", {})

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


def main():
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
