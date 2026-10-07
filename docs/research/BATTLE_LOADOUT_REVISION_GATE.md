# Исследование: battle-loadout revision adapter

Дата: 2026-10-06

## Цель и граница

Добавлен отдельный adapter `server/gateway/src/battle/profile4_adapter.rs`,
который связывает trusted `game.account.v1` ownership assertion с уже
существующим `battle/loadout.rs`. Он не является native packet encoder, не
выдаёт battle admission, не резервирует и не списывает боекомплект.

## VERIFIED inputs

- Профиль r4 из принятого bundle имеет exact SHA256
  `2610dbd9ee64a12852986def336da057326f14a3289dda43eaae616286998d2d`,
  revision `profile_version=4`, `snapshot_revision=4`.
- Compatibility blob exact SHA256
  `825a7e7024993c83b132499fe6f383b233ac288049bb77ca94b5407430f8d4d3`.
- Native MS-1 ammunition export exact SHA256
  `683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74`.
  Из него adapter принимает только version/kind `native-ms1-ammo`, MS-1
  inventory `1`, type `3329`, turret `5891`, gun `5892`, capacity `96` и
  совместимый AP shell `2570`.
- Profile ammo row — `shell:ms1-stock-ap`, count `20`, owned MS-1 inventory;
  crew — ровно commander + driver, оба назначены на этот inventory.
- Compatibility mapping сверяется с vehicle/shell IDs и exact native module IDs.

## Реализация

Adapter ограничивает ownership envelope 4096 байтами, profile/compatibility/
native source по 8192 байтам, проверяет exact envelope/data keys,
profile/compatibility/native SHA, account/nickname/creation/native DB binding,
revision 4/4, crew and ammunition invariants, затем строит typed
`AuthenticatedVehicleProfile` + `AmmoMapping` и вызывает прежний
`loadout::validate`. Возвращаемый `BoundBattleLoadout` связывает результат с
account, native DB, revisions, profile SHA, policy `test_lab.profile4-ms1.v1`
и crew count. В DTO нет credentials, session, paths, client coordinates или
wire bytes.

`battle/mod.rs` и compile-only module declaration в `main.rs` включают adapter в
canonical gateway test/build path, но ни один session/transport/arena/physics
handler его не вызывает. Existing `loadout.rs` byte content не менялся.

## Проверки

`server/build.py gateway --test` на свежем isolated output завершает canonical
Rust suite: 307 tests PASS, включая 5 adapter tests для accepted r4, stale
assertion, foreign selection, exact digest, malformed/oversize input и
compatibility/native hash pins. Сборка не заменяет deployed gateway; его
прежний SHA сохраняется в receipt. `server/check_layout.py` PASS, 49 source
files.

## UNKNOWN / NOT_RUN

- Native Avatar loadout/ammo event и wire compatibility — NOT_RUN.
- Session/main runtime wiring, battle reservation/admission, consumption,
  reload, fire, damage, physics, economy and persistence — NOT_RUN.
- Ownership JSON trusted-boundary authentication is not cryptographic signature;
  SHA is exact revision/integrity binding.
- Adapter policy is deliberately pinned to one local `test_lab` r4 closure;
  other vehicles/shells and future profile revisions are unsupported.

## Evidence

Plan: `docs/plans/BATTLE_LOADOUT_REVISION_GATE.md`.
Receipt and before/after hashes:
`local/evidence/20261006-battle-loadout-revision-gate/`.
Existing domain-only gate receipt:
`local/evidence/20261006-battle-progress-loadout-gate/result.json`.
