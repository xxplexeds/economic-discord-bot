from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import NamedTuple, Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from database import session_scope
from economy import get_or_create_balances, record_transaction
from models import (
    Account,
    Bank,
    BankInvite,
    BankMembership,
    BankRequest,
    BankTransaction,
    Player,
)

BANK_STARTING_CAPACITY = Decimal("100000.00")
BANK_STARTING_UPGRADE_COST = Decimal("125000.00")
BANK_UPGRADE_MULTIPLIER = Decimal("1.5")
BANK_MAX_LEVEL = 10
MONEY_CENT = Decimal("0.01")
FIHCOIN = "<:fihcoin:1575710572907987064>"


class BankError(ValueError):
    """An expected bank action that cannot be completed."""


class BankInviteDetails(NamedTuple):
    bank_name: str
    inviter_discord_id: int
    created_at: datetime


class BankTransferOutcome(NamedTuple):
    bank_name: str
    action: str
    amount: Decimal
    balance_after: Optional[Decimal]
    capacity: Decimal
    owner_discord_id: int
    request_id: Optional[UUID]


class BankRequestOutcome(NamedTuple):
    bank_name: str
    action: str
    amount: Decimal
    requester_discord_id: int
    status: str
    balance_after: Optional[Decimal]
    message: str


def bank_capacity(level: int) -> Decimal:
    if not 1 <= level <= BANK_MAX_LEVEL:
        raise BankError("That bank upgrade level is invalid.")
    return (BANK_STARTING_CAPACITY * BANK_UPGRADE_MULTIPLIER ** (level - 1)).quantize(MONEY_CENT)


def next_bank_upgrade(level: int) -> Optional[tuple[int, Decimal, Decimal]]:
    if not 1 <= level <= BANK_MAX_LEVEL:
        raise BankError("That bank upgrade level is invalid.")
    if level >= BANK_MAX_LEVEL:
        return None
    new_level = level + 1
    cost = (
        BANK_STARTING_UPGRADE_COST * BANK_UPGRADE_MULTIPLIER ** (level - 1)
    ).quantize(MONEY_CENT)
    return new_level, bank_capacity(new_level), cost


def parse_bank_amount(value: str) -> Decimal:
    try:
        amount = Decimal(value.strip())
    except (AttributeError, InvalidOperation) as error:
        raise BankError("Enter a valid currency amount, such as `250` or `250.50`.") from error
    if (
        not amount.is_finite()
        or amount <= 0
        or amount > Decimal("999999999999999999.99")
    ):
        raise BankError("Enter a positive amount within the supported currency range.")
    try:
        has_extra_precision = amount.quantize(MONEY_CENT) != amount
    except InvalidOperation as error:
        raise BankError("Enter a valid currency amount, such as `250` or `250.50`.") from error
    if has_extra_precision:
        raise BankError("Amounts must be positive and have no more than two decimal places.")
    return amount


def normalize_bank_name(name: str) -> tuple[str, str]:
    cleaned = " ".join(name.split())
    if not 2 <= len(cleaned) <= 32:
        raise BankError("Bank names must be between 2 and 32 characters.")
    if not all(character.isprintable() for character in cleaned):
        raise BankError("Bank names must use printable characters.")
    return cleaned, unicodedata.normalize("NFKC", cleaned).casefold()


async def create_bank(
    guild_id: int,
    owner_discord_id: int,
    name: str,
    *,
    description: Optional[str] = None,
    banner_url: Optional[str] = None,
    logo_url: Optional[str] = None,
) -> Bank:
    bank_name, normalized_name = normalize_bank_name(name)
    description = description.strip() if description else None
    if description is not None and len(description) > 500:
        raise BankError("Bank descriptions must be 500 characters or fewer.")
    try:
        async with session_scope() as session:
            async with session.begin():
                existing_membership = await session.scalar(
                    select(BankMembership.id).where(
                        BankMembership.guild_id == guild_id,
                        BankMembership.discord_user_id == owner_discord_id,
                    )
                )
                if existing_membership is not None:
                    raise BankError("You must leave your current bank before creating another.")

                existing_bank = await session.scalar(
                    select(Bank.id).where(
                        Bank.guild_id == guild_id,
                        Bank.normalized_name == normalized_name,
                    )
                )
                if existing_bank is not None:
                    raise BankError("A bank with that name already exists in this server.")

                bank = Bank(
                    guild_id=guild_id,
                    name=bank_name,
                    normalized_name=normalized_name,
                    owner_discord_id=owner_discord_id,
                    description=description or None,
                    banner_url=banner_url,
                    logo_url=logo_url,
                )
                session.add(bank)
                await session.flush()
                session.add(
                    BankMembership(
                        guild_id=guild_id,
                        bank_id=bank.id,
                        discord_user_id=owner_discord_id,
                    )
                )
    except IntegrityError as error:
        raise BankError(
            "A bank with that name exists, or you already belong to a bank. Please try again."
        ) from error
    return bank


