# PostgreSQL Database

The first database foundation uses PostgreSQL through SQLAlchemy's async engine and the asyncpg driver.

## Tables

- `players`: one player record per Discord user per guild.
- `accounts`: wallet and bank balances for each player. Each player can have one account of each type.
- `economy_transactions`: append-only records of economy operations, including sender, recipient, amount, fee, actor, and timestamp.

Balances use `NUMERIC(20, 2)`, not floating-point numbers. Database constraints reject negative balances, invalid account types, non-positive transaction amounts, and negative fees.

## Startup behavior

Both the bot and API verify the PostgreSQL connection and call SQLAlchemy `create_all` to create missing initial tables. This is a bootstrap for the first release, not a replacement for versioned migrations. Before schema changes are deployed to production, add and use Alembic migrations.

## Railway variables

Set `DATABASE_URL` on both the Discord Bot and FastAPI Backend services using the Railway reference:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

The service name inside the reference must match the actual PostgreSQL service name in Railway.

## Transaction history

- The `/transactions` command reads the member's sent and received rows from `economy_transactions`, scoped to the current guild.
- The command response is ephemeral and read-only. Regular members can query only their own history. Discord Administrators and members with active `admin_user_grants` or `admin_role_grants` can inspect another member.
- Use the `record_transaction` helper from `economy.py` inside the same active SQLAlchemy transaction that changes account balances. This keeps the balance update and history row atomic.
- A history page contains 10 records, ordered newest-first. The view provides Previous / Next buttons and a page dropdown.

## Important implementation notes

- Keep the database URL and Discord token in Railway Variables or a local ignored `.env` file.
- Do not commit secrets.
- Future balance-changing operations must use a single database transaction and row-level locking (or conditional updates) so concurrent commands cannot overspend an account.
- Every successful balance-changing operation must write its matching transaction record in the same database transaction.
