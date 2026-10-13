# P09C ammunition service — isolated domain and integration contract

Date: 2026-10-13. Base: `90c7a1d92a67be2acf2d02ab9a5720a377c9f2c8`.
Branch: `codex/p09c-ammo-service`; separate managed worktree. Parallel handoff,
no merge/main checkout change. Acceptance applies only to this isolated card.

## Existing work and new boundary

P02_MS1_AMMO already verified the native MS-1 mounted capacity, three shell
types and immutable profile4 grant of 20 AP; repeating that grant is not the
goal. P03I records vehicle/loadout/native handoff boundaries. The accepted
profile4 battle adapter and original Avatar ammo codec remain untouched.
P09B already supplies the isolated SQLite game snapshot, ownership/reservation
rows, shared revision and idempotent command ledger. P09C extends those same
interfaces with owned depot-to-tank service; it does not create another game
store, deploy a migration, or interpret a native service message.

## Source facts and classifications

**VERIFIED_STATIC_ORIGINAL_717:** fresh bounded read-only audit of nine exact
original files, resolved through the primary checkout's existing
`config/project.local.json` / `tools/client_audit.py:config`, at
`C:\WoT_0.9.1_RU_0717_original`. No client execution was needed or performed.

| Mount | Vehicle CD | Turret / CD | Gun / CD | Mounted capacity | Compatible shell CDs, in source order |
|---|---:|---|---|---:|---|
| `ms1-stock` | 3329 | `T-18_Standart` / 5891 | `_37mm_Gochkins` / 5892 | 96 | 2570 AP, 2826 HEAT, 3082 HE |
| `is7-stock` | 7169 | `IS-7` / 12035 | `_130mm_S-70` / 14852 | 30 | 14602 AP, 14858 APCR, 15114 HE |

The original vehicle-specific `maxAmmo` overrides are mandatory. Shared gun
defaults are 92 and 28 respectively and are not the mounted capacities.
Shell definitions and the mounted gun's ordered `shots` membership both agree.
IS-7 shell resource names are `_130mm_UBR-482`, `_130mm_UBR-482P`,
`_130mm_UOF-482` (item IDs 57/58/59).

The bounded inert Python 2.7 parser verifies original `makeIntCompactDescrByID`
at source line 2708: `(itemID << 8) + (nationID << 4) + itemTypeID`.
Original nation order gives USSR=0; item type IDs are vehicle=1, turret=3,
gun=4, shell=10. This establishes static IS-7 compact IDs; it is not a fresh
native IS-7 ammunition export or confirmation of service callback delivery.
The historical IS-7 UI06 export referenced by old research was absent during
this audit; its native evidence is not claimed here.

Nine exact sizes/SHA256 are in `tools/p09c_ammo_catalog.py:SOURCE_PINS` and
the local source receipt. Vehicle XML pins:

- MS-1: `a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535`.
- IS-7: `8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d`.
- Guns: `889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b`.
- Shells: `ed301edbe07a72b04dc6c6d799bc563de55d0d1f26bd35798354a9f6769e7a96`.

The complete catalogue fingerprint is
`9c50c64b85c6301e64145f9fbb90450417dc9063bcd8c136ac6de0c9cbabca62`.
Only metadata, hashes and independently authored code are tracked; original
resources/bytecode, DBs and observations stay outside Git.

## Versioned domain contract

`AmmoServiceStore` subclasses the existing P09B `GameProfileStore`.
The existing `game_snapshot`, `game_vehicle` and `game_command_ledger` retain
their roles. Two namespaced tables hold mounted ammunition and per-account
depot stock; a schema marker and `p09c_result_sha256` ledger column bind the
extension. Snapshot `p09c-ammo-service.v1` includes the catalogue fingerprint,
loaded counts and depot projection, with the same aggregate revision.

`set_ammunition` takes only trusted authenticated subject, target account,
server-owned command key, owned inventory vehicle ID, expected aggregate
revision and an absolute desired map of domain shell IDs to counts. A caller
cannot supply a mounted gun, capacity, inventory balance, price or result.
The service reads the current mounted configuration from the owned record.
Omitted compatible types mean zero/unload. Explicit incompatible types reject
even at zero quantity. Dictionary order does not affect idempotency; an omitted
key versus an explicit zero is a different command payload in v1.