async def update_bank_profile(
    guild_id: int,
    owner_discord_id: int,
    name: str,
    *,
    description: Optional[str],
    banner_url: Optional[str] = None,
    logo_url: Optional[str] = None,
) -> Bank:
    bank_name, normalized_name = normalize_bank_name(name)
    description = description.strip() if description else None
    if description is not None and len(description) > 500:
        raise BankError("Bank descriptions must be 500 characters or fewer.")
    try:
        async with session_scope() as session:
            async with session.begin():
                bank = await session.scalar(
                    select(Bank)
                    .where(
                        Bank.guild_id == guild_id,
                        Bank.owner_discord_id == owner_discord_id,
                    )
                    .with_for_update()
                )
                if bank is None:
                    raise BankError("Only the current bank owner can edit the bank profile.")
                duplicate = await session.scalar(
                    select(Bank.id).where(
                        Bank.guild_id == guild_id,
                        Bank.normalized_name == normalized_name,
                        Bank.id != bank.id,
                    )
                )
                if duplicate is not None:
                    raise BankError("A bank with that name already exists in this server.")

                bank.name = bank_name
                bank.normalized_name = normalized_name
                bank.description = description
                if banner_url is not None:
                    bank.banner_url = banner_url
                if logo_url is not None:
                    bank.logo_url = logo_url
                return bank
    except IntegrityError as error:
        raise BankError("A bank with that name already exists in this server.") from error


async def invite_to_bank(
    guild_id: int,
    inviter_discord_id: int,
    invitee_discord_id: int,
) -> str:
    if inviter_discord_id == invitee_discord_id:
        raise BankError("You cannot invite yourself.")

    try:
        async with session_scope() as session:
            async with session.begin():
                bank = await session.scalar(
                    select(Bank)
                    .where(
                        Bank.guild_id == guild_id,
                        Bank.owner_discord_id == inviter_discord_id,
                    )
                    .with_for_update()
                )
                if bank is None:
                    raise BankError("Only a bank owner can invite members.")

                membership = await session.scalar(
                    select(BankMembership.id).where(
                        BankMembership.guild_id == guild_id,
                        BankMembership.discord_user_id == invitee_discord_id,
                    )
                )
                if membership is not None:
                    raise BankError("That member already belongs to a bank in this server.")

                invite = await session.scalar(
                    select(BankInvite)
                    .where(
                        BankInvite.guild_id == guild_id,
                        BankInvite.bank_id == bank.id,
                        BankInvite.invitee_discord_id == invitee_discord_id,
                    )
                    .with_for_update()
                )
                if invite is not None and invite.status == "pending":
                    raise BankError("That member already has a pending invite to your bank.")
                if invite is None:
                    session.add(
                        BankInvite(
                            guild_id=guild_id,
                            bank_id=bank.id,
                            inviter_discord_id=inviter_discord_id,
                            invitee_discord_id=invitee_discord_id,
                        )
                    )
                else:
                    invite.inviter_discord_id = inviter_discord_id
                    invite.status = "pending"
                    invite.created_at = datetime.now(timezone.utc)
                return bank.name
    except IntegrityError as error:
        raise BankError("That member already has an invite or joined a bank. Please try again.") from error


