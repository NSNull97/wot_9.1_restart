# P04C — source-bound configuration and ammunition reservation

2026-10-13. One isolated integration card after P04B; branch
`codex/p04c-configuration-reservation`. No native installation, gateway,
physics, live inventory or primary-checkout change is part of this card.

## Scope and dependencies

Accepted base is `90c7a1d92a67be2acf2d02ab9a5720a377c9f2c8`.
P04B is `20b5d523cc3d8dbc99f1accef199fa8f390f785a`. P09C dependency
`7fb0e479dce684af0940fe37e5798d54d1c1e7fd` was cherry-picked as
`85c4710a6b826dcef92594df06ccf7310cd25bb1`; the only conflict was
additive STATUS history. Existing P04B domain and P09B/P09C implementation
and tests remain byte-identical to these pins.

The isolated store extends the existing P09C connection, profile projection,
aggregate revision and command ledger. It does not introduce another account
registry or deploy a replacement persistence service. Parallel native ammo
wiring belongs to P09D; runtime IS-7 integration belongs to P03M.

## VERIFIED: exact mounted mass

`tools/crew_equipment_mass.py` uses the established bounded packed-XML and
inert Python 2.7 bytecode readers. Before returning an assembly it rehashes
11 original #717 files, checks the selected component IDs/fields and pinned
`VehicleDescr.__computeWeight` algorithm, and checks two historical native
descriptor exports. Neither original bytecode nor native client code is run.

