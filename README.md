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
- `api.py` — FastAPI service with basic health endpoints

## Local development

1. Use Python 3.11 or newer.
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your Discord bot token.
4. Start the bot: `python bot.py`
5. Start the API separately: `uvicorn api:app --host 0.0.0.0 --port 8000`

Never commit your `.env` file or share your Discord bot token.

## Railway

Deploy the repository as separate Railway services:

- Bot start command: `python bot.py`
- API start command: `uvicorn api:app --host 0.0.0.0 --port $PORT`
- PostgreSQL: add a Railway PostgreSQL service and provide its connection URL as `DATABASE_URL`

The database integration, migrations, economy commands, and website are not implemented yet.
