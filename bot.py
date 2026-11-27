import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from database import close_database, initialize_database
from economy import (
    get_leaderboard_page,
    get_or_create_balances,
    get_transaction_history_page,
    has_admin_history_access,
)

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
        balance_sections: tuple[str, str, str] | None = None,
        description_sections: tuple[str, str] | None = None,
    ) -> None:
        super().__init__(timeout=None)
        if balance_sections is not None:
            profile_content = discord.ui.TextDisplay(f"## {heading}")
            wallet_section, bank_section, total_section = balance_sections
            content = [
                discord.ui.TextDisplay(wallet_section),
                discord.ui.Separator(),
                discord.ui.TextDisplay(bank_section),
                discord.ui.Separator(),
                discord.ui.TextDisplay(total_section),
            ]
        elif description_sections is not None:
            profile_content = discord.ui.TextDisplay(f"## {heading}")
            intro_section, details_section = description_sections
            content = [
                discord.ui.TextDisplay(intro_section),
                discord.ui.Separator(),
                discord.ui.TextDisplay(details_section),
            ]
        else:
            profile_content = discord.ui.TextDisplay(f"## {heading}\\n{description}")
            content = []

        profile = discord.ui.Section(
            profile_content,
            accessory=discord.ui.Thumbnail(media=avatar_url),
        )
        self.add_item(
            discord.ui.Container(
                profile,
                *content,
                discord.ui.Separator(),
                discord.ui.TextDisplay(footer),
            )
        )


class LeaderboardPageButton(discord.ui.Button):
    def __init__(self, leaderboard_view: "LeaderboardView", *, direction: int, disabled: bool) -> None:
        super().__init__(
            label="Previous" if direction < 0 else "Next",
            style=discord.ButtonStyle.secondary,
            disabled=disabled,
        )
        self.leaderboard_view = leaderboard_view
        self.direction = direction

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.leaderboard_view.navigate(
            interaction,
            self.leaderboard_view.current_page + self.direction,
        )


