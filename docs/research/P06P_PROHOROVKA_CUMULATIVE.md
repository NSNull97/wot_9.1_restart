# P06P — Prohorovka cumulative map migration

## Goal and state

Owner requested replacing the test map with Prohorovka while continuing map
object work. This card migrates the accepted P06O cumulative native battle:
movement, grounded suspension, aim/RMB, ammunition/reload, world/live/wreck
contacts and effects, and catalog-based fragile removal. Trees follow as a
separate card after this prerequisite. Base main:878ade656906918f2aa9c095621feb4f504be603.
Branch:codex/p06p-prohorovka-cumulative. Acceptance:IN_PROGRESS, native NOT_RUN.

## Evidence and knowledge categories

Evidence root: `local/evidence/20261012-p06p-prohorovka-01/`.

VERIFIED: original #717 arena list assigns asset05_prohorovka arena type4,
not5. Native arena INT32 and space asset are now derived from one MapId.
Arena XML SHA7a3898a15922ff6b350e0ba91fe5ceab53b916ad1bcfdf1a198002f9d33e863d.

VERIFIED: fresh projectile mask128 export (not driving mask18) has3904
instances,285350 triangles; source709793=kept285350+excluded424443,
degenerate0. Manifest SHA3db1ad3859ae2f5fed678ac5f148005cff38a3c915bb33dde3303de22e22bef7.
Physics mesh428597 triangles; terrain769x769,144 chunks without holes.
Exact source/buffer pins are centralized in drive/map_profile.rs; readers
verify size/SHA before decoding and reject mixed maps. Original resources
are read-only; their package/member pins precede inventory XML decoding.

VERIFIED: full inventory finds712 fragiles,2943 trees,71 falling atoms,
58 structures and120 undefined objects. Nine whole fragile colliders meet
the accepted rule: sixenv014_Toilet and one eachmle019_GerBoxes1/2/3.
703 exclusions have explicit reasons. MAX_OBJECTS64/removed40 unchanged.
Native preprocessing must still read all44 fragile-containing chunks before
joining the nine eligible objects; no partial output or ordinal guess.
Importer verification preserves the accepted Karelia inventory byte-for-byte.

OBSERVED: private physics25/25 on original configurations verifies both maps,
two Prohorovka lane poses/contact/travel, emptyIPC3 equality withIPC1,
cumulative removal/retry/restore and malformed map/hash/generation rejection.
This does not prove rendered native passage. Exact root DLL run is pending.

UNKNOWN: owner-visible Prohorovka movement/rendering/FX and eligible-object
passage are not yet tested. Historical penetration/damage and full object
coverage are not claimed; existing test_lab approximations remain explicit.
Tree flags from12 pinned BSP resources all have bit128, so the native
projectile mask excludes those faces. Tree fall/collision needs a separate
original contract; do not silently add trees to the static projectile subset.

## Changes and commands

Changed: map_profile.rs; main/session/shared runtime/wire/terrain/obstacles/
impact/model/fragile admission; physics catalog verification; original native
catalog probe; importer and focused tests. No vehicle physics coefficients
are changed. Source-derived test spawn may change only origin/yaw.

Canonical builds (fresh ignored output):

```powershell
python -B -X utf8 server/build.py physics --out local/build/server/physics-integrated-p06p-01
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-integrated-world-p06p-01
python -B -X utf8 tools/destructible_catalog.py --map 05_prohorovka --out local/evidence/20261012-p06p-prohorovka-01/import/catalog-inventory01
```

First physics command and importer command completed; gateway command is planned,
not yet a PASS. Importer20 tests and native probe14 tests PASS in isolated
worktrees; root integrated suite remains pending. Exact commands/receipts are
retained under import/,native-contract/ and boundary/.

## Rollback and next gate

P06O gateway05/physics01/pool-near/catalog remain intact. Stop only receipt-
verified own processes, restore installed diagnostic ledgers, and restart the
accepted P06O Karelia configuration. Revert the P06P branch changes if needed.
No merge/push while any required native gate is FAIL/NOT_RUN.

One next gate: complete canonical integration checks, then launch the approved
native copies with the full Prohorovka runtime and collect the original IDs.
