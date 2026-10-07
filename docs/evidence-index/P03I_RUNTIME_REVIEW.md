# P03I runtime review evidence index

Status: **PASS_STATIC_RUNTIME_REVIEW / NATIVE_PROFILE_HANDOFF_NOT_RUN**.

This index records evidence inspected for the read-only review of runtime
commits `4b66ce3` and `cae2c3b`. It deliberately excludes their runtime and
client changes from `main`; it is not an acceptance record for those commits.

## Receipts

| Receipt | Result | What it proves | What it does not prove |
|---|---|---|---|
| `local/evidence/20261007-p03i-vehicle-profile-loadout-01/native-profile-04/native-catalog-01.json` | `PASS_NATIVE_MOUNTED_VEHICLE_CATALOG` | Two native mounted catalogues agree on the MS-1/IS-7 descriptors and pure catalogue/aim samples | Crew assignment, owned loadout, queue or battle admission (`crew_assignment_verified=false`, `inventory_loadout_verified=false`) |
| `local/evidence/20261007-p03i-vehicle-profile-loadout-01/native-profile-05/profile-binding-06.json` | `PASS_AUTHENTICATED_PROFILE_BINDING` | Two authenticated sessions bind distinct profile sources; both are MS-1, with AP `2570`, ammo `20`, crew `2/2`, no garage mutation | Selected IS-7 handoff, native queue, impact or damage |
| `local/evidence/20261007-p03i-vehicle-profile-loadout-01/native-profile-05/capture-audit-profile06.json` | `PASS_CRYPTO_TRANSPORT` | Receipt prefix has 3,746 packets, 3,738 channel frames, 2 logins, 4 vehicle creations, 1,153 poses and zero audit errors | Correct native application semantics, CMD700, callback or selection-to-battle |
| `local/evidence/20261007-p03i-vehicle-profile-loadout-01/native-profile-05/launch-server-06.json` | `SERVER_STARTED_NOT_ACCEPTED` | Isolated gateway process and receipt-matched capture command were started | Native acceptance; `native_acceptance=NOT_RUN` |
| `local/evidence/20261007-p03i-vehicle-profile-loadout-01/native-profile-05/launch-a-06.json` and `launch-b-06.json` | `NATIVE_CLIENT_STARTED_NOT_ACCEPTED` | Two isolated client processes started with separate profiles | Manual queue click, callback or battle acceptance; both mark `native_acceptance=NOT_RUN` |
| `local/evidence/20261007-p03i-vehicle-profile-loadout-01/native-selection-07/selection-07.json` | `PASS_NATIVE_GARAGE_SELECTION_MODEL_OBSERVED` | Existing observer saw inventory `1 → 2` and an IS-7 hangar model | Manual gesture provenance is `UNKNOWN`; `battle_handoff=NOT_RUN`; crew is false and ammo is zero |
| `local/build/server/gateway-p03i-profile-06/result.json` | `PASS_ISOLATED_BUILD` | Canonical profile06 gateway build: 381 Rust tests, executable SHA `81f5643e64898892d9dbf44b60a9f982d92ea104ea1589850f21c6a7dfcdee6e`; deployed gateway not replaced | Native compatibility or owner acceptance |
| `local/build/server/gateway-p03i-profile-legacy-04/result.json` | `PASS_ISOLATED_BUILD` | Legacy gateway build: 379 Rust tests, executable SHA `5d9a5dea9e540580b92d1da67f642f836508276d37dc3822c17e972398a91188`; deployed gateway not replaced | Native compatibility or owner acceptance |
| `local/evidence/20261007-p03i-vehicle-profile-loadout-01/layout-profile-03.json` | `PASS_SERVER_SOURCE_LAYOUT` | 59 server files, 22 single-source relocation checks; remote/Linux readiness remains `NOT_RUN` | Runtime behavior or native protocol |

The profile06 transport manifest prefix SHA is
`826d68035863d739e104d2d50012fa04a86821968bfa55900ebc7528a35bf2a6`.
The profile06 canonical executable SHA is the one recorded in its build
receipt above; neither executable replaced the deployed gateway.

## Reviewed runtime surface

| File | Review result | Boundary |
|---|---|---|
| `server/gateway/src/battle/profile.rs` | Typed MS-1/IS-7 profile and fail-closed crew/ammo validation | Static fields are not a native ownership or queue resolver |
| `server/gateway/src/battle/preparation.rs` | Hash-pinned primary projection and explicit secondary MS-1 lab grant | No general selected-vehicle admission; IS-7 grant absent |
| `server/gateway/src/battle/fire.rs` | Integer reload/profile seam and generic callback helpers | Native callback path remains the old MS-1 wrapper; live generic callback NOT_RUN |
| `server/gateway/src/shared/model.rs` | Profile reaches actor/fire/projectile state; rejoin keeps profile/ammo | Synthetic IS-7 test is domain-only; storage/legacy bound needs review |
| `server/gateway/src/shared/projectile.rs` | Selected shell speed/gravity/range reach bounded tracer | Tracer lifecycle is not hit/damage or native solver proof |
| `server/gateway/src/shared/wire.rs` | Descriptor/health/shell/reload encoders accept profile values | Aim/rate values remain fixed MS-1 constants |
| `server/gateway/src/shared/server.rs` and `shared/mod.rs` | Authenticated profile source and generic HUD/reload logging | Only MS-1 sources are admitted in production path |
| `client_patch/sr_interactive.py` | Bounded read-only native catalogue observer | No garage mutation, crew/ammo assignment, queue call or battle handoff |

## Exact next gate

Run one ordinary native MS-1 random-battle click with a receipt-matched
process manifest and preserve the decrypted Account body: both leading
`INT16` values, request `202`, command `700`, selected vehicle `INT64`, both
`INT32` gameplay/arena values, and either the success callback plus queue event
or the failure callback with its arguments and event. Correlate the selected
inventory ID with the authenticated server session and prove no fixture or
database mutation. Treat missing body fields or callbacks as `NOT_RUN`.

Do not repeat for IS-7 until an explicit hash-pinned assigned crew and
server-owned shell stack exists. Until that gate passes, no runtime profile
merge, CMD700 decoder, equipment modifier, hit solver or damage path should be
claimed.

## Checks and rollback

This card adds documentation only. Applicable checks are Markdown link/readability
inspection and `git diff --check`; no server, client, deployed artifact,
fixture, database or physics process is started. Rollback is a single commit
revert.
