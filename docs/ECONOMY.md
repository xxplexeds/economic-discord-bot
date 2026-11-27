# Economy Rules

This document records the current economy direction. Values, command names, and edge-case policies remain configurable decisions until explicitly approved.

## Currency model

- **Release 1 uses one currency only.** Multiple currencies are out of scope for the first release.
- The project targets one Discord server; there is no need for multi-server economy configuration in Release 1.

The planned account model has two balances:

- **Wallet:** currency available for everyday spending and transfers.
- **Bank:** currency stored separately from the wallet.

Deposits move currency from wallet to bank. Withdrawals move currency from bank to wallet. These are internal virtual-currency movements and do not represent real-world money.

Bank limits and the exact deposit/withdrawal rules still need to be decided.

## Taxes

Taxes are administrator-configurable. Each tax type has its own rate and administrator-controlled destination.

| Tax type | Proposed trigger | Treatment |
| --- | --- | --- |
| Income tax | A member receives eligible earnings | Deduct from the earning amount |
| Transfer tax | A member sends currency to another member | Deduct from the transfer amount |
| Purchase tax | A member buys an item | Add to the purchase cost |
| Withdrawal tax | A member moves bank funds into their wallet | Deduct from the withdrawn amount |

### Confirmed tax requirements

- Each tax type has an independently configurable rate.
- Tax proceeds go to an administrator-controlled destination.
- Tax deductions appear in transaction history.

### Withdrawal tax clarification

The proposed meaning of withdrawal tax is a fee applied when moving funds from the bank to the wallet. Whether this tax type is included in the first release is still undecided.

### Transaction integrity

A taxed operation must be processed as one logical transaction. The balance movement, tax collection, and history records must either all succeed or all fail. The system must prevent negative balances unless a future, explicit policy allows them.

Tax configuration must validate rates and destination accounts before it can be used.

## Transaction history

History should make it possible to understand:

- Who initiated the operation.
- Which account or balance was affected.
- The gross amount.
- The tax or fee, if any.
- The net amount received or spent.
- The destination or source.
- When it occurred.
- Whether it was a member action or an administrative adjustment.

Administrative adjustments should record the acting administrator and a reason.

## Administrative currency operations

Requested Candy Bot-inspired operations include adding, removing, and subtracting currency. Exact command semantics, permissions, and confirmation behavior are still to be specified.

All administrative balance changes must be logged and must not silently overwrite history.
