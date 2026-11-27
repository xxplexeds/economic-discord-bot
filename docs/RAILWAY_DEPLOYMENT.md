# Railway Deployment Plan

Railway is the intended hosting platform for Economic Bot.

## Planned service layout

The exact topology depends on the selected application stack. The expected logical services are:

- **Bot service:** runs the Discord bot process.
- **API service:** serves shared economy logic to the bot and website.
- **Website service:** serves the member dashboard and administration interface.
- **Database:** persistent storage, either a Railway-managed database or an external provider.

These may be combined during early development if the chosen framework supports it cleanly. They should remain logically separated so they can be scaled and restarted independently later.

## Environment variables

Secrets must be stored in Railway Variables and must never be committed to Git.

Expected configuration categories include:

- Discord bot token.
- Discord application/client ID and OAuth client secret (when website login is implemented).
- Database connection string.
- API signing/session secret.
- Public website URL.
- API base URL.
- Environment name and logging level.

The final variable names will be documented after the stack is selected.

## Deployment principles

- Use separate development/staging and production environments where practical.
- Pin dependencies and use a reproducible build/start command.
- Add health checks for web services.
- Keep the bot process independent from web request workers.
- Run database migrations or initialization steps safely and predictably.
- Never print tokens, passwords, or full connection strings in logs.
- Configure persistent storage for any service that requires local files; do not rely on an ephemeral container filesystem for durable data.
- Test graceful shutdown and restart behavior.

## Initial deployment sequence

1. Select and implement the application stack.
2. Add a local development setup and environment template without secrets.
3. Connect the repository to a Railway project.
4. Provision/configure the database.
5. Deploy the API and verify its health endpoint.
6. Deploy the Discord bot and verify gateway connection.
7. Deploy the website and configure Discord OAuth after its callback URL is known.
8. Verify that bot and website read and write the same test data.

No Railway services or credentials have been configured yet.
