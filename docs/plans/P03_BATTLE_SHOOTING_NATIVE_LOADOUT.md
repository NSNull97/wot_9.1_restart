# P03: native Avatar ammo loadout candidate

Дата: 2026-10-06. Статус до выполнения: **NOT_READY_NATIVE_LOADOUT**.

## Цель

Собрать изолированный серверный маршрут для одного доказанного MS-1 loadout:
native `Avatar.updateVehicleAmmo` должен быть закодирован как entity-method
`0x13, 0x44` с четырьмя фиксированными аргументами. Маршрут должен исходить
только из уже проверенного server-owned `BattlePreparation`. В ordinary map-drive
маршруте кандидат добавляется после измеренного 122-байтового ready/binding body
после own-vehicle creation ACK; итог — 133 байта в одной reliable записи. В
legacy PREBATTLE probe сохранён отдельный путь 51 + 11 = 62 байта. Live supervisor,
deployed gateway, original client и сохранённые native captures не меняются.

## Доказательства и границы

- **VERIFIED_STATIC:** original #717 `avatar.def` registration table maps
  `Avatar.updateVehicleAmmo` to message id `68 (0x44)`, argument types
  `INT32, UINT16, UINT8, INT16`, fixed size 9 bytes. Entity selection prefix
  `0x13` is already used by the checked `updateOwnVehiclePosition` codec.
- **VERIFIED_NATIVE_HANGAR:** closed MS-1 ammo trace reports compact shell
  `2570`, total/default count `20`, max ammo `96`, and shell rows
  `2570:20, 2826:0, 3082:0`.
- **VERIFIED_OFFLINE_TRANSPORT:** the frozen 345-packet `map-drive-phase2-v1`
  capture decrypts with the local RSA/Blowfish evidence key and all 341
  post-handoff channel packets pass the bounded transport parser. The exact
  candidate body and `0x13 0x44` prefix are absent; this proves the old capture
  has no ammo candidate, not that a new candidate is accepted by the client.
- **OBSERVED_STATIC:** `PlayerAvatar.updateVehicleAmmo` forwards
  `(compactDescr, quantity, quantityInClip, timeRemaining)` into the native
  consumables processor and stores the same tuple in `__ammo`.
- **INFERRED_CANDIDATE:** for the single-shot MS-1 preparation the candidate
  tuple is `(2570, 20, 0, 0)`. The value/order of `quantityInClip` and
  `timeRemaining` has not been observed in a live Avatar battle callback.
- **UNKNOWN:** whether the chosen order after the ready/binding body is accepted,
  whether the client accepts the fixed entity-method framing in this phase, and
  whether the selected tuple renders the in-battle HUD.

## Implementation rules

1. Add a typed, bounded codec with exact constants and no generic object or
   caller-supplied bytes.
2. Derive the candidate only from the authenticated MS-1 `BattlePreparation`;
   reject all other gun/shell/count/capacity combinations.
3. Queue the native candidate and existing preparation body atomically in the
   isolated gateway. Log `native_delivery_candidate=true` and
   `native_receipt=NOT_RUN`; do not call this native compatibility acceptance.
4. Add unit tests for exact bytes, all bounds, and queue ordering/rollback.
5. Build a fresh executable under `local/build/server/` without touching the
   live service. Record hashes and test output in a fresh evidence directory.

## Acceptance for this card

Offline source/tests/build/evidence may be **PASS**. Native client receipt,
correct battle HUD values, and actual method/order compatibility remain
**NOT_RUN** until one owner-driven MS-1 entry with capture. The owner test must
not fire, move, or enter sniper; it only checks entry, ammo HUD, and normal
return.

Current result: **PASS_OFFLINE_OWNER_ROUTE_FIX**. The first owner capture
verified the old route miss (122-byte binding, no ammo candidate), and the
corrected isolated EXE `gateway-battle-shooting-native-loadout-07` passed 318
Rust tests and a separate bind smoke. The post-fix owner handoff is
`local/evidence/20261006-battle-shooting-native-loadout-01/owner-test-build07.md`.
The offline transport audit is
`local/evidence/20261006-battle-progress-loadout-capture-01/offline-transport-audit.json`.
Native battle receipt, HUD, and wire-order acceptance after build07 remain
**NOT_RUN**.

