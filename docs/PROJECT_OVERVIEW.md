# Fihcoin Economic Bot — Project Overview

## Vision

Fihcoin is a Discord-first virtual-currency economy with a companion Next.js website. It takes inspiration from Candy Bot's feature breadth while establishing its own identity, improved user experience, and maintainable architecture.

The Discord bot, website, and backend share one source of truth for balances, permissions, blocked-user status, and transactions.

## Confirmed decisions

- Release 1 supports one Discord server and one currency.
- Currency: **Fihcoins** (singular: **Fihcoin**, meaning Fish Coin).
- Official emoji: <:fihcoin:1575710572907987064>.
- Balances support two decimal places.
- Banking and configurable taxes are planned; bank interest is excluded.
- No gambling mechanics.
- Clans will have a shared treasury, roles, and leaderboards.
- Hosting: Railway.
- Stack: Python + discord.py, FastAPI, PostgreSQL, and Next.js.

## Management authorization

Management access is granted when at least one condition is met:
1. The member has Discord guild-level Administrator permission, including when granted by any assigned role.
2. The Discord User ID has an active explicit management grant.
3. The member has an explicitly authorized Discord Role ID.

The same policy protects Discord management commands and website management APIs. The backend verifies identity, current guild membership, and roles server-side. Sensitive permission changes are audited. The system prevents accidental removal of the final viable management access path.

## Economy-level blocks

Blocking is an economy restriction, not a Discord server ban.
- Blocked users cannot earn, receive, transfer, deposit, withdraw, purchase, or participate in clan economy actions.
- Enforcement occurs in shared backend logic, not only by hiding interface controls.
- Existing balances and transaction history are preserved.
- Unblocking restores eligibility without resetting account data.
- Block/unblock actions record actor, reason, and timestamp.
- Management access is independent from economy blocked status.

## Website dashboard

The planned Next.js website uses Discord OAuth2 and secure server-side sessions. It includes overview, economy analytics, member profiles, balances and history, economy administration, clan management, shop, leaderboards, access control, blocked users, audit logs, maintenance mode, logging configuration, and database backup history.

The dashboard and Discord bot use the same FastAPI business logic. Website-only authorization checks are insufficient.

## Operations and safety

- Audit sensitive administrative actions with actor, action, target, timestamp, and relevant details.
- Maintenance mode blocks member economy actions but leaves authorized management access available.
- Discord log channels are configurable by event category.
- Backups are encrypted, stored outside the live PostgreSQL database, integrity-checked, and periodically restore-tested.
- Analytics are derived from authoritative transaction/account data.

Implementation is staged. Planned features are not live until implemented, deployed, and verified.
