# Fihcoin Economic Bot — Update Log

## 2026-11-27 — Add balance section dividers

### Changed
- Rebuilt the `/balance` Components V2 layout with separate Wallet, Bank, and Total text sections divided by native Discord Separator components.
- Kept the member avatar, silent clickable mention, and shared leaderboard profile layout intact.

---


## 2026-11-27 — Disable leaderboard mention notifications

### Fixed
- Kept leaderboard member mentions visible and clickable while disabling all mention notifications in the leaderboard response with `discord.AllowedMentions.none()`.

---


## 2026-11-27 — Balance profile and leaderboard UI refinements

### Changed
- Updated the leaderboard profile thumbnail to use the Discord server icon instead of the bot avatar. If the server has no icon, it falls back to the invoking member's avatar.
- Updated the balance profile heading to use a Discord user mention for the selected member, while disabling mention notifications so it displays as a mention without pinging them.

---

## 2026-11-27 — Balance profiles and leaderboard

### Added
- Updated `/balance` to accept an optional server member, so members can view their own balance or look up another member.
- Rebuilt balance responses with Discord Components V2, including wallet, bank, combined total, Fihcoin emoji, and the target member's avatar.
- Added the public `/leaderboard` command showing the top 10 members by combined wallet and bank balance.
- Added deterministic tie ordering for leaderboard entries.

### Changed
- Balance and leaderboard views are public.
- Corrected the wallet foundation status below: PR #5 has been merged into `main`; deployment still needs to be confirmed.

### Scope
- These commands only read balances and initialize missing zero-balance accounts. They do not add, transfer, deposit, or withdraw currency.

---

# Fihcoin Economic Bot — Update Log

## 2026-11-27 — Wallet and balance foundation (merged)

### Added
- Added shared PostgreSQL-backed balance retrieval that creates a player's wallet and bank accounts on first use.
- Added the `/balance` Discord command showing wallet, bank, and combined totals with two decimal places.
- The initial balance response used a private embed and included the member's Discord avatar.
- Added a scoped async SQLAlchemy session helper for explicit transaction boundaries.

### Safety and integrity
- Player and account creation use PostgreSQL conflict handling so concurrent first-time requests do not create duplicate profiles or accounts.
- This milestone only reads balances and initializes zero-balance accounts; it does not yet add, transfer, deposit, or withdraw currency.

### Status
- PR #5 was merged into `main`. Confirm the Railway bot deployment before treating the command as live.

---

This file records project decisions, implementation changes, and setup milestones. Keep entries newest-first. A planned or specified feature must not be described as live.

## 2026-11-27 — Administration and dashboard foundation

### Confirmed
- Management access supports Discord Administrator permission, explicit Discord User ID grants, and explicit Discord Role ID grants.
- Regular members retain access to regular economy commands; management authorization protects administrative actions.
- Blocking is an economy-level restriction, not a Discord server ban.
- Blocked users cannot earn, receive, transfer, deposit, withdraw, purchase, or use clan economy features.
- Blocked users retain balances and transaction history; unblocking restores eligibility.
- Management access is independent from economy blocked status.
- Confirmed audit logs, economy analytics, maintenance mode, configurable Discord logging channels, and database backups.

### Added
- Added docs/ADMIN_DASHBOARD.md with the agreed access-control, blocklist, audit, analytics, maintenance, logging, backup, OAuth, and last-admin safety requirements.
- Added SQLAlchemy model foundations for explicit administrator User ID grants and Role ID grants.
- Added a blocked-user model with reason and block/unblock actor/timestamps.
- Added an administrative audit-event model.
- Added model foundations for maintenance settings, event log-channel configuration, and backup metadata.
- Expanded the roadmap and project overview to track these requirements.

### Status
- The admin foundation is merged into `main` and deployed with the PostgreSQL foundation. Its models/specifications are present; the user-facing admin features still require implementation.
- OAuth login, authorization enforcement, block/unblock endpoints, audit UI, analytics, maintenance controls, Discord log delivery, and backup jobs still require implementation and testing.
- The deployed backend health check confirms PostgreSQL connectivity. The initial schema is created at service startup.

---

## 2026-11-27 — PostgreSQL foundation

### Added
- Added an async SQLAlchemy database layer using PostgreSQL and asyncpg.
- Added initial players, wallet/bank accounts, and economy transaction tables.
- Added constraints for valid account types, non-negative balances/fees, and positive transaction amounts.
- Added docs/DATABASE.md and python-dotenv.

### Changed
- FastAPI /health checks PostgreSQL and reports database connectivity.
- Bot and API initialize the initial database schema at startup.
- Updated .env.example and README.md with database configuration.

### Infrastructure
- Railway has Discord Bot, FastAPI Backend, and PostgreSQL services.
- Both app services reference the Railway PostgreSQL DATABASE_URL variable.
- The deployed bot responded to /ping.
- The API returned a healthy response before the database-aware health check was merged/deployed.

### Follow-up
- Verified after deployment: `/health` returns `{"status":"healthy","database":"connected"}`.
- Add Alembic migrations before future production schema changes.
- Implement economy commands, atomic balance operations, clans, shop, leaderboards, and website.

---

## 2026-11-27 — Project foundation and Fihcoin identity

### Confirmed
- One Discord server and one currency for Release 1.
- Fihcoins (singular: Fihcoin), meaning Fish Coin.
- Official emoji: <:fihcoin:1575710572907987064>.
- PostgreSQL, Python + discord.py, FastAPI, Next.js, and Railway.
- No gambling mechanics and no bank interest.

### Added
- Initial bot entry point with /ping and application-command synchronization.
- Initial FastAPI app with root and /health endpoints.
- requirements.txt, .env.example, .gitignore, README.md, and initial docs.
- Official Fihcoin identity and emoji in project documentation.

### Not implemented yet
- Economy commands beyond /ping, balance operations, taxes, transaction history, clans, shop, leaderboards, website, and Discord OAuth.

---

## Update entry template

## YYYY-MM-DD — Short update title

### Added
- ...

### Changed
- ...

### Fixed
- ...

### Infrastructure / setup
- ...

### Not implemented / follow-up
- ...