## Owner run review and route correction

The first owner run against build06 is now **VERIFIED_OWNER_CAPTURE_ROUTE_MISS**,
not a native HUD rejection. The capture contains a valid `READY_COMPOUND` at
packet 74 and a following server→client binding of exactly 122 bytes at packet
76. Its bounded Login/BaseApp/channel audit passes for 658 packets, but no
`0x13 0x44` prefix or exact ammo candidate appears. The client trace records an
MS-1 hangar with `2570:20`, reaches `BattleLoading` and `onSpaceLoaded`, and
closes cleanly; its ammo callbacks are hangar callbacks before battle and do not
prove a battle HUD value. The owner observed “БК нет”. Evidence is kept in
`owner-test/owner-capture-audit-060.json`,
`owner-test/owner-wire-frame-summary-060.json`, and
`owner-test/owner-trace-audit-060.json`.

The cause was the dispatch order in `drive_avatar`: live map-drive sessions
enter that branch before the later `queue_map_binding` branch, so build06 sent
the old 122-byte binding. Plan `P03C_OWNER_WIRE_AMMO_ROUTE_FIX.md` records the
bounded repair. Build07 appends the same typed 11-byte candidate inside
`drive_avatar`, keeps the 122-byte prefix and reliable retry semantics, and has
an explicit focused test for this real route. Build07 passes 318 Rust tests,
source-layout check, and an isolated map-drive bind smoke on `20124/20126`.

The next owner handoff is
`local/evidence/20261006-battle-shooting-native-loadout-01/owner-test-build07.md`
with a fresh `owner-capture-070`. Native client receipt, order acceptance, and
HUD rendering remain **NOT_RUN_AFTER_BUILD07** until that one repeat entry.

## Owner handoff prepared

### Review correction before owner handoff

The first handoff is **REJECTED_BEFORE_RUN**: `legacy091-interactive` never
initializes the ordinary map-drive session, and its smoke has already consumed
the proposed capture directory. The codec had only been wired to the legacy
PREBATTLE probe, so ordinary `drive_avatar` could not send it. No owner test was
requested or started against that recipe.

Correction plan (same card):

1. Preserve the first receipt/handoff/source as rejected evidence.
2. Append the bounded ammo candidate atomically to the ordinary 122-byte
   ready/binding body only after the native own-vehicle creation ACK. Validate
   the same generation-bound server-owned preparation; preserve retransmission
   and duplicate handling. The candidate order is still INFERRED.
3. Add focused tests for ordinary ready delivery, retry/duplicate behaviour,
   and fail-closed rollback; rebuild the isolated executable.
4. Prepare a fresh client install with `enable_map_drive=true`, a separate
   pool descriptor with hash-verified read-only worker/map inputs, and distinct
   empty native and smoke capture directories. Use `legacy091-map-drive`.
5. Smoke the corrected executable/config/pool, then verify the actual installed
   client hashes, reachable route, empty native capture and exact command.

The old `client-install-018` and its smoke capture remain historical evidence.
The corrected `client-install-020` is installed with `enable_map_drive=true`.
The first owner run used build06 and is preserved in `owner-capture-060`;
its smoke wrote only to `smoke-capture-060`. The build07 follow-up uses the same
hash-pinned `map-drive-pool-060.json` and fresh `owner-capture-070`; its bind
smoke is `map-drive-smoke-071.json` on `20124/20126`. No post-fix native client
process has been started.

The isolated executable and the fresh research-copy install are prepared under
`local/evidence/20261006-battle-shooting-native-loadout-01/owner-test-build07.md`.
That handoff keeps the existing service running only for the identity bridge,
uses gateway ports `20114/20116`, and limits the manual run to one MS-1 entry,
ammo-HUD observation, and normal close. The owner must not fire, move, enter
sniper, change shells, or start a second client.

## Rollback

Revert the files listed in the evidence receipt and delete the isolated build.
For the prepared research copy, run the recorded rollback command against
`local/evidence/20261006-battle-shooting-native-loadout-01/client-install-020`
if the owner test is cancelled. Do not touch the original client, deployed
gateway, or supervisor.