async def list_bank_invites(
    guild_id: int,
    invitee_discord_id: int,
) -> list[BankInviteDetails]:
    async with session_scope() as session:
        result = await session.execute(
            select(Bank.name, BankInvite.inviter_discord_id, BankInvite.created_at)
            .join(Bank, Bank.id == BankInvite.bank_id)
            .where(
                BankInvite.guild_id == guild_id,
                BankInvite.invitee_discord_id == invitee_discord_id,
                BankInvite.status == "pending",
            )
            .order_by(BankInvite.created_at, Bank.name)
        )
        return [
            BankInviteDetails(name, inviter_id, created_at)
            for name, inviter_id, created_at in result.all()
        ]


async def respond_to_bank_invite(
    guild_id: int,
    invitee_discord_id: int,
    bank_name: str,
    *,
    accept: bool,
) -> str:
    _, normalized_name = normalize_bank_name(bank_name)
    try:
        async with session_scope() as session:
            async with session.begin():
                result = await session.execute(
                    select(BankInvite, Bank)
                    .join(Bank, Bank.id == BankInvite.bank_id)
                    .where(
                        BankInvite.guild_id == guild_id,
                        BankInvite.invitee_discord_id == invitee_discord_id,
                        BankInvite.status == "pending",
                        Bank.normalized_name == normalized_name,
                    )
                    .with_for_update(of=BankInvite)
                )
                invite, bank = result.one_or_none() or (None, None)
                if invite is None or bank is None:
                    raise BankError("You do not have a pending invite from that bank.")

                if accept:
                    membership = await session.scalar(
                        select(BankMembership.id).where(
                            BankMembership.guild_id == guild_id,
                            BankMembership.discord_user_id == invitee_discord_id,
                        )
                    )
                    if membership is not None:
                        raise BankError("You already belong to a bank in this server.")
                    session.add(
                        BankMembership(
                            guild_id=guild_id,
                            bank_id=bank.id,
                            discord_user_id=invitee_discord_id,
                        )
                    )
                    invite.status = "accepted"
                    await session.execute(
                        update(BankInvite)
                        .where(
                            BankInvite.guild_id == guild_id,
                            BankInvite.invitee_discord_id == invitee_discord_id,
                            BankInvite.status == "pending",
                            BankInvite.id != invite.id,
                        )
                        .values(status="cancelled")
                    )
                else:
                    invite.status = "declined"
                return bank.name
    except IntegrityError as error:
        raise BankError(
            "You joined another bank at the same time. Check your current bank and try again."
        ) from error


async def leave_bank(guild_id: int, discord_user_id: int) -> str:
    async with session_scope() as session:
        async with session.begin():
            result = await session.execute(
                select(BankMembership, Bank)
                .join(Bank, Bank.id == BankMembership.bank_id)
                .where(
                    BankMembership.guild_id == guild_id,
                    BankMembership.discord_user_id == discord_user_id,
                )
                .with_for_update(of=BankMembership)
            )
            membership, bank = result.one_or_none() or (None, None)
            if membership is None or bank is None:
                raise BankError("You are not in a bank in this server.")
            if bank.owner_discord_id == discord_user_id:
                raise BankError(
                    "Transfer bank ownership to another member before leaving."
                )
            await session.delete(membership)
            return bank.name


async def transfer_bank_ownership(
    guild_id: int,
    owner_discord_id: int,
    new_owner_discord_id: int,
) -> str:
    if owner_discord_id == new_owner_discord_id:
        raise BankError("You already own this bank.")
    async with session_scope() as session:
        async with session.begin():
            bank = await session.scalar(
                select(Bank)
                .where(
                    Bank.guild_id == guild_id,
                    Bank.owner_discord_id == owner_discord_id,
                )
                .with_for_update()
            )
            if bank is None:
                raise BankError("Only the current bank owner can transfer ownership.")
            membership = await session.scalar(
                select(BankMembership.id).where(
                    BankMembership.guild_id == guild_id,
                    BankMembership.bank_id == bank.id,
                    BankMembership.discord_user_id == new_owner_discord_id,
                )
            )
            if membership is None:
                raise BankError("Ownership can only be transferred to a current bank member.")

            bank.owner_discord_id = new_owner_discord_id
            await session.execute(
                update(BankRequest)
                .where(
                    BankRequest.bank_id == bank.id,
                    BankRequest.status == "pending",
                )
                .values(
                    status="cancelled",
                    reviewer_discord_id=owner_discord_id,
                    responded_at=datetime.now(timezone.utc),
                )
            )
            session.add(
                BankTransaction(
                    guild_id=guild_id,
                    bank_id=bank.id,
                    actor_discord_id=owner_discord_id,
                    action="ownership_transfer",
                    amount=Decimal("0.00"),
                    balance_after=bank.balance,
                    note=f"Ownership transferred to Discord user {new_owner_discord_id}.",
                )
            )
            return bank.name