class LeaderboardPageSelect(discord.ui.Select):
    def __init__(self, leaderboard_view: "LeaderboardView") -> None:
        self.leaderboard_view = leaderboard_view
        current = leaderboard_view.current_page
        total_pages = leaderboard_view.total_pages
        first_page = max(1, min(current - 12, total_pages - 24))
        last_page = min(total_pages, first_page + 24)
        options = [
            discord.SelectOption(
                label=f"Page {page}",
                description=(
                    f"Ranks {(page - 1) * leaderboard_view.page_size + 1}-"
                    f"{min(page * leaderboard_view.page_size, leaderboard_view.total_count)}"
                ),
                value=str(page),
                default=(page == current),
            )
            for page in range(first_page, last_page + 1)
        ]
        super().__init__(
            placeholder=f"Jump to page {current} of {total_pages}",
            min_values=1,
            max_values=1,
            options=options,
            disabled=(total_pages <= 1),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.leaderboard_view.navigate(interaction, int(self.values[0]))


class LeaderboardView(discord.ui.LayoutView):
    """Interactive Components V2 leaderboard with buttons and a page selector."""

    page_size = 10

    def __init__(
        self,
        *,
        guild_id: int,
        avatar_url: str,
        entries: list[tuple[int, object]],
        total_count: int,
        page: int = 1,
    ) -> None:
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.avatar_url = avatar_url
        self.entries = entries
        self.total_count = total_count
        self.total_pages = max(1, (total_count + self.page_size - 1) // self.page_size)
        self.current_page = page
        self._render()

    def _render(self) -> None:
        self.clear_items()
        if not self.entries:
            rankings = "No members have economy accounts yet. Use /balance to create an account!"
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for index, (member_id, total_balance) in enumerate(
                self.entries,
                start=(self.current_page - 1) * self.page_size + 1,
            ):
                marker = medals[index - 1] if index <= 3 else f"**#{index}**"
                lines.append(
                    f"{marker} <@{member_id}> — **{total_balance:,.2f} {FIHCOIN}**"
                )
            rankings = "\\n".join(lines)

        profile = discord.ui.Section(
            discord.ui.TextDisplay("## Fihcoin Leaderboard"),
            accessory=discord.ui.Thumbnail(media=self.avatar_url),
        )
        self.add_item(
            discord.ui.Container(
                profile,
                discord.ui.TextDisplay("Top 10 members ranked by wallet + bank balance."),
                discord.ui.Separator(),
                discord.ui.TextDisplay(rankings),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"Page **{self.current_page}** of **{self.total_pages}**"
                    f" • {self.total_count:,} members"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "Fihcoin • Fish Coin • Rankings are server-specific"
                ),
            )
        )
        self.add_item(
            discord.ui.ActionRow(
                LeaderboardPageButton(
                    self,
                    direction=-1,
                    disabled=(self.current_page <= 1),
                ),
                LeaderboardPageButton(
                    self,
                    direction=1,
                    disabled=(self.current_page >= self.total_pages),
                ),
            )
        )
        self.add_item(discord.ui.ActionRow(LeaderboardPageSelect(self)))

    async def navigate(self, interaction: discord.Interaction, page: int) -> None:
        target_page = max(1, min(page, self.total_pages))
        try:
            entries, total_count = await get_leaderboard_page(
                self.guild_id,
                limit=self.page_size,
                offset=(target_page - 1) * self.page_size,
            )
        except Exception:
            logger.exception(
                "Failed to retrieve leaderboard page %s for guild %s",
                target_page,
                self.guild_id,
            )
            await interaction.response.send_message(
                "I couldn't load that leaderboard page. Please try again shortly.",
                ephemeral=True,
            )
            return

        self.entries = entries
        self.total_count = total_count
        self.total_pages = max(1, (total_count + self.page_size - 1) // self.page_size)
        self.current_page = min(target_page, self.total_pages)
        self._render()
        await interaction.response.edit_message(
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class TransactionHistoryPageButton(discord.ui.Button):
    def __init__(
        self,
        history_view: "TransactionHistoryView",
        *,
        direction: int,
        disabled: bool,
    ) -> None:
        super().__init__(
            label="Previous" if direction < 0 else "Next",
            style=discord.ButtonStyle.secondary,
            disabled=disabled,
        )
        self.history_view = history_view
        self.direction = direction

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.history_view.navigate(
            interaction,
            self.history_view.current_page + self.direction,
        )


class TransactionHistoryPageSelect(discord.ui.Select):
    def __init__(self, history_view: "TransactionHistoryView") -> None:
        self.history_view = history_view
        current = history_view.current_page
        total_pages = history_view.total_pages
        first_page = max(1, min(current - 12, total_pages - 24))
        last_page = min(total_pages, first_page + 24)
        options = [
            discord.SelectOption(
                label=f"Page {page}",
                description=(
                    f"Records {(page - 1) * history_view.page_size + 1}-"
                    f"{min(page * history_view.page_size, history_view.total_count)}"
                ),
                value=str(page),
                default=(page == current),
            )
            for page in range(first_page, last_page + 1)
        ]
        super().__init__(
            placeholder=f"Jump to page {current} of {total_pages}",
            min_values=1,
            max_values=1,
            options=options,
            disabled=(total_pages <= 1),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.history_view.navigate(interaction, int(self.values[0]))


class TransactionHistoryView(discord.ui.LayoutView):
    """Private, read-only Components V2 transaction history with pagination."""

    page_size = 10

    def __init__(
        self,
        *,
        requester_id: int,
        guild_id: int,
        target_id: int,
        target_name: str,
        avatar_url: str,
        entries: list,
        total_count: int,
        page: int = 1,
    ) -> None:
        super().__init__(timeout=900)
        self.requester_id = requester_id
        self.guild_id = guild_id
        self.target_id = target_id
        self.target_name = target_name
        self.avatar_url = avatar_url
        self.entries = entries
        self.total_count = total_count
        self.total_pages = max(1, (total_count + self.page_size - 1) // self.page_size)
        self.current_page = page
        self._render()

    def _render(self) -> None:
        self.clear_items()
        if not self.entries:
            details = "No transactions have been recorded for this member yet."
        else:
            lines = []
            for record in self.entries:
                if (
                    record.sender_discord_id == self.target_id
                    and record.recipient_discord_id != self.target_id
                ):
                    direction = "Sent"
                elif (
                    record.recipient_discord_id == self.target_id
                    and record.sender_discord_id != self.target_id
                ):
                    direction = "Received"
                else:
                    direction = record.transaction_type.replace("_", " ").title()

                amount = f"{record.amount:,.2f} {FIHCOIN}"
                if direction == "Sent":
                    amount = f"−{amount}"
                elif direction == "Received":
                    amount = f"+{amount}"

                timestamp = int(record.created_at.timestamp()) if record.created_at else 0
                line = (
                    f"**{direction}** • **{amount}**\n"
                    f"<t:{timestamp}:f>"
                )
                if record.fee:
                    line += f" • Fee: {record.fee:,.2f} {FIHCOIN}"
                if record.note:
                    line += f"\n_{discord.utils.escape_markdown(record.note)}_"
                if record.actor_discord_id and record.actor_discord_id != self.target_id:
                    line += f"\nBy <@{record.actor_discord_id}>"
                lines.append(line)
            details = "\n\n".join(lines)

        profile = discord.ui.Section(
            discord.ui.TextDisplay("## Fihcoin Transaction History"),
            accessory=discord.ui.Thumbnail(media=self.avatar_url),
        )
        self.add_item(
            discord.ui.Container(
                profile,
                discord.ui.TextDisplay(f"History for **{discord.utils.escape_markdown(self.target_name)}**"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(details),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"Page **{self.current_page}** of **{self.total_pages}**"
                    f" • {self.total_count:,} transactions"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay("Read-only • Only you can see this • Fihcoin"),
            )
        )
        self.add_item(
            discord.ui.ActionRow(
                TransactionHistoryPageButton(
                    self,
                    direction=-1,
                    disabled=(self.current_page <= 1),
                ),
                TransactionHistoryPageButton(
                    self,
                    direction=1,
                    disabled=(self.current_page >= self.total_pages),
                ),
            )
        )
        self.add_item(discord.ui.ActionRow(TransactionHistoryPageSelect(self)))

    async def navigate(self, interaction: discord.Interaction, page: int) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who opened this private history can use these controls.",
                ephemeral=True,
            )
            return

        if self.requester_id != self.target_id:
            member = interaction.user
            has_access = (
                isinstance(member, discord.Member)
                and member.guild_permissions.administrator
            )
            if not has_access and isinstance(member, discord.Member):
                has_access = await has_admin_history_access(
                    self.guild_id,
                    member.id,
                    [role.id for role in member.roles],
                )
            if not has_access:
                await interaction.response.send_message(
                    "You no longer have permission to view another member's transaction history.",
                    ephemeral=True,
                )
                return

        target_page = max(1, min(page, self.total_pages))
        try:
            entries, total_count = await get_transaction_history_page(
                self.guild_id,
                self.target_id,
                limit=self.page_size,
                offset=(target_page - 1) * self.page_size,
            )
        except Exception:
            logger.exception(
                "Failed to retrieve transaction history page %s for user %s",
                target_page,
                self.target_id,
            )
            await interaction.response.send_message(
                "I couldn't load that transaction history page. Please try again shortly.",
                ephemeral=True,
            )
            return

        self.entries = entries
        self.total_count = total_count
        self.total_pages = max(1, (total_count + self.page_size - 1) // self.page_size)
        self.current_page = min(target_page, self.total_pages)
        self._render()
        await interaction.response.edit_message(
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
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
        description="",
        balance_sections=(
            f"**Wallet**\n{wallet:,.2f} {FIHCOIN}",
            f"**Bank**\n{bank:,.2f} {FIHCOIN}",
            f"**Total**\n**{total:,.2f} {FIHCOIN}**",
        ),
        avatar_url=target.display_avatar.url,
    )
    await interaction.followup.send(
        view=view,
        allowed_mentions=discord.AllowedMentions.none(),
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
        entries, total_count = await get_leaderboard_page(
            interaction.guild.id,
            limit=LeaderboardView.page_size,
            offset=0,
        )
    except Exception:
        logger.exception(
            "Failed to retrieve the Fihcoin leaderboard for guild %s",
            interaction.guild.id,
        )
        await interaction.followup.send(
            "I couldn't retrieve the leaderboard right now. Please try again shortly."
        )
        return

    # Prefer the server icon; use the invoking member's avatar if the server has no icon.
    avatar_url = (
        interaction.guild.icon.url
        if interaction.guild.icon
        else interaction.user.display_avatar.url
    )
    view = LeaderboardView(
        guild_id=interaction.guild.id,
        avatar_url=avatar_url,
        entries=entries,
        total_count=total_count,
    )
    await interaction.followup.send(
        view=view,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.tree.command(
    name="transactions",
    description="Privately view your transaction history or an authorized member's history.",
)
@app_commands.guild_only()
@app_commands.describe(user="The member whose history you want to inspect (administrators only).")
async def transactions(
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
    if target.id != interaction.user.id:
        requester = interaction.user
        has_access = (
            isinstance(requester, discord.Member)
            and requester.guild_permissions.administrator
        )
        if not has_access and isinstance(requester, discord.Member):
            try:
                has_access = await has_admin_history_access(
                    interaction.guild.id,
                    requester.id,
                    [role.id for role in requester.roles],
                )
            except Exception:
                logger.exception(
                    "Failed to verify transaction-history access for user %s",
                    requester.id,
                )
                await interaction.response.send_message(
                    "I couldn't verify your permissions right now. Please try again shortly.",
                    ephemeral=True,
                )
                return

        if not has_access:
            await interaction.response.send_message(
                "You can only view your own transaction history. Discord Administrators "
                "and members with an authorized Administrative Role can inspect other members.",
                ephemeral=True,
            )
            return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        entries, total_count = await get_transaction_history_page(
            interaction.guild.id,
            target.id,
            limit=TransactionHistoryView.page_size,
            offset=0,
        )
    except Exception:
        logger.exception(
            "Failed to retrieve transaction history for user %s",
            target.id,
        )
        await interaction.followup.send(
            "I couldn't retrieve that transaction history right now. Please try again shortly.",
            ephemeral=True,
        )
        return

    view = TransactionHistoryView(
        requester_id=interaction.user.id,
        guild_id=interaction.guild.id,
        target_id=target.id,
        target_name=target.display_name,
        avatar_url=target.display_avatar.url,
        entries=entries,
        total_count=total_count,
    )
    await interaction.followup.send(
        view=view,
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )



def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")

    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
