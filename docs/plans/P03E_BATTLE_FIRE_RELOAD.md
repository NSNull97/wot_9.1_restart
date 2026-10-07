# P03E: native MS-1 fire, ammo consumption and reload callback

Дата: 2026-10-07, Asia/Yekaterinburg.

## Цель карточки

Добавить минимальный серверный срез для уже принятой native battle-сессии MS-1:
распознать авторизованный `Avatar.BaseMethods.vehicle_shoot` (`0x88`, ноль
аргументов), принять решение только по серверному боекомплекту, списать один
AP и отправить штатные `Avatar.updateVehicleAmmo` (`0x44`),
`Avatar.updateVehicleGunReloadTime` (`0x46`) и начальную установку
`Avatar.updateVehicleSetting(CURRENT_SHELLS, 2570)` (`0x40`) callbacks. Для
single-shot орудия МС-1 используется 2.5 секунды из проверенного статического
каталога `0.9.1 #717`, построенного с baseline-проверкой исходного Packed XML.

`vehicle_replenishAmmo` (`0x89`, ноль аргументов) распознаётся отдельной
командой, но бесплатное пополнение/экономика этой карточкой не включаются:
до подтверждения его runtime-семантики команда получает явный
`domain_applied=false` и не меняет состояние.

## Классификация данных

- **VERIFIED_STATIC:** `BaseMethods.vehicle_shoot` — native id 136 (`0x88`),
  ноль аргументов; `BaseMethods.vehicle_replenishAmmo` — 137 (`0x89`), ноль
  аргументов; `PlayerAvatar.shoot` вызывает `base.vehicle_shoot()` после
  локальных проверок; `PlayerAvatar.replenishAmmo` вызывает
  `base.vehicle_replenishAmmo()`; callbacks `updateVehicleAmmo` (`0x44`,
  `INT32, UINT16, UINT8, INT16`), `updateVehicleGunReloadTime` (`0x46`,
  `OBJECT_ID, FLOAT32, FLOAT32`) and `updateVehicleSetting` (`0x40`,
  `UINT8, INT32`), where `CURRENT_SHELLS=0`.
- **VERIFIED_STATIC:** входной Avatar method stream в принятой native сессии
  использует `[method:u8, length:u16 LE, args]`; exact zero-argument формы
  `0x86` уже проходят этот же boundary в readiness compound.
- **VERIFIED_STATIC:** проверенный каталог #717 извлекает для MS-1 /
  `T-18_Standart` / `_37mm_Gochkins` `reloadTime=2.5`, `magazine=null`.
- **OBSERVED:** owner HUD уже рисует три ammo rows (20/0/0) после P03D.
- **UNKNOWN:** native owner receipt именно `vehicle_shoot`, фактический ACK /
  callback ordering, projectile/hit/damage/physics semantics, and actual
  runtime use of `vehicle_replenishAmmo`.
- **NOT_RUN:** ручной выстрел/reload/consumption на клиенте до этой карточки.

## Шаги

1. Добавить bounded `battle/fire.rs`: exact parser for only `0x88/0x89`,
   server-owned MS-1 state, monotonic 2.5 s cooldown, and fixed native callback
   encoders. No client coordinates, clocks, shell IDs or counts are accepted.
   Append the fixed `0x40/CURRENT_SHELLS/2570` callback after the three ammo
   rows so the verified client has a current shell index before `shoot`.
2. Wire the state into both accepted battle routes (`arena_ready` and the
   owner-tested `map_drive` avatar route). Preserve clone/commit atomicity:
   malformed input, cooldown rejection, wrong phase, queue full and encoder
   errors do not mutate ammo, reload or transport state.
3. Keep `0x89` observable but unsupported until runtime semantics are captured;
   do not create ammunition, credits, equipment, projectile, hit or damage
   state. Add unit/Session contract tests for valid shot, no-ammo, cooldown,
   malformed/split/unknown methods, callback bytes and atomic rollback.
4. Build the isolated gateway, run the full Rust suite and layout check, create
   a static-method receipt and owner handoff. Stop before the manual shot; the
   owner must press fire once and capture the resulting HUD/wire behavior.

## Границы

- One authenticated local MS-1 session; one selected AP shell; no second player.
- No projectile trajectory, hit test, damage, visibility, physics, economy,
  equipment or persistence.
- No client patch, original-client mutation, live/deployed gateway restart or
  external server connection.
- `vehicle_replenishAmmo` remains explicitly unsupported at the domain layer.

## Приёмка

`PASS_ISOLATED_NATIVE_FIRE_ROUTE_READY` означает: canonical/legacy isolated
builds pass, full Rust tests and layout pass, exact bounded fire parser,
server-owned ammo/reload state and the initial current-shell callback pass
contract tests, and no deployed process or client changed. Native owner
fire/reload remains `NOT_RUN` until the handoff.

## Откат

Revert only the new `battle/fire.rs`, `main.rs` module declaration, Session
wiring and this plan/receipt; delete only the new isolated build/evidence
catalog. Keep deployed gateway, supervisor, client copies, database and prior
P03D frozen captures untouched.