async def disband_bank(
    guild_id: int,
    owner_discord_id: int,
    confirmation_name: str,
) -> str:
    _, normalized_confirmation = normalize_bank_name(confirmation_name)
    async with session_scope() as session:
        async with session.begin():
            bank = await session.scalar(
                select(Bank)
                .where(
                    Bank.guild_id == guild_id,
                    Bank.owner_discord_id == owner_discord_id,
                )
                .with_for_update()
            )
            if bank is None:
                raise BankError("You do not own a bank in this server.")
            if bank.normalized_name != normalized_confirmation:
                raise BankError("The confirmation must match your bank's name.")
            if bank.balance != Decimal("0.00"):
                raise BankError("Withdraw all currency from the bank before disbanding it.")
            name = bank.name
            await session.delete(bank)
            return name


class BankDetails(NamedTuple):
    bank: Bank
    member_discord_ids: list[int]
    member_count: int


async def get_bank_details(
    guild_id: int,
    viewer_discord_id: int,
    bank_name: Optional[str] = None,
) -> Optional[BankDetails]:
    async with session_scope() as session:
        if bank_name is None:
            bank = await session.scalar(
                select(Bank)
                .join(BankMembership, BankMembership.bank_id == Bank.id)
                .where(
                    Bank.guild_id == guild_id,
                    BankMembership.discord_user_id == viewer_discord_id,
                )
            )
        else:
            _, normalized_name = normalize_bank_name(bank_name)
            bank = await session.scalar(
                select(Bank).where(
                    Bank.guild_id == guild_id,
                    Bank.normalized_name == normalized_name,
                )
            )

        if bank is None:
            return None

        member_count = int(
            await session.scalar(
                select(func.count(BankMembership.id)).where(
                    BankMembership.bank_id == bank.id,
                )
            )
            or 0
        )
        result = await session.scalars(
            select(BankMembership.discord_user_id)
            .where(BankMembership.bank_id == bank.id)
            .order_by(BankMembership.joined_at, BankMembership.discord_user_id)
            .limit(25)
        )
        return BankDetails(bank, list(result.all()), member_count)


async def _wallet_account(session, guild_id: int, discord_user_id: int) -> Account:
    account = await session.scalar(
        select(Account)
        .join(Player, Player.id == Account.player_id)
        .where(
            Player.guild_id == guild_id,
            Player.discord_user_id == discord_user_id,
            Account.account_type == "wallet",
        )
        .with_for_update(of=Account)
    )
    if account is None:
        raise RuntimeError("The member's wallet account could not be retrieved.")
    return account


async def _apply_bank_transfer(
    session,
    bank: Bank,
    member_discord_id: int,
    actor_discord_id: int,
    action: str,
    amount: Decimal,
) -> Decimal:
    wallet = await _wallet_account(session, bank.guild_id, member_discord_id)
    capacity = bank_capacity(bank.upgrade_level)
    if action == "deposit":
        if wallet.balance < amount:
            raise BankError("Your wallet does not contain enough currency.")
        if bank.balance + amount > capacity:
            raise BankError(
                f"That deposit would exceed the bank's {capacity:,.2f} {FIHCOIN} capacity."
            )
        wallet.balance -= amount
        bank.balance += amount
        transaction_type = "bank_deposit"
        sender_id, recipient_id = member_discord_id, None
    elif action == "withdraw":
        if bank.balance < amount:
            raise BankError("The bank does not contain enough currency for that withdrawal.")
        wallet.balance += amount
        bank.balance -= amount
        transaction_type = "bank_withdraw"
        sender_id, recipient_id = None, member_discord_id
    else:
        raise BankError("Unsupported bank transfer action.")

    session.add(
        BankTransaction(
            guild_id=bank.guild_id,
            bank_id=bank.id,
            actor_discord_id=actor_discord_id,
            action=action,
            amount=amount,
            balance_after=bank.balance,
        )
    )
    await record_transaction(
        session,
        guild_id=bank.guild_id,
        transaction_type=transaction_type,
        amount=amount,
        actor_discord_id=actor_discord_id,
        sender_discord_id=sender_id,
        recipient_discord_id=recipient_id,
        note=f"Bank: {bank.name}",
    )
    return bank.balance


