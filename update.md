# Fihcoin Economic Bot — Update Log

This file records project decisions, implementation changes, and setup milestones. Add a new dated entry whenever the project is updated. Keep entries newest-first and describe user-visible changes separately from planning or infrastructure work.

## 2026-11-27 — PostgreSQL foundation

### Added
- Added an async SQLAlchemy database layer using PostgreSQL and asyncpg.
- Added the initial `players` table to identify a Discord user within a server.
- Added the `accounts` table for separate wallet and bank balances.
- Added the `economy_transactions` table to record transaction participants, amounts, fees, notes, and timestamps.
- Added database constraints for valid account types, non-negative balances and fees, and positive transaction amounts.
- Added `docs/DATABASE.md` describing the schema and database safety requirements.
- Added `python-dotenv` for loading local `.env` configuration.

### Changed
- The FastAPI `/health` endpoint now checks PostgreSQL and reports `database: connected` when successful.
- The Discord bot now verifies PostgreSQL and ensures the initial tables exist during startup.
- The FastAPI service now verifies PostgreSQL and ensures the initial tables exist during startup.
- Updated `.env.example` and `README.md` with the database configuration and behavior.

### Infrastructure / setup
- Railway now has separate Discord Bot and FastAPI Backend services plus a PostgreSQL service.
- Both application services use the Railway PostgreSQL variable reference for `DATABASE_URL`.
- The deployed bot successfully responded to `/ping`.
- The deployed API returned a healthy response before database integration was added.

### Not implemented / follow-up
- Deploy this database foundation and verify `/health` returns `{"status":"healthy","database":"connected"}`.
- Add versioned Alembic migrations before making future production schema changes.
- Implement player registration and account creation.
- Implement atomic balance operations and matching transaction writes.
- Add economy commands, clans, shop, leaderboards, and website.

---

## 2026-11-27 — Project foundation and Fihcoin identity

### Confirmed decisions
- Release 1 targets one Discord server.
- Release 1 uses one currency: **Fihcoins** (singular: **Fihcoin**), meaning **Fish Coin**.
- Official currency emoji: `<:fihcoin:1575710572907987064>`.
- PostgreSQL is the selected database.
- Technology stack: Python + discord.py, FastAPI, PostgreSQL, and Next.js.
- Railway is the selected hosting platform.
- Gambling mechanics are excluded.
- Bank interest is excluded; the planned bank uses configurable taxes only.

### Discord setup
- Created the Discord application and bot.
- Configured the application for a private, single-server installation.
- Invited the bot to the intended Discord server.
- Bot token and other credentials must remain in secure environment variables and must never be committed here.

### Repository foundation
- Added the initial Python Discord bot entry point in `bot.py`, including a `/ping` command and application-command synchronization.
- Added a basic FastAPI application in `api.py` with root and `/health` endpoints.
- Added `requirements.txt` for the initial Python dependencies.
- Added `.env.example` as a safe environment-variable template.
- Added `.gitignore` to exclude local environments and secret files.
- Updated `README.md` and `docs/ECONOMY.md` with the official Fihcoin name and custom emoji.
- Added the initial project planning documents under `docs/`.

### Not implemented yet
- PostgreSQL schema, database connection, and migrations.
- Wallet and bank operations.
- Tax processing and transaction history.
- Economy commands beyond `/ping`.
- Clan system, shop, and leaderboards.
- Next.js website and Discord OAuth.
- Railway services, variables, and production deployment.

---

## Update entry template

When adding future updates, copy this structure:

```md
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
```
