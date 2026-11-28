from __future__ import annotations

import logging
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from banks import (
    BankDetails,
    BankError,
    BankRequestOutcome,
    bank_capacity,
    buy_bank_upgrade,
    cancel_bank_request,
    create_bank,
    decide_bank_request,
    disband_bank,
    get_bank_details,
    get_owned_bank,
    initiate_bank_transfer,
    invite_to_bank,
    leave_bank,
    list_bank_invites,
    next_bank_upgrade,
    pending_bank_request_ids,
    respond_to_bank_invite,
    transfer_bank_ownership,
    update_bank_profile,
)
from database import close_database, initialize_database
from economy import (
    get_leaderboard_page,
    get_or_create_balances,
    get_player_profile,
    get_transaction_history_page,
    has_admin_history_access,
)
from models import Bank

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("fihcoin.bot")
FIHCOIN = "<:fihcoin:1575710572907987064>"
BANK_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
BANK_IMAGE_MAX_BYTES = 8 * 1024 * 1024


class BankRequestView(discord.ui.View):
    """Persistent approval controls delivered only to the current bank owner by DM."""

    def __init__(self, request_id) -> None:
        super().__init__(timeout=None)
        self.request_id = request_id
        approve = discord.ui.Button(
            label="Approve",
            style=discord.ButtonStyle.success,
            custom_id=f"bank_request:{request_id}:approve",
        )
        decline = discord.ui.Button(
            label="Decline",
            style=discord.ButtonStyle.danger,
            custom_id=f"bank_request:{request_id}:decline",
        )
        approve.callback = self.approve
        decline.callback = self.decline
        self.add_item(approve)
        self.add_item(decline)

    async def approve(self, interaction: discord.Interaction) -> None:
        await self._resolve(interaction, approve=True)

    async def decline(self, interaction: discord.Interaction) -> None:
        await self._resolve(interaction, approve=False)

    async def _resolve(self, interaction: discord.Interaction, *, approve: bool) -> None:
        await interaction.response.defer()
        try:
            outcome = await decide_bank_request(
                self.request_id,
                interaction.user.id,
                approve=approve,
            )
        except BankError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        except Exception:
            logger.exception("Failed to process bank request %s", self.request_id)
            await interaction.followup.send(
                "I couldn't process that request. Please try again.",
                ephemeral=True,
            )
            return

        decision = {
            "approved": "approved",
            "declined": "declined",
            "failed": "could not be completed",
            "cancelled": "cancelled",
        }.get(outcome.status, "resolved")
        result_message = (
            f"Bank request {decision}: {outcome.message}\n"
            f"Bank: **{discord.utils.escape_markdown(outcome.bank_name)}**\n"
            f"Action: **{outcome.action.title()} {outcome.amount:,.2f} {FIHCOIN}**"
        )
        await _notify_bank_requester(outcome)
        try:
            await interaction.edit_original_response(
                content=result_message,
                embed=None,
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            logger.exception(
                "Could not update bank request message %s after resolution",
                self.request_id,
            )
            await interaction.followup.send(
                "The request decision was recorded and the requester was notified, "
                "but I could not update this message.",
                ephemeral=True,
            )


class EconomyProfileView(discord.ui.LayoutView):
    """Components V2 profile layout with the member or server icon in its accessory."""

    def __init__(
        self,
        *,
        heading: str,
        description: str,
        avatar_url: str,
        footer: str = f"{FIHCOIN} • Fihcoin • Fish Coin",
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
        guild_name: str,
        avatar_url: str,
        entries: list[tuple[int, object]],
        total_count: int,
        page: int = 1,
    ) -> None:
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.guild_name = guild_name
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
            rankings = "\n".join(lines)

        profile = discord.ui.Section(
            discord.ui.TextDisplay(f"## 🏆 Fihcoin Leaderboard\n-# {self.guild_name}"),
            accessory=discord.ui.Thumbnail(media=self.avatar_url),
        )
        self.add_item(
            discord.ui.Container(
                profile,
                discord.ui.TextDisplay("-# Ranked by combined wallet + bank balance"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(rankings),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"-# Page {self.current_page} of {self.total_pages}"
                    f" • {self.total_count:,} ranked members"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"{FIHCOIN} • Fihcoin • Rankings are server-specific"
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
                    line += f"\n_{discord.utils.escape_markdown(record.note[:160])}{'…' if len(record.note) > 160 else ''}_"
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
        pending_requests = await pending_bank_request_ids()
        for request_id in pending_requests:
            self.add_view(BankRequestView(request_id))
        logger.info("Restored %s pending bank approval views", len(pending_requests))

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
bank_group = app_commands.Group(
    name="bank",
    description="Create and manage server banks.",
)


def bank_details_view(guild: discord.Guild, details: BankDetails) -> discord.ui.LayoutView:
    bank = details.bank
    capacity = bank_capacity(bank.upgrade_level)
    member_mentions = [f"<@{member_id}>" for member_id in details.member_discord_ids]
    member_text = ", ".join(member_mentions) or "No members"
    if details.member_count > len(member_mentions):
        member_text += f" … and {details.member_count - len(member_mentions)} more"
    owner = f"<@{bank.owner_discord_id}>"
    heading = discord.ui.TextDisplay(
        f"## 🏰 {discord.utils.escape_markdown(bank.name)}\n"
        f"-# {discord.utils.escape_markdown(guild.name)}"
    )
    if bank.logo_url:
        heading = discord.ui.Section(
            heading,
            accessory=discord.ui.Thumbnail(
                bank.logo_url,
                description=f"{bank.name} logo",
            ),
        )
    contents = [heading, discord.ui.Separator()]
    if bank.banner_url:
        contents.extend(
            [
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(
                        media=bank.banner_url,
                        description=f"{bank.name} banner",
                    )
                ),
                discord.ui.Separator(),
            ]
        )
    description = (
        f"**Description:** {discord.utils.escape_markdown(bank.description)}\n"
        if bank.description
        else ""
    )
    contents.extend(
        [
            discord.ui.TextDisplay(
                f"{description}"
                f"**Owner:** {owner}\n"
                f"**Members ({details.member_count:,}):** {member_text}\n"
                f"**Vault:** {bank.balance:,.2f} {FIHCOIN} / "
                f"{capacity:,.2f} {FIHCOIN}\n"
                f"**Storage level:** {bank.upgrade_level}"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay("Banks are server-specific"),
        ]
    )
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        discord.ui.Container(
            *contents,
            accent_colour=0x7C3AED,
        )
    )
    return view


async def _notify_bank_requester(outcome: BankRequestOutcome) -> None:
    if outcome.status == "approved":
        status = "approved"
    elif outcome.status == "declined":
        status = "declined"
    elif outcome.status == "failed":
        status = "could not be completed"
    else:
        status = "cancelled"
    message = (
        f"Your {outcome.action} request for **{discord.utils.escape_markdown(outcome.bank_name)}** "
        f"({outcome.amount:,.2f} {FIHCOIN}) was {status}. {outcome.message}"
    )
    try:
        requester = bot.get_user(outcome.requester_discord_id)
        if requester is None:
            requester = await bot.fetch_user(outcome.requester_discord_id)
        await requester.send(message, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.warning(
            "Could not DM requester %s about bank request status %s",
            outcome.requester_discord_id,
            outcome.status,
        )


def _bank_image_filename(attachment: discord.Attachment, slot: str) -> str:
    extension = BANK_IMAGE_TYPES.get(attachment.content_type or "")
    if extension is None:
        raise BankError("Bank banners and logos must be PNG, JPEG, GIF, or WebP images.")
    if attachment.size > BANK_IMAGE_MAX_BYTES:
        raise BankError("Each bank image must be 8 MB or smaller.")
    return f"bank-{slot}{extension}"


def _bank_profile_embed(
    name: str,
    description: Optional[str],
    owner_discord_id: int,
    *,
    banner_url: Optional[str] = None,
    logo_url: Optional[str] = None,
    empty_description: str = "A shared bank has been created.",
) -> discord.Embed:
    embed = discord.Embed(
        title=f"🏦 {discord.utils.escape_markdown(name)}",
        description=(
            discord.utils.escape_markdown(description)
            if description
            else empty_description
        ),
        colour=discord.Colour.gold(),
    )
    embed.add_field(name="Owner", value=f"<@{owner_discord_id}>")
    if banner_url:
        embed.set_image(url=banner_url)
    if logo_url:
        embed.set_thumbnail(url=logo_url)
    return embed


async def _delete_profile_message(message: discord.Message, context: str) -> bool:
    try:
        await message.delete()
        return True
    except discord.HTTPException:
        logger.exception("Could not remove %s bank profile message", context)
        return False


class BankCreateModal(discord.ui.Modal):
    def __init__(self, guild_id: int, owner_discord_id: int) -> None:
        super().__init__(title="Create a bank")
        self.guild_id = guild_id
        self.owner_discord_id = owner_discord_id
        self.name_input = discord.ui.TextInput(
            custom_id="bank_name",
            placeholder="A unique name (2-32 characters)",
            min_length=2,
            max_length=32,
        )
        self.description_input = discord.ui.TextInput(
            custom_id="bank_description",
            style=discord.TextStyle.paragraph,
            placeholder="What is this bank for? (optional)",
            required=False,
            max_length=500,
        )
        self.banner_upload = discord.ui.FileUpload(
            custom_id="bank_banner",
            required=False,
            min_values=0,
            max_values=1,
        )
        self.logo_upload = discord.ui.FileUpload(
            custom_id="bank_logo",
            required=False,
            min_values=0,
            max_values=1,
        )
        self.add_item(
            discord.ui.Label(
                text="Bank name",
                description="Required",
                component=self.name_input,
            )
        )
        self.add_item(
            discord.ui.Label(
                text="Description",
                description="Optional, up to 500 characters",
                component=self.description_input,
            )
        )
        self.add_item(
            discord.ui.Label(
                text="Banner image",
                description="Optional PNG, JPEG, GIF, or WebP; up to 8 MB",
                component=self.banner_upload,
            )
        )
        self.add_item(
            discord.ui.Label(
                text="Logo image",
                description="Optional PNG, JPEG, GIF, or WebP; up to 8 MB",
                component=self.logo_upload,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if (
            interaction.guild is None
            or interaction.guild.id != self.guild_id
            or interaction.user.id != self.owner_discord_id
        ):
            await interaction.response.send_message(
                "This bank form is only valid for its original server member.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = interaction.channel
        if channel is None:
            await interaction.followup.send(
                "I couldn't find the server channel to post the bank profile.",
                ephemeral=True,
            )
            return

        description = (self.description_input.value or "").strip() or None
        banner = self.banner_upload.values[0] if self.banner_upload.values else None
        logo = self.logo_upload.values[0] if self.logo_upload.values else None
        files: list[discord.File] = []
        filenames: dict[str, str] = {}
        try:
            if banner is not None:
                filenames["banner"] = _bank_image_filename(banner, "banner")
            if logo is not None:
                filenames["logo"] = _bank_image_filename(logo, "logo")
            if banner is not None:
                files.append(await banner.to_file(filename=filenames["banner"]))
            if logo is not None:
                files.append(await logo.to_file(filename=filenames["logo"]))
        except BankError as error:
            for file in files:
                file.close()
            await interaction.followup.send(str(error), ephemeral=True)
            return
        except discord.HTTPException:
            for file in files:
                file.close()
            logger.exception("Failed to retrieve bank image uploads for user %s", interaction.user.id)
            await interaction.followup.send(
                "I couldn't read one of those image uploads. Please try again.",
                ephemeral=True,
            )
            return
        except Exception:
            for file in files:
                file.close()
            logger.exception("Unexpected error retrieving bank image uploads for user %s", interaction.user.id)
            await interaction.followup.send(
                "I couldn't read one of those image uploads. Please try again.",
                ephemeral=True,
            )
            return

        name = self.name_input.value
        embed = _bank_profile_embed(
            name,
            description,
            self.owner_discord_id,
            banner_url=(
                f"attachment://{filenames['banner']}"
                if "banner" in filenames
                else None
            ),
            logo_url=(
                f"attachment://{filenames['logo']}"
                if "logo" in filenames
                else None
            ),
        )

        try:
            profile_message = await channel.send(
                embed=embed,
                files=files,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            logger.exception("Failed to post bank profile for user %s", interaction.user.id)
            await interaction.followup.send(
                "I couldn't upload the bank profile, so the bank was not created.",
                ephemeral=True,
            )
            return
        except Exception:
            logger.exception("Unexpected error posting bank profile for user %s", interaction.user.id)
            await interaction.followup.send(
                "I couldn't upload the bank profile, so the bank was not created.",
                ephemeral=True,
            )
            return
        finally:
            for file in files:
                file.close()

        uploaded_urls = {
            attachment.filename: attachment.url
            for attachment in profile_message.attachments
        }
        missing_uploads = [
            filename
            for filename in filenames.values()
            if filename not in uploaded_urls
        ]
        if missing_uploads:
            removed = await _delete_profile_message(profile_message, "incomplete creation")
            message = "Discord did not retain all uploaded images, so the bank was not created."
            if not removed:
                message += " A server moderator may need to remove the profile post."
            await interaction.followup.send(message, ephemeral=True)
            return
        try:
            bank = await create_bank(
                self.guild_id,
                self.owner_discord_id,
                name,
                description=description,
                banner_url=uploaded_urls.get(filenames.get("banner", "")),
                logo_url=uploaded_urls.get(filenames.get("logo", "")),
            )
        except BankError as error:
            removed = await _delete_profile_message(profile_message, "failed creation")
            if not removed:
                error_message = (
                    f"{error} I couldn't remove the temporary profile post; "
                    "a server moderator may need to remove it."
                )
            else:
                error_message = str(error)
            await interaction.followup.send(error_message, ephemeral=True)
            return
        except Exception:
            logger.exception("Failed to create bank for user %s", interaction.user.id)
            await interaction.followup.send(
                "I couldn't confirm whether the bank was created. Check `/bank view` "
                "before retrying; its profile post may already be visible.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"🏰 **{discord.utils.escape_markdown(bank.name)}** was created. You are its owner.",
            ephemeral=True,
        )


@bank_group.command(name="create", description="Open the bank creation form.")
@app_commands.guild_only()
async def bank_create(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "Banks are only available in a server.",
            ephemeral=True,
        )
        return
    await interaction.response.send_modal(
        BankCreateModal(interaction.guild.id, interaction.user.id)
    )


class BankEditModal(discord.ui.Modal):
    def __init__(self, guild_id: int, owner_discord_id: int, bank: Bank) -> None:
        super().__init__(title="Edit your bank")
        self.guild_id = guild_id
        self.owner_discord_id = owner_discord_id
        self.bank = bank
        self.name_input = discord.ui.TextInput(
            custom_id="bank_edit_name",
            default=bank.name,
            min_length=2,
            max_length=32,
        )
        self.description_input = discord.ui.TextInput(
            custom_id="bank_edit_description",
            style=discord.TextStyle.paragraph,
            default=bank.description or "",
            placeholder="Leave empty to remove the description",
            required=False,
            max_length=500,
        )
        self.banner_upload = discord.ui.FileUpload(
            custom_id="bank_edit_banner",
            required=False,
            min_values=0,
            max_values=1,
        )
        self.logo_upload = discord.ui.FileUpload(
            custom_id="bank_edit_logo",
            required=False,
            min_values=0,
            max_values=1,
        )
        self.add_item(
            discord.ui.Label(
                text="Bank name",
                description="Required; the current name is prefilled",
                component=self.name_input,
            )
        )
        self.add_item(
            discord.ui.Label(
                text="Description",
                description="Edit the text or clear it; up to 500 characters",
                component=self.description_input,
            )
        )
        self.add_item(
            discord.ui.Label(
                text="Banner image",
                description="Upload a replacement or leave empty to keep it",
                component=self.banner_upload,
            )
        )
        self.add_item(
            discord.ui.Label(
                text="Logo image",
                description="Upload a replacement or leave empty to keep it",
                component=self.logo_upload,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if (
            interaction.guild is None
            or interaction.guild.id != self.guild_id
            or interaction.user.id != self.owner_discord_id
        ):
            await interaction.response.send_message(
                "This bank form is only valid for its original server member.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = interaction.channel
        if channel is None:
            await interaction.followup.send(
                "I couldn't find the server channel to post the updated bank profile.",
                ephemeral=True,
            )
            return

        banner = self.banner_upload.values[0] if self.banner_upload.values else None
        logo = self.logo_upload.values[0] if self.logo_upload.values else None
        files: list[discord.File] = []
        filenames: dict[str, str] = {}
        try:
            if banner is not None:
                filenames["banner"] = _bank_image_filename(banner, "banner")
            if logo is not None:
                filenames["logo"] = _bank_image_filename(logo, "logo")
            if banner is not None:
                files.append(await banner.to_file(filename=filenames["banner"]))
            if logo is not None:
                files.append(await logo.to_file(filename=filenames["logo"]))
        except BankError as error:
            for file in files:
                file.close()
            await interaction.followup.send(str(error), ephemeral=True)
            return
        except Exception:
            for file in files:
                file.close()
            logger.exception(
                "Failed to retrieve bank edit image uploads for user %s",
                interaction.user.id,
            )
            await interaction.followup.send(
                "I couldn't read one of those image uploads. Please try again.",
                ephemeral=True,
            )
            return

        banner_source = (
            f"attachment://{filenames['banner']}"
            if banner is not None
            else self.bank.banner_url
        )
        logo_source = (
            f"attachment://{filenames['logo']}"
            if logo is not None
            else self.bank.logo_url
        )
        embed = _bank_profile_embed(
            self.name_input.value,
            (self.description_input.value or "").strip() or None,
            self.owner_discord_id,
            banner_url=banner_source,
            logo_url=logo_source,
            empty_description="Bank profile updated.",
        )
        try:
            profile_message = await channel.send(
                embed=embed,
                files=files,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception:
            logger.exception("Failed to post edited bank profile for user %s", interaction.user.id)
            await interaction.followup.send(
                "I couldn't post the updated bank profile, so no changes were saved.",
                ephemeral=True,
            )
            return
        finally:
            for file in files:
                file.close()

        uploaded_urls = {
            attachment.filename: attachment.url
            for attachment in profile_message.attachments
        }
        missing_uploads = [
            filename
            for filename in filenames.values()
            if filename not in uploaded_urls
        ]
        if missing_uploads:
            removed = await _delete_profile_message(profile_message, "incomplete edit")
            message = "Discord did not retain all uploaded images, so no profile changes were saved."
            if not removed:
                message += " A server moderator may need to remove the profile post."
            await interaction.followup.send(message, ephemeral=True)
            return
        try:
            bank = await update_bank_profile(
                self.guild_id,
                self.owner_discord_id,
                self.name_input.value,
                description=(self.description_input.value or "").strip() or None,
                banner_url=(
                    uploaded_urls[filenames["banner"]]
                    if banner is not None
                    else None
                ),
                logo_url=(
                    uploaded_urls[filenames["logo"]]
                    if logo is not None
                    else None
                ),
            )
        except BankError as error:
            removed = await _delete_profile_message(profile_message, "failed edit")
            if not removed:
                error_message = (
                    f"{error} I couldn't remove the temporary profile post; "
                    "a server moderator may need to remove it."
                )
            else:
                error_message = str(error)
            await interaction.followup.send(error_message, ephemeral=True)
            return
        except Exception:
            logger.exception("Failed to save edited bank profile for user %s", interaction.user.id)
            await interaction.followup.send(
                "I couldn't confirm whether the profile changes were saved. "
                "Check `/bank view` before retrying; the updated profile post may be visible.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"🏦 **{discord.utils.escape_markdown(bank.name)}** was updated. "
            "Use `/bank view` to see the current profile.",
            ephemeral=True,
        )


class BankEditConfirmationView(discord.ui.View):
    def __init__(self, guild_id: int, owner_discord_id: int, bank: Bank) -> None:
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.owner_discord_id = owner_discord_id
        self.bank = bank
        self.form_opened = False

    @discord.ui.button(label="Yes, edit bank", style=discord.ButtonStyle.primary)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.user.id != self.owner_discord_id:
            await interaction.response.send_message(
                "Only the bank owner can edit this bank.",
                ephemeral=True,
            )
            return
        if self.form_opened:
            await interaction.response.send_message(
                "The edit form has already been opened. Run `/bank edit` again if it was closed.",
                ephemeral=True,
            )
            return
        self.form_opened = True
        await interaction.response.send_modal(
            BankEditModal(self.guild_id, self.owner_discord_id, self.bank)
        )

    @discord.ui.button(label="No, cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.user.id != self.owner_discord_id:
            await interaction.response.send_message(
                "Only the bank owner can cancel this prompt.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            content="Bank edit cancelled.",
            view=None,
        )


@bank_group.command(name="edit", description="Edit your bank profile.")
@app_commands.guild_only()
async def bank_edit(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "Banks are only available in a server.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        bank = await get_owned_bank(interaction.guild.id, interaction.user.id)
    except Exception:
        logger.exception("Failed to load bank edit prompt for user %s", interaction.user.id)
        await interaction.followup.send("I couldn't load your bank profile right now.", ephemeral=True)
        return
    if bank is None:
        await interaction.followup.send(
            "Only the owner of a bank can edit it. Create a bank or ask its owner to transfer ownership.",
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        f"Do you want to edit **{discord.utils.escape_markdown(bank.name)}**? "
        "Confirm to open the form, or cancel to leave it unchanged. "
        "Empty image uploads keep the current images.",
        view=BankEditConfirmationView(interaction.guild.id, interaction.user.id, bank),
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bank_group.command(name="invite", description="Invite a member to the bank you own.")
@app_commands.guild_only()
@app_commands.describe(member="The server member to invite.")
async def bank_invite(interaction: discord.Interaction, member: discord.Member) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Banks are only available in a server.")
        return
    await interaction.response.defer(thinking=True)
    try:
        bank_name = await invite_to_bank(interaction.guild.id, interaction.user.id, member.id)
    except BankError as error:
        await interaction.followup.send(str(error))
        return
    except Exception:
        logger.exception("Failed to create bank invite for user %s", member.id)
        await interaction.followup.send("I couldn't send that bank invite right now. Please try again.")
        return
    await interaction.followup.send(
        f"🏰 <@{member.id}> was invited to **{discord.utils.escape_markdown(bank_name)}**. "
        f"They can use `/bank invites`, then `/bank accept` or `/bank decline`."
    )


@bank_group.command(name="invites", description="View your pending bank invitations.")
@app_commands.guild_only()
async def bank_invites(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Banks are only available in a server.")
        return
    await interaction.response.defer(thinking=True)
    try:
        invites = await list_bank_invites(interaction.guild.id, interaction.user.id)
    except Exception:
        logger.exception("Failed to retrieve bank invites for user %s", interaction.user.id)
        await interaction.followup.send("I couldn't retrieve your bank invites right now.")
        return
    if not invites:
        await interaction.followup.send("You have no pending bank invitations.")
        return
    lines = [
        f"• **{discord.utils.escape_markdown(invite.bank_name)}** — invited by "
        f"<@{invite.inviter_discord_id}> (<t:{int(invite.created_at.timestamp())}:R>)"
        for invite in invites
    ]
    await interaction.followup.send("## 🏰 Your bank invitations\n" + "\n".join(lines))


async def _bank_invite_decision(
    interaction: discord.Interaction,
    bank_name: str,
    *,
    accept: bool,
) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Banks are only available in a server.")
        return
    await interaction.response.defer(thinking=True)
    try:
        resolved_name = await respond_to_bank_invite(
            interaction.guild.id,
            interaction.user.id,
            bank_name,
            accept=accept,
        )
    except BankError as error:
        await interaction.followup.send(str(error))
        return
    except Exception:
        logger.exception("Failed to respond to bank invite for user %s", interaction.user.id)
        await interaction.followup.send("I couldn't process that bank invite right now.")
        return
    if accept:
        await interaction.followup.send(
            f"🏰 You joined **{discord.utils.escape_markdown(resolved_name)}**."
        )
    else:
        await interaction.followup.send(
            f"You declined the invitation to **{discord.utils.escape_markdown(resolved_name)}**."
        )


@bank_group.command(name="accept", description="Accept an invitation to a bank.")
@app_commands.guild_only()
@app_commands.describe(bank_name="The bank name shown by `/bank invites`.")
async def bank_accept(interaction: discord.Interaction, bank_name: str) -> None:
    await _bank_invite_decision(interaction, bank_name, accept=True)


@bank_group.command(name="decline", description="Decline an invitation to a bank.")
@app_commands.guild_only()
@app_commands.describe(bank_name="The bank name shown by `/bank invites`.")
async def bank_decline(interaction: discord.Interaction, bank_name: str) -> None:
    await _bank_invite_decision(interaction, bank_name, accept=False)


@bank_group.command(name="view", description="View your bank or look up a bank by name.")
@app_commands.guild_only()
@app_commands.describe(bank_name="Optional bank name to look up.")
async def bank_view(
    interaction: discord.Interaction,
    bank_name: Optional[str] = None,
) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Banks are only available in a server.")
        return
    await interaction.response.defer(thinking=True)
    try:
        details = await get_bank_details(interaction.guild.id, interaction.user.id, bank_name)
    except BankError as error:
        await interaction.followup.send(str(error))
        return
    except Exception:
        logger.exception("Failed to retrieve bank details in guild %s", interaction.guild.id)
        await interaction.followup.send("I couldn't retrieve that bank right now.")
        return
    if details is None:
        message = (
            f"No bank named **{discord.utils.escape_markdown(bank_name)}** exists in this server."
            if bank_name
            else "You are not in a bank yet. Create one with `/bank create` or view a bank by name."
        )
        await interaction.followup.send(message)
        return
    await interaction.followup.send(
        view=bank_details_view(interaction.guild, details),
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def _request_bank_transfer(
    interaction: discord.Interaction,
    action: str,
    amount: str,
) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "Banks are only available in a server.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        outcome = await initiate_bank_transfer(
            interaction.guild.id,
            interaction.user.id,
            action,
            amount,
        )
    except BankError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return
    except Exception:
        logger.exception(
            "Failed to process bank %s for user %s",
            action,
            interaction.user.id,
        )
        await interaction.followup.send(
            f"I couldn't process that {action} right now. Please try again.",
            ephemeral=True,
        )
        return

    if outcome.request_id is None:
        if outcome.balance_after is None:
            logger.error(
                "Bank %s completed without a resulting balance for user %s",
                action,
                interaction.user.id,
            )
            await interaction.followup.send(
                "Your transaction completed, but I couldn't retrieve the updated vault balance.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f"Your {action} of **{outcome.amount:,.2f} {FIHCOIN}** "
            f"was completed. The bank vault now holds **{outcome.balance_after:,.2f} "
            f"{FIHCOIN}**.",
            ephemeral=True,
        )
        return

    try:
        owner = bot.get_user(outcome.owner_discord_id)
        if owner is None:
            owner = await bot.fetch_user(outcome.owner_discord_id)
        request_view = BankRequestView(outcome.request_id)
        await owner.send(
            embed=discord.Embed(
                title=f"Bank {action} approval",
                description=(
                    f"<@{interaction.user.id}> requests to **{action}** "
                    f"**{outcome.amount:,.2f} {FIHCOIN}** "
                    f"{'into' if action == 'deposit' else 'from'} "
                    f"**{discord.utils.escape_markdown(outcome.bank_name)}**."
                ),
                colour=discord.Colour.gold(),
            ),
            view=request_view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException:
        logger.warning(
            "Could not DM bank owner %s about request %s",
            outcome.owner_discord_id,
            outcome.request_id,
        )
        cancelled = True
        try:
            await cancel_bank_request(outcome.request_id)
        except Exception:
            cancelled = False
            logger.exception(
                "Could not cancel undelivered bank request %s",
                outcome.request_id,
            )
        if cancelled:
            await interaction.followup.send(
                "I couldn't DM the bank owner, so the request was cancelled. "
                "The owner may need to enable direct messages from server members.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "I couldn't DM the bank owner, and could not confirm cancellation. "
                "The request may still be pending; please contact the bank owner "
                "before submitting another request.",
                ephemeral=True,
            )
        return

    await interaction.followup.send(
        f"Your {action} request for **{outcome.amount:,.2f} {FIHCOIN}** "
        f"was sent privately to the bank owner for approval.",
        ephemeral=True,
    )


@bank_group.command(name="deposit", description="Deposit currency into your bank.")
@app_commands.guild_only()
@app_commands.describe(amount="Amount to deposit, with up to two decimal places.")
async def bank_deposit(interaction: discord.Interaction, amount: str) -> None:
    await _request_bank_transfer(interaction, "deposit", amount)


@bank_group.command(name="withdraw", description="Withdraw currency from your bank.")
@app_commands.guild_only()
@app_commands.describe(amount="Amount to withdraw, with up to two decimal places.")
async def bank_withdraw(interaction: discord.Interaction, amount: str) -> None:
    await _request_bank_transfer(interaction, "withdraw", amount)


@bank_group.command(name="shop", description="View available bank storage upgrades.")
@app_commands.guild_only()
async def bank_shop(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "Banks are only available in a server.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        details = await get_bank_details(interaction.guild.id, interaction.user.id)
    except Exception:
        logger.exception("Failed to load bank shop for user %s", interaction.user.id)
        await interaction.followup.send("I couldn't load the bank shop right now.", ephemeral=True)
        return
    if details is None:
        await interaction.followup.send(
            "Join a bank before viewing its storage upgrades.",
            ephemeral=True,
        )
        return

    bank = details.bank
    capacity = bank_capacity(bank.upgrade_level)
    upgrade = next_bank_upgrade(bank.upgrade_level)
    if upgrade is None:
        upgrade_text = "This bank has reached the maximum storage level."
    else:
        next_level, next_capacity, cost = upgrade
        upgrade_text = (
            f"**Next upgrade:** Level {next_level}\n"
            f"**New capacity:** {next_capacity:,.2f} {FIHCOIN}\n"
            f"**Price:** {cost:,.2f} {FIHCOIN} from the owner's wallet\n"
            f"Purchase with `/bank upgrade`."
        )
    await interaction.followup.send(
        f"## 🏦 {discord.utils.escape_markdown(bank.name)} Bank Shop\n"
        f"**Current level:** {bank.upgrade_level}/{10}\n"
        f"**Vault:** {bank.balance:,.2f} / {capacity:,.2f} {FIHCOIN}\n\n"
        f"{upgrade_text}\n\n"
        f"Only the bank owner can purchase upgrades.",
        ephemeral=True,
    )


@bank_group.command(name="upgrade", description="Buy the next bank storage upgrade.")
@app_commands.guild_only()
async def bank_upgrade(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "Banks are only available in a server.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        bank_name, level, capacity, cost = await buy_bank_upgrade(
            interaction.guild.id,
            interaction.user.id,
        )
    except BankError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return
    except Exception:
        logger.exception("Failed to buy bank upgrade for user %s", interaction.user.id)
        await interaction.followup.send("I couldn't purchase that upgrade right now.", ephemeral=True)
        return
    await interaction.followup.send(
        f"🏦 **{discord.utils.escape_markdown(bank_name)}** upgraded to level **{level}/10**. "
        f"Capacity is now **{capacity:,.2f} {FIHCOIN}**. "
        f"Paid **{cost:,.2f} {FIHCOIN}** from your wallet.",
        ephemeral=True,
    )


@bank_group.command(name="transfer-owner", description="Transfer your bank to a current member.")
@app_commands.guild_only()
@app_commands.describe(member="The current bank member who will become the owner.")
async def bank_transfer_owner(interaction: discord.Interaction, member: discord.Member) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "Banks are only available in a server.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        bank_name = await transfer_bank_ownership(
            interaction.guild.id,
            interaction.user.id,
            member.id,
        )
    except BankError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return
    except Exception:
        logger.exception("Failed to transfer bank ownership for user %s", interaction.user.id)
        await interaction.followup.send("I couldn't transfer ownership right now.", ephemeral=True)
        return
    await interaction.followup.send(
        f"**{discord.utils.escape_markdown(bank_name)}** is now owned by <@{member.id}>. "
        "You can leave the bank with `/bank leave`.",
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bank_group.command(name="leave", description="Leave your current bank.")
@app_commands.guild_only()
async def bank_leave(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Banks are only available in a server.")
        return
    await interaction.response.defer(thinking=True)
    try:
        bank_name = await leave_bank(interaction.guild.id, interaction.user.id)
    except BankError as error:
        await interaction.followup.send(str(error))
        return
    except Exception:
        logger.exception("Failed to remove user %s from their bank", interaction.user.id)
        await interaction.followup.send("I couldn't remove you from your bank right now.")
        return
    await interaction.followup.send(
        f"You left **{discord.utils.escape_markdown(bank_name)}**."
    )


@bank_group.command(name="disband", description="Disband the bank you own.")
@app_commands.guild_only()
@app_commands.describe(confirmation_name="Type your bank's exact name to confirm.")
async def bank_disband(interaction: discord.Interaction, confirmation_name: str) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Banks are only available in a server.")
        return
    await interaction.response.defer(thinking=True)
    try:
        bank_name = await disband_bank(
            interaction.guild.id,
            interaction.user.id,
            confirmation_name,
        )
    except BankError as error:
        await interaction.followup.send(str(error))
        return
    except Exception:
        logger.exception("Failed to disband bank for user %s", interaction.user.id)
        await interaction.followup.send("I couldn't disband that bank right now.")
        return
    await interaction.followup.send(
        f"🏰 **{discord.utils.escape_markdown(bank_name)}** was disbanded. "
        "Its members and pending invites were removed."
    )


bot.tree.add_command(bank_group)


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
    user: Optional[discord.Member] = None,
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
    name="profile",
    description="View your Fihcoin profile or look up another server member.",
)
@app_commands.guild_only()
@app_commands.describe(user="The server member whose profile you want to view.")
async def profile(
    interaction: discord.Interaction,
    user: Optional[discord.Member] = None,
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
        wallet, bank, total, rank, created_at, transaction_count = await get_player_profile(
            guild_id=interaction.guild.id,
            discord_user_id=target.id,
        )
    except Exception:
        logger.exception("Failed to retrieve Fihcoin profile for Discord user %s", target.id)
        await interaction.followup.send(
            "I couldn't retrieve that profile right now. Please try again shortly."
        )
        return

    account_created = (
        f"<t:{int(created_at.timestamp())}:D>"
        if created_at is not None
        else "Unavailable"
    )
    view = EconomyProfileView(
        heading=f"🎃 {target.display_name}'s Fihcoin Profile",
        description="",
        description_sections=(
            f"**Member:** {target.mention}\n"
            f"**Account created:** {account_created}",
            f"**Wallet:** {wallet:,.2f} {FIHCOIN}\n"
            f"**Bank:** {bank:,.2f} {FIHCOIN}\n"
            f"**Total:** **{total:,.2f} {FIHCOIN}**\n"
            f"**Leaderboard rank:** #{rank:,}\n"
            f"**Transactions:** {transaction_count:,}",
        ),
        avatar_url=target.display_avatar.url,
        footer=f"{FIHCOIN} • Fihcoin • Rankings are server-specific",
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
        guild_name=interaction.guild.name,
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
    user: Optional[discord.Member] = None,
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