Examples of domain IDs: `shell:ms1-stock-ap` (preserves P02's ID),
`shell:is7-stock-ap`, `shell:is7-stock-apcr`, `shell:is7-stock-he`.
Native compact IDs are confined to the catalogue adapter.

For each compatible shell:

`new_depot = old_depot + old_loaded - desired_loaded`

Every accepted operation commits depot, load, snapshot revision and ledger
result in one `BEGIN IMMEDIATE` transaction. Replayed commands return the
original committed result without reapplying it, even after later revisions
or reopening the DB. A distinct no-change command still advances the revision
once; this is an explicit harness command policy, not historical native UI
semantics. Command keys share the P09B reservation namespace; cross-family
reuse rejects.

Authenticated-subject mismatch rejects before replay lookup. Stale revisions,
unknown/unowned vehicles, reservations, unsupported mounts, incompatible
shells, capacity overflow, insufficient stock and invalid quantity types reject
without partial writes. Revisions, payload bytes, JSON depth, vehicle count and
depot quantities are bounded; the harness depot limit of 1,000,000 per type and
16 vehicles is policy, not a historical claim. Mounted capacities come only
from verified original data. SQLite writer wait is the inherited two seconds.

The reservation method is inherited, with snapshot and replay hooks validating
the extended aggregate and keeping the same revision. P09C also bounds the
inherited reservation increment at the maximum supported revision. Ammo replay
checks result integrity; reservation replay reconstructs the original payload
binding and verifies the current aggregate. These hashes detect corruption;
they do not authenticate a caller or protect a DB against an administrator
rewriting all rows and hashes.

`seed_test_ammunition` is a one-time fixture bootstrap before any command.
It requires revision zero, no ledger, and a mount binding for every owned test
vehicle. Mount rows themselves are the once-only marker, including zero-stock
seeds. Stock is explicitly provided by the test fixture. This method is not a
runtime grant, purchase or source of historical initial loadouts.

## Integration handoff and dependencies

1. Run `audit_sources` against the explicitly configured original root before
   activating this catalogue. The supplied harness performs it before creating
   any DB. A mismatched source rejects activation. Unit fixtures alone do not
   satisfy that source gate.
2. A future trusted adapter authenticates the subject and resolves the owned
   inventory vehicle and its exact mounted type/turret/gun to a catalogue mount.
   Neither caller-controlled account IDs nor fixture mount assignments are live
   identity proof. No native bytes or identity tokens enter this service.
3. All writers of a P09C test DB use this subclass. Existing ordinary P09B/live
   DBs are rejected, not automatically migrated. Deployment requires a separate
   migration/recovery and identity binding card. P09B source remains unchanged.
4. Native service request framing, callback errors, garage cache/layout updates,
   battle reservation/consumption/release and mapping into accepted runtime
   loadout belong to the integration gate. The existing r4 MS-1-only adapter
   does not accept this store or silently gain IS-7 support.

| Area | Coverage in this card | Dependency before use |
|---|---|---|
| Compatible ammo and capacity | VERIFIED source metadata for two exact mounts | Trusted inventory mount mapping at runtime |
| Reload tank from owned depot / change shell mix | Isolated atomic service | Identity, persistent deployment, native request/response and UI gate |
| Buy shells / auto-buy | Explicit `PURCHASE_UNSUPPORTED`; no financial mutation | Proven historical prices/currency policy and economic ledger |
| Repair | UNKNOWN / unsupported | Authoritative post-battle durability, original repair semantics and prices |
| Consumables | UNKNOWN / unsupported | Original equipment descriptors/slots, stock, activation/consumption semantics and prices |
| Equipment/crew | Outside this card | Separate parallel component and common integration gate |

P02_HANGAR_WINDOWS established that original repair/fill/setLayouts paths
exist but were unsupported. Their existence supplies neither a wire decoder nor
economic rules. Old source `buyPrice/defaultPrice=0` observations are not prices.

## Evidence, limitations and rollback

See [P09C evidence index](../evidence-index/P09C_AMMO_SERVICE.md) for final
commands, counts, receipts and source hashes. The local scenario retains an
isolated DB with both test tanks, service/replay/change and shared reservation.
Deterministic failpoints prove transaction rollback; they are not OS power-loss
tests. Concurrent local connections do not establish distributed persistence.

**OBSERVED:** automatic results recorded in the evidence index on the named
Windows/Python/SQLite environment. **INFERRED/project policy:** absolute desired
load command, depot bounds, seed procedure and schema design. **UNKNOWN/NOT_RUN:**
live native servicing, fresh IS-7 native ammo export, live runtime wiring,
prices, financial ledger, repair, consumables and battle consumption integration.

Rollback is a revert of the P09C commit; no live/client restoration is needed.
Its isolated DB is disposable and must never be copied over a shared DB.
One next step: integrate this exact source-bound contract through a separately
reviewed authoritative account/loadout gate, coordinating crew and equipment;
only then perform native MS-1/IS-7 service acceptance.
