# ADR 0004: Immutable snapshots and reviewed merge

- Status: Accepted
- Date: 2026-07-27

## Decision

Identity snapshots are immutable. Forks name an explicit base snapshot. A merge proposal is
inert until a human accepts or edits it. Applying an approved proposal creates a child
snapshot and advances the core pointer. Rollback only moves that pointer and creates an
audit event; it does not mutate historical snapshots.

Conflict resolutions are limited to `coexist`, `select`, `synthesize`, `suspend`, and
`reject`. Uncertain conflicts default to `suspend`.
