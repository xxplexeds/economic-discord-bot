import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("fihcoin.bot")


class FihcoinBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
        )

    async def setup_hook(self) -> None:
        guild_id = os.getenv("DISCORD_GUILD_ID")

        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("Synced %s application commands to guild %s", len(synced), guild_id)
        else:
            synced = await self.tree.sync()
            logger.info("Synced %s global application commands", len(synced))


bot = FihcoinBot()


@bot.event
async def on_ready() -> None:
    if bot.user:
        logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)


@bot.tree.command(name="ping", description="Check whether Fihcoin Bot is online.")
async def ping(interaction: discord.Interaction) -> None:
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(
        f"🐟 Fihcoin Bot is online! Latency: **{latency_ms} ms**",
        ephemeral=True,
    )


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")

    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
