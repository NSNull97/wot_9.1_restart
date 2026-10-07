# P09B — game profile persistence and transaction boundary

Status: **HARNESS_ACCEPTED; runtime integration and native acceptance NOT_RUN**.
Implementation branch: `codex/p09b-transaction-harness`.

## Goal

Close one narrow P09 seam before adding purchases, progression, or economy:
separate identity durability, immutable profile4 provenance, and future game-state
writes, then define the transaction/idempotency boundary that a later persistence
implementation must satisfy. This card records the contract and acceptance gate;
it does not add a database table, write path, migration, ledger, reservation,
worker wiring, or native client behavior.

The accepted `game.account.v1` assertion is an ownership/integrity assertion.
`profile_version` and `snapshot_revision` identify the server-owned snapshot that
was hashed; they are not a transaction ID, a lock, a reservation, or proof that a
mutation was committed.

## Existing boundary (VERIFIED)

- `server/identity/schema.mjs` declares append-only identity migrations. The
  migration and its `schema_migrations` row are executed in one SQLite
  transaction by `server/identity/account_service.mjs`. That service owns
  credentials, browser sessions, and account profile fields; it is not a game
  inventory store.
- `server/identity/ownership.mjs` builds an exact `game.account.v1`
  `ownership/assert` envelope only after matching the identity subject to the
  server-owned game profile and hashing bounded profile bytes. Its DTO has no
  transaction token, event ID, reservation, balance delta, or replay key.
- `tools/profile4_chain.py` verifies an immutable bundle-rooted
  `profile4-r4 -> r3 -> r2 -> r1-catalog2` chain. Parent profile SHA links,
  revision numbers, grant links, and preserved `shop.bin`/`dossier.bin` hashes
  are provenance checks; the verifier does not open SQLite or publish writes.
- `tools/profile4_semantic_diff.py` proves the measured r3→r4 MS-1 delta only:
  revision 3→4 and the bounded ammunition addition. It does not prove a durable
  mutation, replay protection, or restart recovery.
- `server/gateway/src/battle/profile4_adapter.rs` binds a trusted assertion to
  the accepted profile4 MS-1 domain loadout. The adapter explicitly creates no
  reservation, consumption, expiry, result, or battle admission and emits no
  native bytes.

These facts establish a new, narrow negative boundary: no accepted component
currently owns a durable game-state mutation transaction or exactly-once result
ledger. Existing hashes and revisions are useful preconditions, not substitutes
for that ledger.

## P09B contract proposal (INFERRED; not implemented)

A future game-state write must be a server-owned command with this sequence:

1. Authenticate the caller and validate the current `game.account.v1` subject.
2. Read the current game aggregate and require the expected snapshot revision;
   stale revisions fail closed.
3. Validate the domain delta (for example, one bounded reservation or one
   accepted battle result) without trusting client balances, prices, timestamps,
   coordinates, HP, or hit results.
4. Under one game-store transaction, insert a unique server-generated command or
   result key, append the domain ledger row, apply the new aggregate snapshot, and
   advance `snapshot_revision` exactly once.
5. Commit the complete unit. A repeated key returns the original committed result
   and performs no second balance, inventory, reservation, or reward change.

The first implementation should choose one command family and one SQLite test
schema. It must keep identity credentials/session rows out of the game
transaction, bind every ledger row to `account_id`, aggregate ID, source
revision, destination revision, ruleset and a canonical payload digest, and
reject duplicate keys, stale revisions, negative balances, unknown inventory
IDs, and writes to an active battle reservation. The precise SQL schema,
command names, lease policy, and result economics remain **UNKNOWN** until that
implementation card is selected.

The reservation lifecycle is a future domain policy, not an existing runtime:
`available -> reserved(battle_id, source_revision) -> released | consumed`.
A disconnect/restart must leave one unambiguous state; no automatic reward or
release is implied by this planning card.

## Isolated implementation receipt (2026-10-08)

The selected command family is the bounded server-owned `reserve_vehicle`
command. `tools/game_profile_tx.py` creates a stdlib SQLite schema with a game
snapshot, vehicle rows, and a command ledger. It commits the reservation,
adjacent snapshot revision, and ledger result under one `BEGIN IMMEDIATE`
transaction. A duplicate command key with the same canonical payload replays
the saved result; a changed payload, stale revision, unknown vehicle, or
already reserved vehicle fails closed. The harness also reopens the database
after an injected pre-commit failure and verifies that no vehicle, revision, or
ledger row was partially written.

Targeted `tests.test_game_profile_tx` has **13/13 PASS**. The deterministic
ignored receipt is `local/evidence/20261008-p09b-transaction-harness-01/receipt.json`
(SHA-256 `cedec631a51a5bf802381f04ad6690582518f3b341e0ce1f78e4bd775a614150`)
with status `PASS_P09B_SQLITE_TRANSACTION_HARNESS`.

This is a standalone test harness. It is not wired into the identity service,
gateway, battle runtime, deployed database, client, economy, reservation lease,
release/consume lifecycle, migration runner, or native restart. SQLite schema
details and failpoint names are harness choices, not measured native protocol.
Those integration and compatibility claims remain **NOT_RUN**.

## Evidence and limits

- Profile4 bundle manifest SHA256:
  `d99f2ba765e39d096cf2d0858c9864ed897a36eb9c4ea6972a15385e2355b2db`.
- `game.account.v1` and profile4 source files remain hash-bound by the current
  repository. The current profile4 semantic receipt is
  `local/evidence/20261006-profile4-semantic-diff/semantic-diff.json` (SHA256
  `dd3428eacdfb3888f04fd59c3a1c2a17e07524405ec0dd704f040b00da062b01`).
- Existing identity/account and profile4 unit suites are evidence for shape and
  provenance only. They do not exercise a game DB restart, crash between ledger
  and snapshot, duplicate result after restart, vehicle reservation, or balance
  mutation.
- Live identity/game service, deployed gateway, original/research client,
  database migration, game persistence, economy, purchases, progression,
  reservation and native restart are **NOT_RUN** for P09B.

## Acceptance and rollback

Docs-only acceptance label:
`PASS_P09B_PERSISTENCE_TRANSACTION_BOUNDARY_PLAN`.
It means the ownership/provenance boundary and missing transaction semantics are
explicit and reviewable. It does not claim persistence support or native
compatibility. Revert this docs-only commit and remove its evidence-index row;
no runtime or database restoration is required.

## Single next step

Implement one isolated game-profile SQLite transaction harness for a selected
command family (prefer one vehicle reservation or one battle-result idempotency
case), with migration, crash/restart replay, stale-revision and duplicate-key
negative tests. Keep it off the deployed service until that receipt passes.
