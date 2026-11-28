from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer,
    JSON, Numeric, String, Text, UniqueConstraint, func,
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


class Bank(Base):
    __tablename__ = "banks"
    __table_args__ = (
        UniqueConstraint("guild_id", "normalized_name", name="uq_bank_guild_name"),
        UniqueConstraint("guild_id", "owner_discord_id", name="uq_bank_guild_owner"),
        CheckConstraint("balance >= 0", name="ck_bank_nonnegative_balance"),
        CheckConstraint("upgrade_level BETWEEN 1 AND 10", name="ck_bank_upgrade_level"),
        Index("ix_banks_guild_created", "guild_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    banner_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    upgrade_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BankMembership(Base):
    __tablename__ = "bank_memberships"
    __table_args__ = (
        UniqueConstraint("guild_id", "discord_user_id", name="uq_bank_member_guild_user"),
        UniqueConstraint("bank_id", "discord_user_id", name="uq_bank_member_bank_user"),
        Index("ix_bank_memberships_bank_joined", "bank_id", "joined_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("banks.id", ondelete="CASCADE"),
        nullable=False,
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BankInvite(Base):
    __tablename__ = "bank_invites"
    __table_args__ = (
        UniqueConstraint("guild_id", "bank_id", "invitee_discord_id", name="uq_bank_invite_target"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled')",
            name="ck_bank_invite_status",
        ),
        Index("ix_bank_invites_guild_invitee_status", "guild_id", "invitee_discord_id", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("banks.id", ondelete="CASCADE"),
        nullable=False,
    )
    inviter_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    invitee_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BankRequest(Base):
    __tablename__ = "bank_requests"
    __table_args__ = (
        CheckConstraint("action IN ('deposit', 'withdraw')", name="ck_bank_request_action"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'declined', 'cancelled', 'failed')",
            name="ck_bank_request_status",
        ),
        CheckConstraint("amount > 0", name="ck_bank_request_positive_amount"),
        Index("ix_bank_requests_bank_status_created", "bank_id", "status", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("banks.id", ondelete="CASCADE"),
        nullable=False,
    )
    requester_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    reviewer_discord_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('deposit', 'withdraw', 'upgrade', 'ownership_transfer')",
            name="ck_bank_transaction_action",
        ),
        CheckConstraint("amount >= 0", name="ck_bank_transaction_nonnegative_amount"),
        CheckConstraint("balance_after >= 0", name="ck_bank_transaction_nonnegative_balance"),
        Index("ix_bank_transactions_bank_created", "bank_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("banks.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
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
    actor_discord_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    sender_discord_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    recipient_discord_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
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
    unblocked_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    unblocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


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
    actor_discord_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DashboardSession(Base):
    __tablename__ = "dashboard_sessions"
    __table_args__ = (
        Index("ix_dashboard_sessions_user_expires", "discord_user_id", "expires_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    updated_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
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
    updated_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class BackupRecord(Base):
    """Metadata for backups stored outside the live PostgreSQL database."""
    __tablename__ = "backup_records"
    __table_args__ = (Index("ix_backup_records_created", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    object_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
