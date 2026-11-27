# Railway Deployment Plan

Railway is the selected hosting platform for Economic Bot. The project is designed for cloud-based development and deployment so the bot can continue running when the developer's personal computer is shut down or switched off.

## Confirmed stack

- **Discord bot:** Python + discord.py
- **Backend API:** FastAPI
- **Database:** PostgreSQL
- **Website:** Next.js

## Planned Railway service layout

- **Bot service:** runs `python bot.py`.
- **API service:** runs `uvicorn api:app --host 0.0.0.0 --port $PORT`.
- **Website service:** Next.js application (planned).
- **Database:** Railway PostgreSQL service.

The bot and API can use the same repository with separate Railway services and start commands. Keep their processes independent so they can be restarted and deployed separately.

## Environment variables

Secrets must be stored in Railway Variables and must never be committed to Git.

Initial configuration:

- `DISCORD_TOKEN` — Discord bot token, bot service only.
- `DISCORD_GUILD_ID` — optional development server ID for fast guild command sync.
- `DATABASE_URL` — PostgreSQL connection URL.
- `PORT` — supplied by Railway for the API service.

Later configuration will include Discord OAuth credentials, session/signing secrets, public website URL, and API base URL.

## Deployment principles

- Use separate development/staging and production environments where practical.
- Pin dependencies and use reproducible start commands.
- Add and verify health checks for web services.
- Keep the bot process independent from web request workers.
- Run database migrations safely and predictably.
- Never print tokens, passwords, or full connection strings in logs.
- Do not rely on an ephemeral container filesystem for durable data.
- Test graceful shutdown and restart behavior.

## Initial deployment sequence

1. Connect the GitHub repository to a Railway project.
2. Provision Railway PostgreSQL.
3. Deploy the API and verify `/health`.
4. Deploy the bot and verify its Discord gateway connection and `/ping` command.
5. Implement database models and migrations.
6. Deploy the website and configure Discord OAuth after its callback URL is known.
7. Verify that the bot and website use the same economy data.

The repository scaffold is prepared, but no Railway project, services, variables, or database have been configured yet.
