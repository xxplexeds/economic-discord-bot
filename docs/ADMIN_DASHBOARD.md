# Access Control, Dashboard, and Operations Specification

This document records agreed behavior. It is a specification, not a claim that features are already live.

## Management authorization

A member may access management commands and website management APIs if any of these conditions pass:
- They have the Discord guild-level Administrator permission. In discord.py, check member.guild_permissions.administrator; do not check a role's display name.
- Their Discord User ID has an active explicit management grant.
- They have a Discord Role ID with an active explicit management grant.

User and role grants are scoped to the configured Release 1 guild. The same policy protects Discord management commands and website APIs. The backend must verify the user's identity, current guild membership, and current roles; hiding UI controls is not authorization. Regular economy commands remain available to eligible members.

## Economy-level blocked users

Blocking is separate from Discord moderation. It does not kick, ban, timeout, or remove roles from a Discord member.

A blocked user cannot earn or receive currency, send payments or transfers, deposit or withdraw, purchase from the shop, or participate in clan economy actions. Every restriction must be enforced in shared backend business logic so it applies equally to Discord and website actions.

Existing balances and transaction history are preserved. Unblocking restores eligibility without resetting account data. Each block/unblock action records the actor, target, reason, and timestamp. Management authorization is independent from economy blocked status; blocking an administrator does not silently revoke their dashboard access.

## Audit logs

Record balance adjustments, block/unblock, user/role grant/revoke, tax and economy setting changes, maintenance changes, log-channel changes, backup creation/failure/verification/restore, and session revocation where available.

Each entry includes guild, actor, action, target, timestamp, and structured details. Never store bot tokens, OAuth secrets, database URLs, or session tokens in audit details. Treat audit rows as append-only.

## Economy analytics

Derive wallet totals, bank totals, total circulation, transaction volume/count by time range and type, daily activity, and rankings from authoritative account and transaction data. Do not maintain manually editable aggregate totals. Define gross transaction volume separately from net currency creation/destruction.

## Maintenance mode

Authorized administrators can enable/disable maintenance mode and edit its message. While enabled, member-facing economy operations are rejected in the shared service layer. Health checks and authorized management access remain available.

## Logging configuration

Configure Discord channels by event category, such as economy, access/security, system/maintenance, and admin notifications. Validate that each channel belongs to the configured guild and that the bot can view and send messages there. Database audit records remain authoritative if Discord log delivery fails.

## Database backups

Store backups separately from the live PostgreSQL database. Store metadata in PostgreSQL, not backup credentials. Include encryption, retention, integrity checks/checksums, failure alerts, and periodic restore drills. A backup is successful only after completion and verification.

## Website authentication

Use Discord OAuth2. Validate OAuth state, use secure HTTP-only session cookies, protect against CSRF, and verify current guild membership and roles server-side. Never expose the bot token or OAuth client secret to the browser.

## Last-admin protection

Before revoking a User ID or Role ID grant, check whether at least one viable management access path remains. Prevent accidental lockout and require clear confirmation for changes that could remove the final configured grant.
