# Transactions

Applied repairs are reversible because DataForge15 writes transaction evidence
before it mutates the source CSV.

## Journal contents

- Transaction identifier.
- Source path and immutable pre-mutation snapshot.
- Planned cell fixes.
- Post-state hash guard.
- Applied and reverted events.

## Revert invariant

Revert is byte-for-byte only when the current file still matches the recorded
post-state hash. If another process changed the file after the DataForge15 apply,
the revert is refused to avoid losing unrelated work.
