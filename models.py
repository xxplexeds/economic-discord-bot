import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index,
    JSON, Numeric, String, UniqueConstraint, func,
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


class AdminUserGrant(Base):
    """Explicit management access granted to a Discord User ID."""
    __tablename__ = "admin_user_grants"
    __table_args__ = (UniqueConstraint("guild_id", "discord_user_id", name="uq_admin_user_grant"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    granted_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AdminRoleGrant(Base):
    """Explicit management access granted to members with a Discord Role ID."""
    __tablename__ = "admin_role_grants"
    __table_args__ = (UniqueConstraint("guild_id", "discord_role_id", name="uq_admin_role_grant"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discord_role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    granted_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BlockedUser(Base):
    """Economy-level block; this is not a Discord server ban."""
    __tablename__ = "blocked_users"
    __table_args__ = (
        UniqueConstraint("guild_id", "discord_user_id", name="uq_blocked_user_guild_user"),
        Index("ix_blocked_users_active", "guild_id", "is_active"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    blocked_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    blocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    unblocked_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    unblocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AdminAuditLog(Base):
    """Application audit event for sensitive administrative actions."""
    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        Index("ix_admin_audit_guild_created", "guild_id", "created_at"),
        Index("ix_admin_audit_actor_created", "actor_discord_id", "created_at"),
        Index("ix_admin_audit_action_created", "action", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GuildSettings(Base):
    """Per-guild operational settings, including maintenance mode."""
    __tablename__ = "guild_settings"
    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    maintenance_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    maintenance_message: Mapped[str] = mapped_column(
        String(500), nullable=False,
        default="Fihcoin is temporarily under maintenance. Please try again later.",
        server_default="Fihcoin is temporarily under maintenance. Please try again later.",
    )
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class LogChannelConfig(Base):
    """Maps an event category to a configured Discord text channel."""
    __tablename__ = "log_channel_configs"
    __table_args__ = (UniqueConstraint("guild_id", "event_type", name="uq_log_channel_guild_event"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class BackupRecord(Base):
    """Metadata for backups stored outside the live PostgreSQL database."""
    __tablename__ = "backup_records"
    __table_args__ = (Index("ix_backup_records_created", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
