# Development Roadmap

This roadmap separates confirmed decisions from implemented functionality. A checked item means code exists and has been verified; planned items are not yet available to users.

## Phase 1 — Product decisions

- [x] Railway hosting.
- [x] Candy Bot-inspired rebuild with improved functionality and UI.
- [x] One Discord server and one currency for Release 1.
- [x] Fihcoins (Fihcoin) and official custom emoji.
- [x] Python + discord.py, FastAPI, PostgreSQL, and Next.js.
- [x] No gambling and no bank interest.
- [x] Two-decimal currency precision.
- [x] Management access by Discord Administrator permission, User IDs, and Role IDs.
- [x] Economy-level blocks do not ban users from Discord.
- [x] Audit logs, analytics, maintenance, configurable logging, and backups confirmed.

## Phase 2 — Foundation

- [x] Initial Discord bot and FastAPI scaffold.
- [x] PostgreSQL connection and initial player/account/transaction schema in PR #3.
- [ ] Merge and deploy PostgreSQL foundation; verify live database health.
- [ ] Add Alembic migrations before evolving production schema.
- [ ] Add automated tests and CI checks.

## Phase 3 — Core economy

- [ ] Player registration and wallet/bank account creation.
- [ ] Atomic balance service and transaction history.
- [ ] /balance and member profile.
- [ ] Payments, deposits, withdrawals, and configurable taxes.
- [x] Website exact-balance setting with confirmation, transaction history, and audit.

## Phase 4 — Access control and safety

- [ ] Shared authorization service for Discord and website.
- [ ] Discord Administrator permission check.
- [ ] Explicit User ID grants.
- [ ] Explicit Role ID grants.
- [ ] Economy-level block/unblock and blocked-user list.
- [ ] Server-side block enforcement for every economy operation.
- [ ] Preserve balances/history across blocks.
- [ ] Audit permission and block/unblock changes.
- [ ] Prevent removal of the final management access path.

## Phase 5 — Operations

- [ ] Audit log views and filters.
- [ ] Economy analytics.
- [ ] Maintenance mode and configurable message.
- [ ] Discord log-channel configuration by event category.
- [ ] Scheduled encrypted backups stored separately from PostgreSQL.
- [ ] Backup history, integrity checks, and restore procedure.

## Phase 6 — Discord experience

- [ ] Member economy commands and polished Components V2 responses.
- [ ] Leaderboards and transaction history.
- [ ] Consistent permission and blocked-user responses.

## Phase 7 — Next.js website

- [x] Discord OAuth2 login and secure server-side sessions.
- [x] Member dashboard: profile, balances, and history.
- [x] Administrator dashboard: economy overview and current guild member lookup.
- [ ] Administrator dashboard: bot status.
- [ ] Access Control: authorized User IDs, authorized Role IDs, blocked users, and access history.
- [x] Economy management: audited exact-balance setting.
- [ ] Additional economy management and transaction views.
- [ ] Analytics, maintenance, logging, audit logs, and backup management.
- [x] Responsive desktop/mobile layout for the initial member/admin milestone.

## Phase 8 — Banks and other economy features

- [x] Bank creation, invitations, membership, and ownership transfers.
- [x] Shared vault deposits and withdrawals with private owner approval.
- [x] Owner-purchased storage capacity upgrades and empty-vault disbanding.
- [ ] Shop and other approved non-gambling features.

## Phase 9 — Production readiness

- [ ] Staging and end-to-end tests.
- [ ] Production deployment.
- [ ] OAuth/API/admin security review.
- [ ] Backup restore drill and recovery documentation.
