import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("guild_id", "discord_user_id", name="uq_player_guild_user"),
        Index("ix_players_discord_user_id", "discord_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("player_id", "account_type", name="uq_account_player_type"),
        CheckConstraint("account_type IN ('wallet', 'bank')", name="ck_account_type"),
        CheckConstraint("balance >= 0", name="ck_account_nonnegative_balance"),
        Index("ix_accounts_player_id", "player_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    account_type: Mapped[str] = mapped_column(String(16), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EconomyTransaction(Base):
    __tablename__ = "economy_transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transaction_positive_amount"),
        CheckConstraint("fee >= 0", name="ck_transaction_nonnegative_fee"),
        Index("ix_transactions_guild_created", "guild_id", "created_at"),
        Index("ix_transactions_actor_created", "actor_discord_id", "created_at"),
        Index("ix_transactions_sender_created", "sender_discord_id", "created_at"),
        Index("ix_transactions_recipient_created", "recipient_discord_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sender_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    recipient_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
