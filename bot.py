import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from database import close_database, initialize_database
from economy import get_leaderboard, get_or_create_balances

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("fihcoin.bot")
FIHCOIN = "<:fihcoin:1575710572907987064>"


class EconomyProfileView(discord.ui.LayoutView):
    """Components V2 profile layout with the member or server icon in its accessory."""

    def __init__(
        self,
        *,
        heading: str,
        description: str,
        avatar_url: str,
        footer: str = "Fihcoin • Fish Coin",
    ) -> None:
        super().__init__(timeout=None)
        profile = discord.ui.Section(
            discord.ui.TextDisplay(f"## {heading}\n{description}"),
            accessory=discord.ui.Thumbnail(media=avatar_url),
        )
        self.add_item(
            discord.ui.Container(
                profile,
                discord.ui.Separator(),
                discord.ui.TextDisplay(footer),
            )
        )


class FihcoinBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
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


@bot.tree.command(
    name="balance",
    description="View your Fihcoin balance or look up another server member.",
)
@app_commands.guild_only()
@app_commands.describe(user="The server member whose balance you want to view.")
async def balance(
    interaction: discord.Interaction,
    user: discord.Member | None = None,
) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "The Fihcoin economy is only available in the configured server.",
            ephemeral=True,
        )
        return

    target = user or interaction.user
    await interaction.response.defer(thinking=True)

    try:
        wallet, bank = await get_or_create_balances(
            guild_id=interaction.guild.id,
            discord_user_id=target.id,
        )
    except Exception:
        logger.exception("Failed to retrieve balance for Discord user %s", target.id)
        await interaction.followup.send(
            "I couldn't retrieve that balance right now. Please try again shortly."
        )
        return

    total = wallet + bank
    view = EconomyProfileView(
        heading=f"{target.mention}'s Fihcoin Balance",
        description=(
            f"**Wallet**\n{wallet:,.2f} {FIHCOIN}\n\n"
            f"**Bank**\n{bank:,.2f} {FIHCOIN}\n\n"
            f"**Total**\n**{total:,.2f} {FIHCOIN}**"
        ),
        avatar_url=target.display_avatar.url,
    )
    await interaction.followup.send(
        view=view,
        allowed_mentions=discord.AllowedMentions(users=True),
    )


@bot.tree.command(
    name="leaderboard",
    description="View the top 10 members by their combined Fihcoin balance.",
)
@app_commands.guild_only()
async def leaderboard(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "The Fihcoin economy is only available in the configured server.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(thinking=True)
    try:
        entries = await get_leaderboard(interaction.guild.id, limit=10)
    except Exception:
        logger.exception("Failed to retrieve the Fihcoin leaderboard for guild %s", interaction.guild.id)
        await interaction.followup.send(
            "I couldn't retrieve the leaderboard right now. Please try again shortly."
        )
        return

    if not entries:
        description = "No members have economy accounts yet. Use /balance to create an account!"
    else:
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for rank, (member_id, total_balance) in enumerate(entries, start=1):
            marker = medals[rank - 1] if rank <= 3 else f"**#{rank}**"
            lines.append(f"{marker} <@{member_id}> — **{total_balance:,.2f} {FIHCOIN}**")
        description = "\n".join(lines)

    # Prefer the server icon; use the invoking member's avatar if the server has no icon.
    avatar_url = (
        interaction.guild.icon.url
        if interaction.guild.icon
        else interaction.user.display_avatar.url
    )
    view = EconomyProfileView(
        heading="Fihcoin Leaderboard",
        description=f"Top 10 members ranked by wallet + bank balance.\n\n{description}",
        avatar_url=avatar_url,
        footer="Fihcoin • Fish Coin • Rankings are server-specific",
    )
    await interaction.followup.send(view=view)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")

    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