async def initiate_bank_transfer(
    guild_id: int,
    member_discord_id: int,
    action: str,
    amount_text: str,
) -> BankTransferOutcome:
    if action not in {"deposit", "withdraw"}:
        raise BankError("Choose either a deposit or a withdrawal.")
    amount = parse_bank_amount(amount_text)
    await get_or_create_balances(guild_id, member_discord_id)

    async with session_scope() as session:
        async with session.begin():
            result = await session.execute(
                select(Bank, BankMembership)
                .join(BankMembership, BankMembership.bank_id == Bank.id)
                .where(
                    Bank.guild_id == guild_id,
                    BankMembership.guild_id == guild_id,
                    BankMembership.discord_user_id == member_discord_id,
                )
                .with_for_update(of=Bank)
            )
            bank, membership = result.one_or_none() or (None, None)
            if bank is None or membership is None:
                raise BankError("You must join a bank before depositing or withdrawing.")

            if bank.owner_discord_id == member_discord_id:
                balance_after = await _apply_bank_transfer(
                    session,
                    bank,
                    member_discord_id,
                    member_discord_id,
                    action,
                    amount,
                )
                return BankTransferOutcome(
                    bank.name,
                    action,
                    amount,
                    balance_after,
                    bank_capacity(bank.upgrade_level),
                    bank.owner_discord_id,
                    None,
                )

            request = BankRequest(
                guild_id=guild_id,
                bank_id=bank.id,
                requester_discord_id=member_discord_id,
                action=action,
                amount=amount,
            )
            session.add(request)
            await session.flush()
            return BankTransferOutcome(
                bank.name,
                action,
                amount,
                None,
                bank_capacity(bank.upgrade_level),
                bank.owner_discord_id,
                request.id,
            )


async def cancel_bank_request(request_id: UUID) -> None:
    async with session_scope() as session:
        async with session.begin():
            request = await session.scalar(
                select(BankRequest)
                .where(BankRequest.id == request_id)
                .with_for_update()
            )
            if request is not None and request.status == "pending":
                request.status = "cancelled"
                request.responded_at = datetime.now(timezone.utc)


async def pending_bank_request_ids() -> list[UUID]:
    async with session_scope() as session:
        result = await session.scalars(
            select(BankRequest.id).where(BankRequest.status == "pending")
        )
        return list(result.all())


