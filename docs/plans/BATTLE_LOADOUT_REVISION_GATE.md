# Plan: isolated battle-loadout ownership adapter

## Цель

Связать game.account.v1 ownership assertion с существующим Rust domain-only
loadout gate для принятого profile4-r4. Адаптер должен проверять account,
exact profile bytes SHA256, версии 4/4, crew, inventory, capacity/mounts из
закреплённого native ammo export и ammo mapping перед loadout::validate.

## Шаги

1. Зафиксировать baseline исходного isolated gate, ownership contract,
   semantic evidence и неизменяемых gateway/arena/physics sources.
2. Добавить отдельный Rust adapter с bounded input sizes, exact ownership
   envelope schema, версионированной pinned test_lab policy и bound result.
3. Собрать isolated harness на закреплённых Rust dependencies и вызвать
   реальный существующий gate на bundle-rooted данных + assertion,
   сформированном настоящим createOwnershipAssertion из exact profile bytes.
4. Проверить PASS и отказы stale/foreign/malformed/rehashed profile,
   source mismatch, wrong selection и byte bounds. Проверить identity suites.
5. Сохранить receipt и rollback snapshots; обновить STATUS/research.

## Границы

- Gate является pure domain adapter; ordinary gateway main/session, transport,
  arena/physics, native capture/client/backend/SQLite не менять и не запускать.
- Assertion принимается только на trusted service boundary; JSON shape и SHA
  не являются криптографическим доказательством сетевой аутентификации.
- Capacity берётся из pinned native ammo export MS-1, не из client input или
  общего gun default. Absolute provenance strings не обходятся.
- Никакого fire/reload/ammo consumption/reservation/battle admission.
- Исходный loadout.rs сохраняется byte-identical.

## Приёмка

PASS_BOUND_PROFILE4_LOADOUT_ADAPTER: accepted profile4-r4 -> typed bound
BattleLoadout через существующий Rust gate; все отрицательные inputs rejected,
live/native admission NOT_RUN. Адаптер остаётся isolated до отдельного wiring.
