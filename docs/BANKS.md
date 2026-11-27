# Bank System

Banks are shared vaults scoped to a Discord server. A member can belong to one
bank per server, and bank names are unique within each server. A shared vault is
separate from members' personal bank accounts.

## Commands

- `/bank create name` creates a bank and makes the caller its owner.
- `/bank invite member` lets the owner invite a server member.
- `/bank invites` lists the caller's pending invitations.
- `/bank accept bank_name` and `/bank decline bank_name` respond to invitations.
- `/bank view` shows the caller's bank; `/bank view bank_name` looks up any bank
  in the server, including its vault balance, capacity, and storage level.
- `/bank deposit amount` and `/bank withdraw amount` move currency between a
  member's wallet and the shared vault. The owner transacts immediately; other
  members' requests are sent to the owner by DM for approval or rejection.
- `/bank shop` shows the next capacity upgrade and its cost.
- `/bank upgrade` lets the owner buy the next upgrade from their personal wallet.
- `/bank transfer-owner member` transfers ownership to a current member. Owners
  must transfer ownership before using `/bank leave`.
- `/bank leave` removes a non-owner member.
- `/bank disband confirmation_name` lets the owner disband after typing the
  exact bank name; the vault must be empty.

Membership, financial, and ownership operations are checked in the service
layer and persisted in PostgreSQL. Deposit and withdrawal changes to the wallet
and shared vault, together with their economy and bank transaction records, are
committed atomically. Owner approvals are delivered privately with persistent
Approve and Decline buttons; results are DM'd to the requester. If the owner
cannot receive DMs, the request is cancelled.

## Vault upgrades

- New banks start at level 1 with a capacity of **100,000 Fihcoins**.
- Each upgrade multiplies capacity by **1.5**, up to level 10.
- The first upgrade costs **125,000 Fihcoins**; each later upgrade costs 1.5
  times the previous upgrade.
- Upgrade costs are deducted from the owner's personal wallet. Upgrades do not
  spend money from the shared vault.
- Currency amounts are stored to two decimal places. Deposits cannot exceed
  capacity, and withdrawals cannot exceed the vault balance.
