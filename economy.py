from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database import session_scope
from models import Account, Player


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
