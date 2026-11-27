# Clan System

## Direction

Economic Bot will include a full clan system with a shared balance, member roles, and clan leaderboards.

## Planned capabilities

- Create a clan.
- Invite members and accept or decline invitations.
- Join and leave clans according to configured rules.
- Manage clan membership.
- Assign clan leadership and officer roles.
- Contribute currency to a shared clan treasury.
- View the clan treasury balance.
- View clan rankings and leaderboards.
- Review clan activity and treasury transaction history.

## Roles

The proposed hierarchy is:

1. **Owner:** full clan management authority.
2. **Officer:** delegated membership and clan-management permissions.
3. **Member:** standard participation and contribution permissions.

The exact permission matrix and owner-transfer rules remain to be finalized.

## Treasury rules

The clan treasury is separate from every member's personal wallet and bank.

Every treasury movement must have its own transaction record containing the actor, amount, action, timestamp, and resulting balance. Contributions must debit the member and credit the treasury as one atomic operation.

Treasury spending, withdrawal permissions, clan creation costs, and clan capacity limits are not finalized yet.

## Leaderboards

The clan leaderboard should rank clans using a clearly defined metric. Treasury balance is one possible metric, but the final ranking rules must be selected before implementation.

## Safety and integrity

- A member must not be able to spend from the clan treasury without permission.
- Clan role checks must be performed by the backend, not only hidden or disabled UI controls.
- Clan membership changes and treasury movements must be auditable.
- Clan data must remain scoped to the correct Discord server if server-specific clans are selected.