Paths come exclusively from the explicit existing local configuration.
Original: `C:\WoT_0.9.1_RU_0717_original`, RU `v.0.9.1 #717`.
The canonical whole-client manifest remains
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`;
this card rechecks selected resources, not the full original tree.

| Mass contributor, kg | MS-1 stock | IS-7 stock |
|---|---:|---:|
| Hull | 2750 | 38850 |
| Chassis: T-18 / IS-7 | 1200 | 11000 |
| Engine: MS-1 / M-50T | 266 | 700 |
| Fuel tank: Small / Large | 200 | 300 |
| Radio: Alarm_flags / _10RK-26 | 1 | 160 |
| Turret: T-18_Standart / IS-7 | 170 | 14200 |
| Gun: _37mm_Gochkins / _130mm_S-70 | 104 | 2980 |
| Base total | **4691** | **68190** |
| Chassis maxLoad | **4890** | **70950** |
| Remaining allowance | **199** | **2760** |

All numbers above are verified source values for these exact assemblies.
The MS-1 cannot accept both 100 kg ventilation and 100 kg aim drives on this
chassis: 4891 kg exceeds 4890 kg by 1 kg. Its harness fixture uses ventilation
plus zero-mass optics: 4791 kg. IS-7 uses class3 ventilation, aim drives and
optics: 68490 kg. Unsupported mounted assemblies reject; a vehicle name
alone is not sufficient to choose a mass budget.

Assembly SHA256 pins:

- MS-1: `843de44e80f555730457eff8cbee597b27b71b783a3b49301d1ef9aa3fd866fb`.
- IS-7: `8f22e6743b6c4ed6de68466e62746b38ca3b78119211aa9b66fd966bed352ec9`.

The assembly identity includes the actual selected components and source
pins. Its immutable verified evidence supplies the P04B `MassBudget`.
A constructed Python object or client-supplied evidence JSON is not an
authorization credential.

## Project transaction contract

`ConfigurationStore` first runs actual mass, crew/device and ammunition
source audits, then opens its isolated SQLite file. New schema
`crew-configuration-store.v1` adds one configuration row per owned vehicle;
lower schemas are refused, with no implicit migration of live databases.
Configuration revision is fixed at 1 in this card; aggregate revision starts
at 0 and advances with ammo changes and reservation.

`seed_test_configurations` is a one-time, pre-command fixture operation.
It requires all owned vehicles, matching mounted assemblies, complete crews,
unique crew IDs across the account's vehicles, correct device slots and
source-backed mass. This fixture assignment does not prove real equipment
ownership or grant live tankmen. No network command accepts crew/modifiers.

`reserve_configuration` accepts authenticated account subject, account ID,
command ID, owned vehicle ID, expected aggregate revision, expected stored
configuration SHA256 and battle ID. The trusted caller supplies the subject
from the authenticated session; accepting that field from a client would
violate the contract.

One `BEGIN IMMEDIATE` checks the whole profile, current configuration,
audited mass/policy and loaded ammo, then updates vehicle reservation,
aggregate snapshot/revision and the existing command ledger atomically.
It freezes crew, devices, mass evidence, raw static modifiers and exact loaded
ammo into one result. Ammo was transferred from owned fixture depot during
P09C service; reservation never debits it a second time. Empty ammo rejects.
The inherited unauthenticated `reserve_vehicle` entry point is disabled.

Same command ID and payload return the original frozen result after reopening
the DB and after another vehicle changes. Changed payload or command family
rejects. The replay validates ledger result/payload bindings, current reserved
vehicle, and a freshly rebuilt snapshot. All failures roll back.

`read_reserved_configuration` gives a future battle consumer immutable
canonical `bytes`, bound to authenticated account, reservation command,
battle and expected frozen SHA256. It validates persisted state under one
read transaction. It does not accept an arbitrary caller-provided snapshot
as proof and does not increment revision. No battle worker consumes it yet.

All writers of this extended schema must use this subclass. An old P09C
writer rejects the extended profile projection instead of overwriting it.
The public aggregate read methods remain trusted internal store operations,
not externally authenticated API endpoints.

## OBSERVED: isolated acceptance

The persistent harness uses explicit synthetic accounts Alice/Bob, unique
fixture crews and equipment, and 300 of each of six source-bound shells in
each fixture depot. Actual revision sequence:

1. Seed profiles/configurations at aggregate revision 0.
2. Load 20 AP into MS-1, revision 1.
3. Load 15 AP into IS-7, revision 2.
4. Reserve MS-1, revision 3.
5. Change unreserved IS-7 to 14 AP + 1 APCR, revision 4.
6. Replay the original MS-1 reservation without writing.
7. Reserve IS-7, revision 5.
8. Close/reopen SQLite, replay both reservations and both original service
   commands, and read both frozen snapshots through the consumer method.

The 33 harness checks include shell conservation, no double debit, unchanged
other account, wrong-owner/battle/digest rejection and byte-identical DB
before reopen versus after all reads/replays/rejections. Snapshots and the
persistent database are retained.

The final combined current-head run covers 34 new real SQLite reservation
tests, 19 mounted-mass tests, 44 existing P04B tests, 74 P09B/P09C tests,
16 content regressions and 8 layout tests. Its machine-readable receipt is
the authority for actual totals, failures and skips. The known Windows
symlink fixture is explicitly NOT_RUN when this account cannot create it.
Race tests use separate real connections, including a held read/check point
that keeps the SQLite writer lock until commit. Six injected failure points
cover fixture seed and each reservation mutation boundary.

Independent review also ran 17 checks, including maximum 96-character
account/vehicle IDs with 16 vehicles, reopen/replay and a rehashed false
frozen mass. It found no blocking issue; its receipt is additional evidence,
not a substitute for the current-head suite.

## INFERRED / UNKNOWN and limits

INFERRED: this immutable reservation is a suitable future battle-admission
boundary. Actual worker/native consumption must establish that separately.

UNKNOWN/NOT_RUN: fresh native mass readback; live crew/equipment grants and
stock ownership; account migration/deployment; actual client queue and battle
admission through this store; final crew-to-combat formulas and native float
bit equivalence. Static rational device effects retain the P04B limits.
There is no release/recovery policy or post-battle ammo consumption here.
No purchase prices, progression, repair or consumables are implemented.

Acceptance is **PASS_SOURCE_BOUND_CONFIGURATION_RESERVATION** for the
isolated source/persistence slice only. Native/runtime acceptance is
**NOT_RUN**. The branch stays unmerged/unpushed while parallel integration
and native acceptance remain separate.

## Commands, handoff and rollback

Run from the managed crew worktree:

```powershell
$env:WOT091_CONFIG = 'D:\WoT_9.1_Server\config\project.local.json'
python -B -X utf8 -m unittest -v tests.test_crew_configuration_store tests.test_crew_equipment_mass tests.test_crew_equipment tests.test_crew_equipment_source_audit tests.test_p09c_ammo_catalog tests.test_p09c_ammo_service tests.test_game_profile_tx tests.test_content_import tests.test_content_bundle tests.test_server_layout
python -B -X utf8 tools/crew_equipment_mass.py --config $env:WOT091_CONFIG --out local/evidence/p04c-mass-new
python -B -X utf8 tools/crew_configuration_harness.py --config $env:WOT091_CONFIG --out local/evidence/p04c-harness-new
python -B -X utf8 server/check_layout.py
git diff --check
```

Each output directory must be fresh. The actual final run, commit and code
hashes are recorded under the worktree's ignored
`local/evidence/20261013-p04c-configuration-reservation-01/acceptance-final/`.
Do not copy local DBs, client resources or raw native exports into Git.

Rollback: revert only the new P04C implementation commit recorded in the
receipt, or leave this branch unmerged. The separate P04B and P09C dependency
commits remain intact. There is no client installation or live-state rollback.

One next step: integrate this checked reservation/consumer boundary with the
existing authoritative runtime admission under the P09D/P03M ownership
coordination, then perform actual native MS-1/IS-7 acceptance.
