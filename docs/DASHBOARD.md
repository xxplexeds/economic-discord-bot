# Fihcoin Dashboard

The initial Next.js dashboard milestone includes a member profile, wallet and
personal-bank balances, transaction history, and an administrator console with
server overview, member lookup, and audited exact-balance setting. The dashboard
uses the same PostgreSQL economy tables as the Discord bot. It does not include
the future access-control, blocking, maintenance, backup, or analytics modules.

## Local development

1. Configure the API variables in `.env`, including `DATABASE_URL`,
   `DISCORD_TOKEN`, `RELEASE_GUILD_ID`, `DISCORD_CLIENT_ID`,
   `DISCORD_CLIENT_SECRET`, `DASHBOARD_SESSION_SECRET`,
   `DASHBOARD_API_URL=http://localhost:8000`, and
   `DASHBOARD_FRONTEND_URL=http://localhost:3000`.
2. Add `http://localhost:8000/auth/callback` as a redirect URI in the Discord
   Developer Portal OAuth2 settings.
3. Start the API with `uvicorn api:app --host 0.0.0.0 --port 8000`.
4. In `web/`, set `NEXT_PUBLIC_API_URL=http://localhost:8000`, install packages
   with `npm install`, and start the site with `npm run dev`.

The session secret must contain at least 32 characters. Keep OAuth credentials,
the Discord bot token, and the session secret in server-side environment
variables only. Never expose them through a `NEXT_PUBLIC_` variable.

## Authorization and data safety

- OAuth uses Discord identity, signed time-limited state, and PKCE.
- The API stores only a hash of the opaque, HTTP-only session cookie and expires
  sessions after seven days.
- Current guild membership is rechecked through the bot API. Admin requests
  also re-check Discord Administrator permission and active user/role grants.
- Mutating requests require a CSRF header. CORS allows only the configured
  frontend origin.
- Exact balance changes require a reason and create both an economy-history
  record and an admin audit record in the same database transaction.
- Member-facing profile and history endpoints only return the signed-in
  member's own data. The admin lookup searches current guild members.

## API routes

| Route | Access |
| --- | --- |
| `GET /auth/login` and `GET /auth/callback` | Discord OAuth2 |
| `GET /auth/me` | Signed-in guild member |
| `POST /auth/logout` | Signed-in member, CSRF protected |
| `GET /api/me` | Own profile and balances |
| `GET /api/me/transactions` | Own paginated history |
| `GET /api/admin/overview` | Current administrator |
| `GET /api/admin/members?query=...` | Current administrator |
| `POST /api/admin/members/{discord_user_id}/balance` | Current administrator, CSRF protected |

Set `RELEASE_GUILD_ID` to the one guild served by the release. `DISCORD_GUILD_ID`
is accepted as a development fallback. `DASHBOARD_API_URL` and
`DASHBOARD_FRONTEND_URL` must be the public origins used by the OAuth callback
and browser; configure the callback URL in Discord to match exactly.

This code is not deployed or live until the API, website, OAuth application, and
production environment variables have been configured and verified.
