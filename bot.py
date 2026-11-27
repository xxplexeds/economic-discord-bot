import logging
import os

import discord
from discord.ext import commands
from discord import app_commands

from database import close_database, initialize_database
from economy import get_or_create_balances

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
        await initialize_database()
        logger.info("PostgreSQL is ready.")

        guild_id = os.getenv("DISCORD_GUILD_ID")

        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("Synced %s application commands to guild %s", len(synced), guild_id)
        else:
            synced = await self.tree.sync()
            logger.info("Synced %s global application commands", len(synced))

    async def close(self) -> None:
        try:
            await close_database()
        finally:
            await super().close()


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



@bot.tree.command(name="balance", description="View your Fihcoin wallet and bank balances.")
@app_commands.guild_only()
async def balance(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "The Fihcoin economy is only available in the configured server.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        wallet, bank = await get_or_create_balances(
            guild_id=interaction.guild.id,
            discord_user_id=interaction.user.id,
        )
    except Exception:
        logger.exception("Failed to retrieve balance for Discord user %s", interaction.user.id)
        await interaction.followup.send(
            "I couldn't retrieve your balance right now. Please try again shortly.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="🐟 Your Fihcoin Balance",
        color=discord.Color.blurple(),
        description="Your personal economy accounts.",
    )
    embed.add_field(name="Wallet", value=f"**{wallet:,.2f}** <:fihcoin:1575710572907987064>", inline=True)
    embed.add_field(name="Bank", value=f"**{bank:,.2f}** <:fihcoin:1575710572907987064>", inline=True)
    embed.add_field(name="Total", value=f"**{wallet + bank:,.2f}** <:fihcoin:1575710572907987064>", inline=False)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Fihcoin • Fish Coin")

    await interaction.followup.send(embed=embed, ephemeral=True)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")

    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