## Единственный следующий шаг

Запустить owner handoff на том же MS-1 battle route и нажать один обычный
выстрел, затем проверить фактический native callback, уменьшение AP и reload
HUD по capture/screenshot.


## Выполнение 2026-10-07

- Canonical isolated: `python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-battle-fire-reload-07` — **328 tests PASS**, EXE SHA256 `72dfc02beef4b3af645a98914634463d84a21abb6274a897eac6ba5d47e32ff`.
- Shared legacy: `python -B -X utf8 server/build.py gateway --legacy --test --out local/build/server/gateway-battle-fire-reload-legacy-02` — **327 tests PASS**, EXE SHA256 `e1c05aed270e79d4a8ff25510619e0abd288f5e1718bf4fda68da189cbe9d127`.
- Layout: `python -B -X utf8 server/check_layout.py` — `PASS_SERVER_SOURCE_LAYOUT`, 52 source files, 22 single-source relocations.
- Deployed hash до/после изолированных действий: `daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`, замены нет.
- Static/source receipt: `local/evidence/20261007-battle-fire-reload-01/result.json`; owner handoff: `local/evidence/20261007-battle-fire-reload-01/owner-test/handoff.json`.
- Owner native fire/reload: **NOT_RUN** до ручного шага.

## Follow-up: reload latch correction 2026-10-07

Первый owner-прогон build07 был сохранён как отрицательное доказательство,
а не как успешный fire receipt. Владелец увидел «орудие перезаряжается»,
таймер `0,00`, AP не расходился. Capture имеет PASS для RSA/Blowfish и
bounded transport, но не имеет client→server `vehicle_shoot=0x88` и не имеет
`BATTLE_SHOT_ACCEPTED`/`BATTLE_SHOT_REJECTED`. Initial body был `162` байта:
три ammo rows и `CURRENT_SHELLS`, без initial reload callback.

Static `client__Avatar.json` подтверждает механизм: `shoot()` прекращается
до `base.vehicle_shoot()`, пока `aim.isGunReload()` истинно; только
`updateVehicleGunReloadTime(vehicleID,timeLeft,baseTime)` сбрасывает эту
защёлку. Поэтому добавлен bounded callback `13 46` с vehicle entity
`0x09100003`, `timeLeft=0.0`, `baseTime=2.5`. Новые размеры — PREBATTLE
`105`, map-drive binding `176`; callback располагается после panel rows и
selected-shell setting.

Повторные isolated проверки:

- `python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-battle-fire-reload-08` — **329 tests PASS**, EXE SHA256 `b70c73af9cc0060343e51202bf959326d0a584ce37b20a29ad3b4fe253085727`.
- `python -B -X utf8 server/build.py gateway --legacy --test --out local/build/server/gateway-battle-fire-reload-legacy-03` — **328 tests PASS**, EXE SHA256 `034277a63a55340f21e6604081dfef51d35258e1431307648b992663f5b4fafd`.
- `python -B -X utf8 server/check_layout.py` — **PASS_SERVER_SOURCE_LAYOUT**, 52 source files, 22 single-source relocations.

Deployed gateway SHA256 до/после остаётся
`daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`.
`owner-attempt-01-observation.json` фиксирует первый ручной симптом и его
capture; он не является owner fire acceptance. Следующий единственный шаг —
запустить build08, сделать ровно один MS-1 выстрел, подождать около четырёх
секунд и проверить фактический расход AP, callback и HUD reload.

## Owner acceptance: reload completion 2026-10-07

После completion callback собран build09 и выполнен один owner session на
исследовательской копии клиента #717. Владелец сделал пять выстрелов; gateway
зафиксировал `BATTLE_SHOT_ACCEPTED` с AP `19,18,17,16,15` и ровно пять
`BATTLE_RELOAD_COMPLETE` событий с `time_left=0.0`, `base_time=2.5`. Это
подтверждает native fire/reload/consumption в пределах карточки:

- canonical `gateway-battle-fire-reload-09`: **330 tests PASS**, SHA256 `460d5d68dd47b6599085d2775c316d4e1192a2d53c45f87aaabf86d9341e7970`;
- shared legacy `gateway-battle-fire-reload-legacy-04`: **329 tests PASS**, SHA256 `558a6b72a65e980395e146a48570e1ef1cec2b7accfcbe2c1cdb2a8e832e114a`;
- layout: `PASS_SERVER_SOURCE_LAYOUT`, 52 source files, 22 relocations;
- owner capture: `local/evidence/20261007-battle-fire-reload-01/owner-test/owner-capture-fire-reload-03`, 671 packet files, 667 channel frames, no bounded parse errors;
- owner receipt: `local/evidence/20261007-battle-fire-reload-01/owner-test/owner-acceptance-fire-reload-03.json`.

`projectile`, `hit`, `damage`, `physics`, visibility, equipment, economy и
persistence остаются вне карточки и **NOT_RUN**. Единственный следующий шаг —
новая отдельная projectile/hit/damage карточка.
