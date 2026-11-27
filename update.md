# Fihcoin Economic Bot — Update Log

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
- These changes are on feature/admin-dashboard-foundation, based on the open PostgreSQL foundation PR. They are not merged, deployed, or live.
- OAuth login, authorization enforcement, block/unblock endpoints, audit UI, analytics, maintenance controls, Discord log delivery, and backup jobs still require implementation and testing.
- PR #3 must be merged and deployed before Railway can create/use these additional model tables.

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
- Merge/deploy PR #3 and verify /health reports database connected.
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
