# Economic Bot — Project Overview

## Vision

Economic Bot is a Discord-first virtual-currency economy with a companion website. It takes inspiration from the feature breadth of Candy Bot while establishing its own identity, improved user experience, and maintainable architecture.

The Discord bot, website, and backend must use the same source of truth for balances and transactions.

## Confirmed product decisions

- Rebuild Candy Bot-inspired features with improved functionality and a new UI.
- Include a full clan system with a shared treasury, roles, and leaderboards.
- Support administrator-controlled tax destinations.
- Configure each tax type independently.
- Show tax deductions in transaction history.
- Banking is part of the planned economy.
- No gambling mechanics.
- No bank interest.
- Railway is the intended hosting platform.
- Release 1 supports one Discord server only.
- Release 1 uses one currency: **Fihcoins** (singular: **Fihcoin**, meaning Fish Coin).
- PostgreSQL is the selected database.
- The implementation stack is Python + discord.py, FastAPI, PostgreSQL, and Next.js.

## Product principles

1. **Virtual currency only:** balances are in-app game/economy data, not real-money deposits or payments.
2. **No gambling:** no wagering, betting, roulette, slots, coin-flip betting, or chance-based currency games.
3. **Auditability:** balance changes must create traceable transaction records.
4. **Consistency:** bot and website must use the same backend rules.
5. **Permission safety:** administrative actions must be authorized and logged.
6. **Focused first release:** build for one Discord server and one currency; avoid multi-server and multi-currency complexity until a future release.

## Planned product areas

- Member economy commands and profile views.
- Administrative currency management.
- Wallet and bank.
- Configurable taxes.
- Shop and other non-gambling economy features.
- Clans with shared treasury and member roles.
- Leaderboards.
- Website member area and administration panel.

Detailed command names, earning methods, and website permissions remain to be finalized.

## Confirmed technical stack

- **Discord bot:** Python + discord.py
- **Backend API:** FastAPI
- **Database:** PostgreSQL
- **Website:** Next.js
- **Hosting:** Railway

The initial repository scaffold contains a Discord bot entry point and a basic API health endpoint. Database models, migrations, economy logic, and the website are still to be implemented.
