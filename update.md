# Fihcoin Economic Bot — Update Log

## 2026-11-27 — Add bank creation form

### Added
- Replaced the name-only `/bank create` command with a form for a required name and optional description, banner, and logo.
- Store uploaded image URLs from the bank's creation card and show the banner and logo in `/bank view`.
- Added owner-only `/bank edit` with a confirmation prompt, prefilled name and description, and optional image replacements.
- Add additive PostgreSQL columns for bank descriptions and image URLs.

### Notes
- Banner and logo uploads accept PNG, JPEG, GIF, or WebP up to 8 MB each.
- Keep the bank creation card message because its attachments host the bank profile images.

---

## 2026-11-27 — Add shared bank vaults

### Added
- Added shared bank vault deposits and withdrawals, with immediate owner transactions and private owner DM approval for member requests.
- Added private approval/decision notifications, restored persistent approval buttons for pending requests on startup, and cancel requests when the owner cannot receive DMs.
- Added capacity upgrades starting at 100,000 Fihcoins, with 1.5x capacity and cost progression up to level 10.
- Added owner wallet-funded upgrades, ownership transfer, and the empty-vault rule for disbanding.
- Persisted vault balances, upgrade levels, requests, and bank transaction records; personal bank accounts remain separate.

### Notes
- Bank deposits and withdrawals are logged atomically with wallet changes and the shared vault balance.
- `/bank shop`, `/bank upgrade`, `/bank deposit`, `/bank withdraw`, and `/bank transfer-owner` are available alongside membership commands.

---

## 2026-11-27 — Add private transaction history

### Added
- Added the private `/transactions` command with a separate read-only Components V2 message; it does not edit or replace `/balance`.
- Members can view only their own sent and received transaction records.
- Discord Administrators and members with an active configured Administrative Role grant can privately inspect another member's history.
- Added Previous / Next buttons, a page dropdown, 10 records per page, and a 15-minute interactive view.
- Re-check cross-member history permissions when an administrator navigates pages.
- Added transaction-history query and transaction-record helper functions. Balance-changing commands must write the record in the same database transaction as the balance update.

### Notes
- The transaction table already exists. Since balance-changing economy commands are not implemented yet, the history will remain empty until those commands use the transaction-record helper.
- The configured Administrative Role currently uses the existing `AdminRoleGrant` database records; a dashboard control for managing those grants is not part of this change.
- The `/transactions` response is ephemeral. The Discord client displays the "Only you can see this" banner.

---

## 2026-11-27 — Add interactive leaderboard pagination

### Added
- Added Previous and Next buttons to the public Components V2 leaderboard.
- Added a page dropdown for jumping directly between leaderboard pages.
- Display 10 members per page, current page, total pages, and total ranked members.
- Keep ranking numbers continuous across pages and disable mention notifications during page updates.

---


## 2026-11-27 — Add leaderboard section divider

### Changed
- Split the leaderboard title, Top 10 description, and member rankings into separate Components V2 sections with a native Discord Separator between the description and rankings.
- Kept the server icon and silent clickable member mentions.

---


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
- Blocked users cannot earn, receive, transfer, deposit, withdraw, purchase, or use bank economy features.
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
- Implement economy commands, atomic balance operations, banks, shop, leaderboards, and website.

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
- Economy commands beyond /ping, balance operations, taxes, transaction history, banks, shop, leaderboards, website, and Discord OAuth.

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