async def decide_bank_request(
    request_id: UUID,
    reviewer_discord_id: int,
    *,
    approve: bool,
) -> BankRequestOutcome:
    async with session_scope() as session:
        async with session.begin():
            request_reference = await session.execute(
                select(BankRequest.guild_id, BankRequest.bank_id).where(
                    BankRequest.id == request_id,
                )
            )
            reference = request_reference.one_or_none()
            if reference is None:
                raise BankError("That bank request no longer exists.")
            guild_id, bank_id = reference

            bank = await session.scalar(
                select(Bank)
                .where(
                    Bank.id == bank_id,
                    Bank.guild_id == guild_id,
                )
                .with_for_update()
            )
            request = await session.scalar(
                select(BankRequest)
                .where(BankRequest.id == request_id)
                .with_for_update()
            )
            if request is None:
                raise BankError("That bank request no longer exists.")
            if request.status != "pending":
                raise BankError("That bank request has already been resolved.")
            if bank is None:
                request.status = "cancelled"
                request.responded_at = datetime.now(timezone.utc)
                return BankRequestOutcome(
                    "Deleted bank",
                    request.action,
                    request.amount,
                    request.requester_discord_id,
                    "cancelled",
                    None,
                    "The bank no longer exists.",
                )
            if bank.owner_discord_id != reviewer_discord_id:
                raise BankError("Only the current bank owner can approve this request.")

            if not approve:
                request.status = "declined"
                request.reviewer_discord_id = reviewer_discord_id
                request.responded_at = datetime.now(timezone.utc)
                return BankRequestOutcome(
                    bank.name,
                    request.action,
                    request.amount,
                    request.requester_discord_id,
                    "declined",
                    bank.balance,
                    "The bank owner declined the request.",
                )

            membership = await session.scalar(
                select(BankMembership.id).where(
                    BankMembership.guild_id == request.guild_id,
                    BankMembership.bank_id == bank.id,
                    BankMembership.discord_user_id == request.requester_discord_id,
                )
            )
            if membership is None:
                request.status = "cancelled"
                request.reviewer_discord_id = reviewer_discord_id
                request.responded_at = datetime.now(timezone.utc)
                return BankRequestOutcome(
                    bank.name,
                    request.action,
                    request.amount,
                    request.requester_discord_id,
                    "cancelled",
                    bank.balance,
                    "The requester is no longer a member of this bank.",
                )

            try:
                balance_after = await _apply_bank_transfer(
                    session,
                    bank,
                    request.requester_discord_id,
                    reviewer_discord_id,
                    request.action,
                    request.amount,
                )
            except BankError as error:
                request.status = "failed"
                request.reviewer_discord_id = reviewer_discord_id
                request.responded_at = datetime.now(timezone.utc)
                return BankRequestOutcome(
                    bank.name,
                    request.action,
                    request.amount,
                    request.requester_discord_id,
                    "failed",
                    bank.balance,
                    str(error),
                )

            request.status = "approved"
            request.reviewer_discord_id = reviewer_discord_id
            request.responded_at = datetime.now(timezone.utc)
            return BankRequestOutcome(
                bank.name,
                request.action,
                request.amount,
                request.requester_discord_id,
                "approved",
                balance_after,
                "The request was approved and completed.",
            )


async def buy_bank_upgrade(guild_id: int, owner_discord_id: int) -> tuple[str, int, Decimal, Decimal]:
    await get_or_create_balances(guild_id, owner_discord_id)
    async with session_scope() as session:
        async with session.begin():
            bank = await session.scalar(
                select(Bank)
                .where(
                    Bank.guild_id == guild_id,
                    Bank.owner_discord_id == owner_discord_id,
                )
                .with_for_update()
            )
            if bank is None:
                raise BankError("Only a bank owner can purchase upgrades.")
            upgrade = next_bank_upgrade(bank.upgrade_level)
            if upgrade is None:
                raise BankError(f"This bank is already at the maximum level ({BANK_MAX_LEVEL}).")
            new_level, new_capacity, cost = upgrade
            wallet = await _wallet_account(session, guild_id, owner_discord_id)
            if wallet.balance < cost:
                raise BankError(
                    f"You need {cost:,.2f} {FIHCOIN} in your wallet for this upgrade."
                )

            wallet.balance -= cost
            bank.upgrade_level = new_level
            session.add(
                BankTransaction(
                    guild_id=guild_id,
                    bank_id=bank.id,
                    actor_discord_id=owner_discord_id,
                    action="upgrade",
                    amount=cost,
                    balance_after=bank.balance,
                    note=f"Upgraded bank storage to level {new_level}.",
                )
            )
            await record_transaction(
                session,
                guild_id=guild_id,
                transaction_type="bank_upgrade",
                amount=cost,
                actor_discord_id=owner_discord_id,
                sender_discord_id=owner_discord_id,
                note=f"Bank storage upgrade to level {new_level}.",
            )
            return bank.name, new_level, new_capacity, cost


async def get_owned_bank(guild_id: int, owner_discord_id: int) -> Optional[Bank]:
    async with session_scope() as session:
        return await session.scalar(
            select(Bank).where(
                Bank.guild_id == guild_id,
                Bank.owner_discord_id == owner_discord_id,
            )
        )
