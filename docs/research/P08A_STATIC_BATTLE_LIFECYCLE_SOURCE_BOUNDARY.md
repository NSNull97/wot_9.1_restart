# P08A — static battle lifecycle source research

Дата: 2026-10-08. Статус: `PASS_STATIC_SOURCE_BOUNDARY_ONLY`.

## Method

Проверен только локальный P00/P01 evidence pack для World of Tanks 0.9.1
#717. Аудит сопоставил `summary/lifecycle-static.json` с entity declarations
из `summary/contracts.json`; оригинальная и research копии клиента не
запускались и не редактировались.

Inputs:

- `local/evidence/20261002-p00-p01/summary/lifecycle-static.json`, 17049
  bytes, SHA-256 `f4b8e847513258fff543f46b3efa5c41d3b191df91863a30e04a54fd8220fbcf`;
- `local/evidence/20261002-p00-p01/summary/contracts.json`, 156154 bytes,
  SHA-256 `c9bd0893dfdb1ec6c09de9af200b04eb19b6dd08f71b97f40b32bb831a70a6e5`;
- `local/evidence/20261002-p00-p01/summary/resource-facts.json`, 9712 bytes,
  SHA-256 `817a9c01dd7b367c8d2b54be517f44c08720b3a508bddca0d8f0436f069c5d71`;
- `local/evidence/20261002-p00-p01/summary/sources.json`, 3268 bytes,
  SHA-256 `67a4d82108d821a3a39614ba9b3a278cbf8330b4329d6c6e5e9b5cc8ef53eb9a`.

## Result

Bounded verifier `tools/p08a_lifecycle_static_audit.py` повторно проверяет
четыре входа по exact SHA-256/размеру: lifecycle `f4b8e847…20fbcf`, contracts
`c9bd0893…a70a6e5`, resource-facts `817a9c01…9c5d71` и sources
`67a4d821…f53eb9a`. Он фиксирует 3 Account, 11 Avatar и 4 Vehicle source
records, а Arena берёт из typed entity definitions. Проверены bounded path,
duplicate/non-finite/depth/item guards и negative mutations; targeted suite
**8/8 PASS**. Игнорируемый receipt и hashes: `local/evidence/20261008-p08a-static-audit-01/`.

`lifecycle-static.json` contains these class/method groups:

- Account: `PlayerAccount.onBecomePlayer`, `onBecomeNonPlayer`, `showGUI`;
- Avatar: `onBecomePlayer`, `onBecomeNonPlayer`, `onEnterWorld`,
  `onLeaveWorld`, `onSpaceLoaded`, `vehicle_onEnterWorld`,
  `vehicle_onLeaveWorld`, `updateArena`, `moveVehicleByCurrentKeys`,
  `moveVehicle`, `shoot`;
- Vehicle: `onEnterWorld`, `onLeaveWorld`, `set_health`, `onHealthChanged`;
- connection and replay helpers are present in the manifest but are outside
  this battle-lifecycle boundary.

The same manifest records static references in Avatar initialization and leave
paths to `ClientArena`, `arenaUniqueID`, `arenaTypeID`, `arenaBonusType`,
`arenaGuiType`, `arenaExtraData`, `onLeaveArena`, vehicle cleanup, projectile
cleanup and arena resource release. These are source observations only.

The `arena` entity contract in `contracts.json` contains lifecycle-facing
methods including `onVehicleCreated`, `onCreateVehicleFailure`,
`setAvatarReady`, `removeAvatar`, `sendArenaStateTo`, `stopByFailure` and
`reuse`, plus state/roster/geometry/gameplay properties. The contract marks
wire IDs as `UNKNOWN`; this research intentionally does not infer them.

## Classification

### VERIFIED_STATIC

- The named declarations and their source filenames/line numbers are present
  in the hash-pinned lifecycle manifest.
- The arena method/property names and argument type descriptions are present in
  the hash-pinned entity contract.
- The boundary separates account/avatar/arena/vehicle declaration surfaces;
  it does not collapse them into one guessed protocol.

### UNKNOWN

- Wire IDs, method ordering, flags, binary serializers, state machine numeric
  values and server callback semantics.
- Whether static cleanup references run on every leave, in what order, or after
  which native event.
- Which arena payloads produce the observed UI, timer, audio and remote-vehicle
  effects.

### NOT_RUN

- Successful native Account → Avatar → Arena → Vehicle transition.
- Native battle window, audio/FX, timer/countdown and ten-battle repeatability.
- Rejoin/leave/death/results and two-client lifecycle correlation.

## Non-claims

This card does not implement or change runtime code. It does not establish
server authority for position, health, ammo, crew or equipment, and it does not
claim native wire compatibility. Any future implementation must first attach a
raw, owner-captured lifecycle trace to this boundary.

## Reproduction

```powershell
Get-FileHash local/evidence/20261002-p00-p01/summary/lifecycle-static.json -Algorithm SHA256
Get-FileHash local/evidence/20261002-p00-p01/summary/contracts.json -Algorithm SHA256
Get-Content local/evidence/20261002-p00-p01/summary/lifecycle-static.json -Raw | ConvertFrom-Json
```

The commands inspect local receipts only. No client or service process is
started by this card.
