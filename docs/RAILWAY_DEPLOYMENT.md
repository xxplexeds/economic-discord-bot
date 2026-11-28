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
- **Website service:** runs the Next.js app from `web/`.
- **Database:** Railway PostgreSQL service.

The bot and API can use the same repository with separate Railway services and start commands. Keep their processes independent so they can be restarted and deployed separately.

## Environment variables

Secrets must be stored in Railway Variables and must never be committed to Git.

Initial configuration:

- `DISCORD_TOKEN` — Discord bot token for the bot and API services; never expose it to the website.
- `DISCORD_GUILD_ID` — optional development server ID for fast guild command sync.
- `DATABASE_URL` — PostgreSQL connection URL.
- `PORT` — supplied by Railway for the API service.

Dashboard configuration:

- `RELEASE_GUILD_ID` — the single Discord server served by the dashboard.
- `DISCORD_CLIENT_ID` and `DISCORD_CLIENT_SECRET` — Discord OAuth application credentials.
- `DASHBOARD_SESSION_SECRET` — random server-only secret with at least 32 characters.
- `DASHBOARD_API_URL` — public API origin, also used to build the OAuth callback URL.
- `DASHBOARD_FRONTEND_URL` — public website origin, also used for credentialed CORS.
- `NEXT_PUBLIC_API_URL` — public API origin compiled into the Next.js browser app; contains no secret.

Register `{DASHBOARD_API_URL}/auth/callback` as the Discord OAuth redirect URI.
Keep the API and website on HTTPS in production; the API issues an HTTP-only,
secure session cookie and restricts CORS to the configured website origin.

For the website service, build with `cd web && npm ci && npm run build` and start
with `cd web && npm start`. Set `NEXT_PUBLIC_API_URL` at build time.

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
5. Add and apply versioned database migrations before production schema changes.
6. Configure Discord OAuth, then deploy the website from `web/` with the dashboard variables above.
7. Verify login, current guild membership and admin checks, and that the bot and website use the same economy data.

The repository scaffold is prepared, but no Railway project, services, variables, or database have been configured yet.
