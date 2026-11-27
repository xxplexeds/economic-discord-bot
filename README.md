# Fihcoin Economic Bot

A single-server Discord economy built around **Fihcoins (Fish Coins)**.

Official currency emoji: `<:fihcoin:1575710572907987064>`

## Current project decisions

- One Discord server for the first release
- One currency: Fihcoins (singular: Fihcoin), meaning Fish Coin
- Official Discord currency emoji: `<:fihcoin:1575710572907987064>`
- PostgreSQL database
- No gambling mechanics
- Python + discord.py bot
- FastAPI backend
- Next.js website (planned)
- Railway hosting

## Initial services

- `bot.py` — Discord bot entry point with a `/ping` command
- `api.py` — FastAPI service with database-aware `/health` endpoint
- `database.py` — async SQLAlchemy engine, sessions, and PostgreSQL checks
- `models.py` — initial player, account, and transaction tables

## Database foundation

The schema stores players, personal wallet/bank accounts, shared banks and vaults, and transaction records. Balances use PostgreSQL `NUMERIC(20, 2)` and database constraints prevent negative balances. Both the bot and API verify the database connection and create missing initial tables during startup; startup also renames legacy clan tables and applies additive migrations for existing shared-bank tables.

See [docs/DATABASE.md](docs/DATABASE.md) for details. Versioned schema migrations will be added before future production schema changes.

## Local development

1. Use Python 3.11 or newer.
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your Discord bot token and PostgreSQL URL.
4. Start the bot: `python bot.py`
5. Start the API separately: `uvicorn api:app --host 0.0.0.0 --port 8000`
6. Check `/health`; it should return both `"status": "healthy"` and `"database": "connected"`.

Never commit your `.env` file or share your Discord bot token or database URL.

## Railway

Deploy the repository as separate Railway services:

- Bot start command: `python bot.py`
- API start command: `uvicorn api:app --host 0.0.0.0 --port $PORT`
- PostgreSQL: add a Railway PostgreSQL service and provide its connection URL as `DATABASE_URL`

For both application services, a Railway reference such as `${{Postgres.DATABASE_URL}}` can be used when the database service is named `Postgres`.

The `/bank` group supports shared server vaults, owner-approved member deposits
and withdrawals, and owner-purchased storage upgrades. Shared bank funds are
separate from each member's personal bank account; deposits and withdrawals
move currency between the shared vault and the member's wallet.
