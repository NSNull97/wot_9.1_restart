# POSTMORTEM-01 — режим наблюдателя после смерти и маркер убитого союзника

Ветка `codex/postmortem-01-observer` от `c76fd62` (`integrate/ft15-20261029`, сборка стенда -11 на 29.10).

## Находки владельца 29.10 (стенд -11, MM-01 3х3, `p06t_mixed_ammo`)

Лог `local/stands/full-test-20261027-11/gateway-20261029-094601.stdout.log`, бой `47337667944004827`,
сессия 4 = arena_e (слот 2), arena_c = сессия 2 (слот 0), оба в одной команде, слот 1 — противник.

1. arena_e убит, в «Режиме наблюдателя» переключил камеру на союзника → строка 154715
   `SHARED_REJECT session=4 reason=channel_state sequence=Some(17381) bytes=16 … wire.rs:226:70`,
   далее 210 отказов `unsupported session input` (16 и 5 байт), `idle_timeout`, выброс.
2. arena_c убит выстрелом 23 слота 1 (тик 3596) — у arena_e в списке серый, маркер зелёный «0%».

## Исследование

VERIFIED (дизассемблирование `res/scripts/client/*.pyc` клиента `local/clients/arena/d`, Python 2.7.3 `dis`):

- `AvatarPositionControl.bindToVehicle(bValue, vehicleID=None)`: при True — `__doBind(vehicleID or playerVehicleID)`,
  при False — `__doUnbind()`; оба шлют Cell `Avatar.bindToVehicle(OBJECT_ID)`, unbind — с ID 0.
- `PostMortemControlMode.__switchToVehicle` (стр. 1606) шлёт `positionControl.bindToVehicle(True, curVehicleID)`;
  список `__vIDs` (`__updateVIDsList` 1779) — машины `arena.vehicles` своей команды с `isAlive`
  (и своя), без тега `observer`. `__waitForCameraTarget` ждёт `BigWorld.entity(curVehicleID)`.
- `AvatarInputHandler.onControlModeChanged` (~501–504) шлёт `bindToVehicle(False)` при переходе в
  режим `isManualBind` (Debug, Cat, Strategic) и `bindToVehicle(True)` обратно. PostMortem — не isManualBind.
- Серверная видимость: союзники всегда в интересе (`visibility::Allies::Always`, `spotting.rs:171`), так что
  машина союзника у наблюдателя уже есть; смена камеры не требует менять интерес.
- `Vehicle.set_health` только запрещает «воскрешение»; маркер и `__onVehicleDeath` (маркер `dead`)
  вызываются из `onHealthChanged` (при `health<=0 и isCrewActive`) и из `set_isCrewActive`
  (при `not isCrewActive и health>0`). `VehicleMarkersManager.__getVehicleDamageType(0)` = `FROM_UNKNOWN`.
- `Vehicle.startVisual`: `if not isAlive(): __onVehicleDeath(True)` — поздно появившийся мёртвый получает маркер
  `dead` из `create_vehicle` (health 0, isCrewActive False); этот путь не менялся.
- 5-байтные пакеты — пустое приложение `[0x01, token u32]` (keepalive с новым надёжным номером),
  как в `P08C_NATURAL_RESULTS_RETURN.md`. Отказ 17381 не продвинул `rx`, и каждый следующий
  номер отвергался проверкой `n>self.rx` (`session.rs` `receive_ready_inner`).

INFERRED:
- Пакет 17381 = `0d 08 00 00000000 <vehicle_id союзника>` (байты в логе не сохранены; длина 16 = 5 + 11,
  а отказ в той же строке `if`, что сверяет ID со своим).
- arena_c: `SHARED_AP_PUBLICATION … session=4 shot=23 … queued=false` — убийца не был в AoI arena_e,
  поэтому `p06t_publication::health` отправил только свойство `health` без `onHealthChanged`.

## Изменения

- `wire::postmortem_bind_target` / `postmortem_camera`: нулевой mailbox + OBJECT_ID → Own / Ally(slot) /
  Unbind (0) / Refused (противник, не машина). Команда — только по публичному ростеру.
- `Session::shared_payload` (0x0d в Driving, своя машина мертва): все корректные формы потребляются,
  надёжный номер продвигается; Ally — `SHARED_POSTMORTEM_OBSERVE … interest_changed=false`,
  Refused — `SHARED_UNSUPPORTED method=bindToVehicle refused=true`. Живой владелец, неверный
  mailbox/длина — по-прежнему отказ (без изменений).
- `p06t_publication::health`: `onHealthChanged` всегда, ID атакующего 0 при скрытом (как
  `detached_turret::terminal_health`); получатели пакета — без эпохи скрытого атакующего.

## Проверки

- `postmortem01_observer_camera_switch_to_ally_unbind_and_enemy_keeps_channel_live`
- `postmortem01_visible_ally_killed_by_hidden_attacker_gets_native_death_callback`
- обновлён `native_postmortem_rebind_is_owned_dead_only_and_keeps_reliable_channel_live` (ID не-машины теперь потребляется)
- набор шлюза ветки против `c76fd62` в той же среде — FAIL равны (см. Итог)

## Не входит

- Режим Strategic (SPG) у живого: `bindToVehicle(0)` и обратно — сейчас отказ для живого (как раньше). UNKNOWN,
  есть ли САУ в пуле; отдельная карточка при необходимости.
- Видимость противников «глазами» союзника у наблюдателя — не менялась (интерес считается от своей машины +
  общий засвет команды, если он включён).

## Итог

- Целевые: `postmortem` 4/4, `p06t_publication` 14/14, `detonation` 29/29 — PASS.
- Полный набор шлюза (cargo test, worktree, temp target `local/target-pm01`): ветка `465c9af` 1727 PASS / 94 FAIL / 12 ign,
  база `c76fd62` 1725 / 94 / 12; списки FAIL совпадают (94 — среда worktree без канонического exe/фикстур, как у MM-01).
  Логи: `local/evidence-pm01/{branch,base}.log`, `.fail`.
- Канонический gate в `D:/WoT_9.1_Server`, release, native (бой владельца с наблюдателем) — NOT_RUN.
- Проверка владельцем на стенде: убитый игрок переключает камеру по союзникам (Пробел/мышь) — в логе
  `SHARED_POSTMORTEM_OBSERVE`, нет `SHARED_REJECT … channel_state`, сессия доживает до итогов; союзник, убитый
  невидимым противником, получает серый «мёртвый» маркер.

## Откат

`git revert` коммита карточки; конфигурация стенда не меняется.
