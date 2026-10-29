# INPUT-01 — неподдержанные методы Avatar не ломают канал

Ветка `codex/input-01-settings-methods` от `d0a9b9e` (main после POSTMORTEM-01).

## Находка (29.10, стенд -11 на BW-01 `29c0538`)

Лог `local/stands/full-test-20261027-11/gateway-20261029-145109.stdout.log`, строка 11172:
`SHARED_REJECT session=1 reason=channel_state sequence=Some(3031) bytes=78 … mod.rs:796:33` — ветка
`_ => return Err(bad())` разбора конверта (ID метода вне таблицы шлюза). Далее ~170 отказов
`unsupported session input` (номер `rx` не продвинулся, как в POSTMORTEM-01), `idle_timeout`, выброс.
В трассе клиента в это время `preferences_local_save` — владелец менял настройки в бою.

## Исследование

VERIFIED (байткод `res/scripts/client` клиента `local/clients/arena/d`, `.def` через `tools/packed_xml`):
- Смена настроек: `ServerSettingsManager.setSettings` → `g_settingsCache` → `IntUserSettings.addIntSettings`
  → `proxy._doCmdIntArr(CMD_ADD_INT_USER_SETTINGS=1600, [k,v,…])`; в бою прокси — `PlayerAvatar.__doCmd`
  → Base `doCmdIntArr(INT16 requestID, INT16 cmd, ARRAY<INT32>)`.
- Вкладка «Прицел» (уточнение владельца): `ServerSettingsManager.setAimSettings` → `_buildAimSettings`
  (только изменённые секции `AIM_<ARCADE|SNIPER>_<1..3>`) → `g_settingsCache.setSettings` →
  `PlayerAvatar.intUserSettings` (свой прокси Avatar, `Avatar._doCmdIntArr` 3483) → тот же
  `doCmdIntArr(1600, [k,v,…])`; `setVersion` — отдельный вызов. ARRAY: счётчик u32 (как у Account 0x97).
  INFERRED: 73 байта = например 3 пары (35) + версия 1 пара (19) + `trackPointWithGun` (19); тест на этот размер.
- «Серверный прицел»: `VehicleGunRotator.showServerMarker` → `Avatar.enableServerAim` →
  Base `setDevelopmentFeature('server_marker', enable)`.
- Exposed методы Avatar: Cell — autoAim, moveTo, bindToVehicle, monitorVehicleDamagedDevices (targetFocus/Blur);
  Base — 31 (Chat: chatCommandFromClient, inviteCommand, ackCommand; Avatar: setClientReady, leaveArena,
  confirmBattleResultsReceiving, doCmd*, vehicle_*, requestToken, setClientCtx, setDevelopmentFeature …).
  Vehicle Cell exposed: moveWith, trackPointWithGun, stopTrackingWithGun, changeSetting, sendVisibilityDevelopmentInfo.

INFERRED (таблица ID): фиксированные по размеру по возрастанию (ничьи — порядок .def, Implements первыми),
затем переменные в порядке .def. Совпадает со всеми наблюдаемыми ID шлюза: Base 0x87 confirm, 0x88/0x89
shoot/replenish, 0x8a moveWith, 0x8d changeSetting, 0x8e/0x8f stopTracking/trackPoint, 0x99 leaveArena;
Cell 0x0c autoAim, 0x0d bindToVehicle, 0x0f Vehicle.trackPointWithGun. Отсюда doCmdIntArr = 0x9c,
setDevelopmentFeature = 0xa1, monitorVehicleDamagedDevices = 0x0e.

UNKNOWN: точное содержимое 78-байтного пакета (байты не логировались; 73 байта приложения не делятся
как один doCmdIntArr — в конверте были и другие записи). Ответ Avatar `onCmdResponse` не измерен.

## Изменение

- `wire::unimplemented_exposed`: ID exposed-методов Avatar/Vehicle, которые бой не реализует. Запись
  пропускается точно по её VAR2-длине с логом `SHARED_UNSUPPORTED method=… id=… detail` (для doCmd* —
  request/command, для setDevelopmentFeature — имя). Ответ не выдумывается; настройки клиент хранит
  локально (кэш обновлён до отправки), серверное хранение — вне карточки.
- ID вне таблицы: границу записи определить нельзя. Предварительный разбор (`unframed_record`, та же
  `record_size`, что у основного цикла) находит его до применения любой записи, и весь конверт отбрасывается
  (`SHARED_UNSUPPORTED_ENVELOPE … id offset bytes`): атомарно, как прежний отказ, но надёжный номер
  потребляется и ACK транспорта из аутентичного кадра применяется. Только в фазе Driving (и в слив-клоне
  Leaving/Returning, который идёт через Driving); до первого READY остаётся строгий отказ, чтобы испорченное
  рукопожатие не «съедалось» молча.
- Обрезанная запись (длина больше конверта) по-прежнему отказ (испорченный конверт).

Почему безопасно: конверт уже аутентифицирован токеном и ограничен (≤512 байт, ≤16 записей); из
пропущенных байтов ничего не попадает в домен; каждая применённая запись проходила те же проверки, что и
раньше; сервер остаётся авторитетным. Раньше единственным следствием отказа было зависание собственного
канала игрока до `idle_timeout`, то есть отказ не защищал ничего, кроме выброса самого игрока.

## Проверки

- `input01_unimplemented_avatar_methods_are_skipped_and_unknown_tail_keeps_channel_live`
- обновлены (неразбираемый байт больше не отказ канала, обрезанная запись — отказ):
  `real_channel_clone_rejects_late_poison_without_partial_input_or_ack`,
  `p08c_autoaim_bad_shape_route_and_late_valid_commands_roll_back_actual_ack`,
  `lifecycle_flow_account_reset_waits_for_original_avatar_result_confirmation`
- набор шлюза против `d0a9b9e` — см. Итог

## Итог

- Полный набор шлюза (worktree, temp target): ветка `65cd494` 1752 PASS / 94 FAIL / 13 ign, база `d0a9b9e`
  1750 / 94 / 13; списки FAIL совпадают. Логи `local/evidence-input01/` в worktree.
- Канонический gate, release, native (смена настроек в бою на стенде) — NOT_RUN.
- Проверка владельцем: в бою менять настройки (в т.ч. «серверный прицел»), в логе `SHARED_UNSUPPORTED
  method=doCmdIntArr … command=1600` / `method=setDevelopmentFeature feature=server_marker` или
  `SHARED_UNSUPPORTED_ENVELOPE`, нет `SHARED_REJECT … channel_state`, бой доигрывается.
- Не сделано: ответ `onCmdResponse` на doCmd* в бою (ID ClientMethod Avatar не измерен) — колбэк
  клиента не вызывается; серверное хранение настроек; серверный маркер прицела не реализован.

## Откат

`git revert` коммита карточки.
