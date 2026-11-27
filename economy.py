from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database import session_scope
from models import Account, AdminRoleGrant, AdminUserGrant, EconomyTransaction, Player


async def get_or_create_balances(
    guild_id: int,
    discord_user_id: int,
) -> tuple[Decimal, Decimal]:
    """Return a member's wallet and bank balances, creating zeroed accounts if needed."""
    async with session_scope() as session:
        async with session.begin():
            await session.execute(
                pg_insert(Player)
                .values(guild_id=guild_id, discord_user_id=discord_user_id)
                .on_conflict_do_nothing(constraint="uq_player_guild_user")
            )

            player = await session.scalar(
                select(Player).where(
                    Player.guild_id == guild_id,
                    Player.discord_user_id == discord_user_id,
                )
            )
            if player is None:
                raise RuntimeError("Could not create or retrieve the player's economy profile.")

            await session.execute(
                pg_insert(Account)
                .values(
                    [
                        {"player_id": player.id, "account_type": "wallet"},
                        {"player_id": player.id, "account_type": "bank"},
                    ]
                )
                .on_conflict_do_nothing(constraint="uq_account_player_type")
            )

            result = await session.execute(
                select(Account.account_type, Account.balance).where(
                    Account.player_id == player.id
                )
            )
            balances = {account_type: balance for account_type, balance in result.all()}

            return (
                balances.get("wallet", Decimal("0.00")),
                balances.get("bank", Decimal("0.00")),
            )


async def get_player_profile(
    guild_id: int,
    discord_user_id: int,
) -> tuple[Decimal, Decimal, Decimal, int, datetime, int]:
    """Return a member's balances, leaderboard rank, account age, and activity count."""
    wallet, bank = await get_or_create_balances(guild_id, discord_user_id)
    total = wallet + bank

    async with session_scope() as session:
        player = await session.scalar(
            select(Player).where(
                Player.guild_id == guild_id,
                Player.discord_user_id == discord_user_id,
            )
        )
        if player is None:
            raise RuntimeError("Could not retrieve the player's economy profile.")

        ranked_totals = (
            select(
                Player.id.label("player_id"),
                func.sum(Account.balance).label("total_balance"),
            )
            .join(Account, Account.player_id == Player.id)
            .where(Player.guild_id == guild_id)
            .group_by(Player.id)
            .subquery()
        )
        rank = int(
            await session.scalar(
                select(func.count())
                .select_from(ranked_totals)
                .where(ranked_totals.c.total_balance > total)
            )
            or 0
        ) + 1

        member_activity = or_(
            EconomyTransaction.sender_discord_id == discord_user_id,
            EconomyTransaction.recipient_discord_id == discord_user_id,
        )
        transaction_count = await session.scalar(
            select(func.count(EconomyTransaction.id)).where(
                EconomyTransaction.guild_id == guild_id,
                member_activity,
            )
        )

        return (
            wallet,
            bank,
            total,
            rank,
            player.created_at,
            int(transaction_count or 0),
        )


async def get_leaderboard_page(
    guild_id: int,
    *,
    limit: int = 10,
    offset: int = 0,
) -> tuple[list[tuple[int, Decimal]], int]:
    """Return one leaderboard page and the total number of ranked members."""
    from sqlalchemy import func

    safe_limit = max(1, min(limit, 25))
    safe_offset = max(0, offset)
    async with session_scope() as session:
        total_count = await session.scalar(
            select(func.count(func.distinct(Player.id)))
            .join(Account, Account.player_id == Player.id)
            .where(Player.guild_id == guild_id)
        )
        result = await session.execute(
            select(
                Player.discord_user_id,
                func.sum(Account.balance).label("total_balance"),
            )
            .join(Account, Account.player_id == Player.id)
            .where(Player.guild_id == guild_id)
            .group_by(Player.id, Player.discord_user_id)
            .order_by(
                func.sum(Account.balance).desc(),
                Player.discord_user_id.asc(),
            )
            .limit(safe_limit)
            .offset(safe_offset)
        )
        entries = [
            (discord_user_id, total_balance)
            for discord_user_id, total_balance in result.all()
        ]
        return entries, int(total_count or 0)


async def get_transaction_history_page(
    guild_id: int,
    discord_user_id: int,
    *,
    limit: int = 10,
    offset: int = 0,
) -> tuple[list[EconomyTransaction], int]:
    """Return one member's sent/received transaction page and total record count."""
    safe_limit = max(1, min(limit, 25))
    safe_offset = max(0, offset)
    member_activity = or_(
        EconomyTransaction.sender_discord_id == discord_user_id,
        EconomyTransaction.recipient_discord_id == discord_user_id,
    )

    async with session_scope() as session:
        total_count = await session.scalar(
            select(func.count(EconomyTransaction.id)).where(
                EconomyTransaction.guild_id == guild_id,
                member_activity,
            )
        )
        result = await session.execute(
            select(EconomyTransaction)
            .where(
                EconomyTransaction.guild_id == guild_id,
                member_activity,
            )
            .order_by(
                EconomyTransaction.created_at.desc(),
                EconomyTransaction.id.desc(),
            )
            .limit(safe_limit)
            .offset(safe_offset)
        )
        return list(result.scalars().all()), int(total_count or 0)


async def has_admin_history_access(
    guild_id: int,
    discord_user_id: int,
    role_ids: list[int],
) -> bool:
    """Check explicit per-guild user or role grants for cross-member history access."""
    async with session_scope() as session:
        user_grant = await session.scalar(
            select(AdminUserGrant.id).where(
                AdminUserGrant.guild_id == guild_id,
                AdminUserGrant.discord_user_id == discord_user_id,
                AdminUserGrant.is_active.is_(True),
            ).limit(1)
        )
        if user_grant is not None:
            return True

        if not role_ids:
            return False

        role_grant = await session.scalar(
            select(AdminRoleGrant.id).where(
                AdminRoleGrant.guild_id == guild_id,
                AdminRoleGrant.discord_role_id.in_(role_ids),
                AdminRoleGrant.is_active.is_(True),
            ).limit(1)
        )
        return role_grant is not None


async def record_transaction(
    session,
    *,
    guild_id: int,
    transaction_type: str,
    amount: Decimal,
    actor_discord_id: int | None = None,
    sender_discord_id: int | None = None,
    recipient_discord_id: int | None = None,
    fee: Decimal = Decimal("0.00"),
    note: str | None = None,
) -> EconomyTransaction:
    """Stage an immutable history row in the caller's active balance transaction.

    Call this before committing the same session transaction that changes balances.
    The caller owns the transaction boundary so a balance update and its history
    record can commit or roll back together.
    """
    amount = Decimal(amount)
    fee = Decimal(fee)
    if amount <= 0:
        raise ValueError("Transaction amount must be greater than zero.")
    if fee < 0:
        raise ValueError("Transaction fee cannot be negative.")

    record = EconomyTransaction(
        guild_id=guild_id,
        actor_discord_id=actor_discord_id,
        sender_discord_id=sender_discord_id,
        recipient_discord_id=recipient_discord_id,
        transaction_type=transaction_type[:32],
        amount=amount,
        fee=fee,
        note=note[:500] if note else None,
    )
    session.add(record)
    return record
