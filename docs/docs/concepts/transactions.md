# Transactions

Applied repairs are reversible because DataForge15 writes transaction evidence
before it mutates the source CSV.

## Journal contents

- Transaction identifier.
- Source path and immutable pre-mutation snapshot.
- Planned cell fixes.
- Post-state hash guard.
- Applied and reverted events.
- A local hash chain for newly written v2 events: each event records its index,
  the previous event hash, and its own SHA-256 over canonical JSON.

## Audit

Run `dataforge15 audit <txn-id>` to verify a transaction log before relying on
it as audit evidence. A verified v2 log proves local event order, payload
integrity, and replayability. Legacy v1 logs can still be replayed and reverted,
but audit reports mark them `legacy_unverified` because they do not contain
event hashes.

The hash chain is tamper-evident inside the local workspace. It is not an
external non-repudiation system unless the head hash is anchored in a separate
trusted system.

## Revert invariant

Revert is byte-for-byte only when the current file still matches the recorded
post-state hash. If another process changed the file after the DataForge15 apply,
the revert is refused to avoid losing unrelated work. For v2 logs, revert also
refuses when audit verification fails.
