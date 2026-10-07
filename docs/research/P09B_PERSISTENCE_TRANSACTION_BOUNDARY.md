# P09B — persistence/transaction boundary research ledger

Date: 2026-10-08
Status: **PASS_P09B_SQLITE_TRANSACTION_HARNESS / runtime integration NOT_RUN**.

## New narrow finding

The repository has three different durable-looking identifiers that must not be
collapsed into one persistence claim:

| Input | What it proves | What it does not prove |
|---|---|---|
| Identity DB migration/schema version | Identity schema installation is transactionally recorded | Game inventory durability or result idempotency |
| `game.account.v1` `profile_version`/`snapshot_revision` + `profile_sha256` | A bounded server-owned profile snapshot belongs to the authenticated account | A write lock, mutation transaction, reservation, or replay key |
| profile4 parent/grant SHA chain | Offline fixture provenance and measured r3→r4 content delta | A live DB commit, restart recovery, or native account write |

**VERIFIED:** the identity migration is wrapped in `BEGIN IMMEDIATE` /
`COMMIT` with a schema ledger; ownership assertion creation checks identity
subject, profile subject, creation time and exact profile digest; the profile4
chain and semantic diff are bundle-rooted and read-only; the battle-loadout
adapter rejects mismatched revisions/hashes and explicitly does not reserve or
consume resources.

**INFERRED:** these pieces intentionally stop before a game-state transaction.
No current receipt ties an accepted command key to an atomic game ledger row plus
new profile snapshot revision. Therefore P09B must first define that boundary
rather than treating a profile hash or grant ID as an idempotency token.

## Source anchors

| Source | SHA256 | Classification |
|---|---|---|
| `server/identity/schema.mjs` | `2eddafd18f40148ec9096fed4450314e45ce46e8b84bef75e9cce396ebc24d15` | VERIFIED identity migration shape |
| `server/identity/ownership.mjs` | `4a8af6182f5616405c221d32226b9e00fbbf4b9ada3fb7b5152254f1ddb6043d` | VERIFIED ownership DTO/bounds |
| `server/identity/account_service.mjs` | `70be93bd0dac8a76e65f39057e68e60a58eec69f766497ff7db95ba9f83bb6d9` | VERIFIED identity-store transaction calls |
| `server/gateway/src/battle/profile4_adapter.rs` | `642b2b0b2b4f71214bba166ca3960847b582ba77e4b4d2a6d5af0c2620bea95d` | VERIFIED no reservation/consumption boundary |
| `tools/profile4_chain.py` | `c1e5779c1dba399f6dd9066783b1c0eb81a2a77acea6653518fdbab862997070` | VERIFIED offline provenance verifier |
| `tools/profile4_semantic_diff.py` | `7b8f536111a7a9613895d667e51b9ea44515a3d16fc4a4254d00baa0d4cda36d` | VERIFIED bounded semantic diff |

Accepted profile4 manifest: `d99f2ba765e39d096cf2d0858c9864ed897a36eb9c4ea6972a15385e2355b2db`.
The current semantic-diff JSON is
`local/evidence/20261006-profile4-semantic-diff/semantic-diff.json`,
SHA256 `dd3428eacdfb3888f04fd59c3a1c2a17e07524405ec0dd704f040b00da062b01`.

## Required future invariants (proposal, UNKNOWN until implemented)

- One server-owned command/result key is unique per account and domain action.
- One SQLite transaction atomically records the ledger row and resulting game
  snapshot; source and destination revisions are adjacent and monotonic.
- Replaying a committed key returns the saved result without another delta.
- A stale expected revision, unknown vehicle, reserved vehicle, negative balance,
  malformed digest, or cross-account aggregate fails without a partial write.
- Recovery after process/database restart leaves either the prior committed
  snapshot or the complete new snapshot; no half-applied ledger is accepted.

No SQL schema, command key format, reservation lease or economic formula is
claimed as measured in the native client. Those remain **UNKNOWN** for runtime
integration. The isolated implementation receipt below is a harness boundary,
not native compatibility. Live game persistence integration and native
acceptance remain **NOT_RUN**.

## 2026-10-08 isolated transaction harness

**VERIFIED:** the selected narrow command is a server-owned `reserve_vehicle`
operation in `tools/game_profile_tx.py`. The stdlib SQLite schema separates a
`game_snapshot` aggregate, `game_vehicle` rows and a
`game_command_ledger`. A `BEGIN IMMEDIATE` transaction inserts the ledger row,
updates the reserved vehicle and advances the snapshot revision as one unit.
The ledger stores a canonical payload SHA-256 and result JSON, so a repeated
`(account_id, command_id)` returns the original result without a second
revision, while a payload mismatch rejects the replay.

**VERIFIED:** targeted `tests.test_game_profile_tx` is 13/13 PASS. The
receipt `local/evidence/20261008-p09b-transaction-harness-01/receipt.json`
has SHA-256
`cedec631a51a5bf802381f04ad6690582518f3b341e0ce1f78e4bd775a614150` and status
`PASS_P09B_SQLITE_TRANSACTION_HARNESS`. It covers duplicate replay and
mismatch, stale revision, unknown/reserved vehicle, malformed revision,
non-finite persisted JSON, injected rollback, and reopen/replay persistence.

**INFERRED / NOT_IMPLEMENTED:** this receipt proves only the harness boundary.
The schema is not a migration for the deployed service; there is no battle
lease expiry, release/consume policy, result/economy mutation, identity binding,
concurrency/load claim, gateway route, client callback, or native restart
acceptance. Failpoint rollback is deterministic unit evidence, not an OS crash
or power-loss experiment.

## What was and was not run

Read-only source/receipt inspection and hash verification were run for this card.
Existing profile4 chain/semantic-diff/account ownership tests are cited as prior
shape/provenance evidence. No game persistence code, SQLite migration, deployed
service, native client or restart experiment was run for P09B.
