# P04D — one native MS-1 recruitment

The owner selected recruitment as the next card. Scope is one actual original
#717 combined recruit-and-equip operation, a server-owned new identity and
assignment, and persistence across genuine fresh login. Skills, dismissal,
retraining, paid tariffs, equipment operations and combat admission are outside
this card. Branch: `codex/p04d-native-crew-recruitment`.

## Source facts and explicit project policy

**VERIFIED_STATIC:** pinned original `Shop.buyTankmanAndEquip` uses CMD309 with
`doCmdInt4(requestID,309,shopRevision,vehicleInventoryID,slot,costIdx)`.
The fixed argument payload is 24 bytes: `<hhqiii>`. CMD303 is separate purchase
and CMD105 is separate assignment; their callback contracts must not be
substituted for CMD309. Combined309's original processor ignores callback ext;
an empty literal dictionary is sufficient on the measured source path.

**VERIFIED_STATIC:** the original processor permits an occupied seat, checking
barracks capacity when replacing. Server state must preserve the previous
tankman's descriptor and move its ownership to -1. Native tankman category8
contains `compDescr` and `vehicle`, and category1 contains vehicle crew arrays.
The dossier is embedded in the tankman descriptor. Inventory identity is not
embedded in that descriptor.

**VERIFIED_STATIC:** tariff0 returns zero credits and zero gold after indexing
`tankmanCost[0]`. `StatsRequesterr.freeTankmenLeft` reads `freeTMenLeft`. The
original window nevertheless unconditionally reads paid rows1/2. Their prices
and historical tariff-to-training mapping are **UNKNOWN**.

**PROJECT_POLICY:** `p04d-native-crew.v1`, one free 100% MS-1 driver, slot1,
no skills, fixed verified test passport, 16 inventory/barracks bound, no battle.
Policy SHA256 `7d0e3d7ef28d85bfe32e4fcdea0547696a9b4fd04922a725a2d895e1395f0d55`.
The label explicitly describes a test policy, not historical starting economy.
Paid buttons are hidden/disabled and their tariff readers are guarded.

**OBSERVED_NATIVE_717:** the independently decrypted actual client request
uses `doCmdInt4` wire0x90 and VAR2 length24: `90 18 00` followed by
`<hhqiii> = (226,309,3,1,1,0)`. This was initially only inferred from the
stable inherited method table. Native capture `wire01`, session3, packet156
now establishes the measured index/framing for this build and operation.
The gateway remains reachable only with explicit crew-service opt-in.

## One authoritative writer

The dependency is P09D `db72382652ec18a475b3cf85a024dc78a7e13fe7`, locally
cherry-picked as `b13ca5c`. `NativeCrewStore` extends that existing ammo store;
both native HTTP routes use this same implementation and game.sqlite.
There is no independently writable crew JSON or second inventory database.

Migration retains native IDs1/2, adds free quota1 and configuration revision1,
and publishes profile6/aggregate revision6. CMD309 moves ID2 to barracks,
allocates ID3, assigns crew `[1,3]`, consumes quota and increments both aggregate
and configuration revisions in one `BEGIN IMMEDIATE` transaction. The shared
command ledger and response hash prevent duplicate application. Authenticated
owner, native database ID, expected revision, seat, tariff, quota, reservation
and pinned descriptor are checked before writes. Unsupported choices reject.

The projection combines mutable crew with current ammunition/depot. Neither
operation can restore the immutable baseline over the other's changes.
The legacy writer fails closed after crew migration. Files are immutable
derived caches, regenerated from a consistent same-DB view. A crew source is
required for publication; shop and state output hashes describe actual bytes.

Gateway scheduling shares the existing ammo queue, account revision and single
in-flight job. It dispatches external work only after a complete validated
packet/piggyback transaction. Retired-session work remains accounted for until
its bounded result resolves. The native update must precede its success reply.

## Actual native execution

Run03 used the original RecruitWindow and original decorated recruit callback,
with the explicitly enabled local diagnostic choosing the supported option.
There was no client-side inventory mutation and no synthetic request in place
of the native operation. The server accepted request226, created ID3, moved
ID2 to barracks and published aggregate revision7. Independent raw decoding
finds a158-byte Account.update in packet158/server sequence17, followed by
success0x4d in packet159/sequence18. The original client applied the update
before completing the matching callback and read crew `[1,3]` from its cache.

The gateway and bridge were stopped by receipt-verified PID/executable, then
fresh processes49940/52088 were started over the same authoritative database.
Run04 started a new original client process33176 using the preserved local
preferences. Its read-only snapshot exactly matches run03: IDs1/3 seated,
ID2 in barracks, quota0,100000credits,0gold, unchanged descriptor hashes.
Separate consistent SQLite backups were made after recruitment and relogin.
The fresh-login wire capture contains no second CMD309.

Three actual engine PNGs were inspected. The original recruitment window
shows the explicit `Тест: 100%, бесплатно` option; paid buttons are absent.
The subsequent hangar and fresh-login view show the complete MS-1 crew.
The native driver displays110% because of its commander bonus; its persisted
role level is100%. The fixed test passport duplicates the displaced driver's
name, so identity is established by wire/cache/DB evidence, not a portrait.
Colored background rendering artifacts remain observed and outside this
feature's acceptance. Physical pointer input/owner manual review is NOT_RUN;
the accepted scope is actual native callbacks, network and persistence.

Two earlier native attempts failed before any CMD309 or database mutation:
the original tankmen collection is an ItemsCollection dict subclass, and the
Flash window title does not exist at the first populate hook. The bounded
native reader and optional title access were corrected; failed traces remain
preserved. The successful source hashes match both final installation plans.

## Isolated execution and remaining gates

Read-only original: `C:\WoT_0.9.1_RU_0717_original`, canonical manifest
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
All outputs, own game/identity DBs, keys, credentials, builds and client copy
are below the managed crew worktree's ignored `local/`.
The client copy is `local/clients/p04d-b`, a manifested independent copy;
the primary checkout and the sibling P09D client/services are not changed.

The full native result, source bindings, exact commands, tests and rollback
are recorded in the [evidence index](../evidence-index/P04D_NATIVE_CREW_RECRUITMENT.md).
Both successful installations were restored by their ledgers, both original
client runs exited normally, and only this card's server processes were stopped.
The original and parallel primary/P09D copies were not modified.
The native recruitment/relogin gate passed. The evidence index separately
records full regression failures and the resulting main-integration hold;
native success does not waive another required gate.
