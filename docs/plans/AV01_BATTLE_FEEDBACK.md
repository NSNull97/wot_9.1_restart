# AV-01 — аудиовизуальная обратная связь боя (2026-10-29)

Ветка `codex/av-01-battle-feedback` от `integrate/ft15b-20261029` = `a69ac83`.
Замечания владельца 29.10 (стенд -11, MM-01 3×3 и 15×15). Исследование — по
оригиналу `C:/WoT_0.9.1_RU_0717_original` (#717), байткод разобран как данные
(`tools/py27_static.py`, `tools/packed_xml.py`), клиентский код не исполнялся.

## Исследование

### Нумерация методов Avatar

VERIFIED (по якорям): фиксированные методы сортируются по размеру потока
устойчиво (как в P03G/P06K), переменные идут после них в порядке объявления,
методы интерфейса `Chat` (`onChatAction`, переменный) — перед собственными.
Правило сходится со всеми известными нативными ID шлюза: Avatar 0x3b, 0x3f,
0x40, 0x44, 0x45, 0x46, 0x48, 0x4a, 0x4c, 0x57 (explodeProjectile), 0x58
(updateArena); Account 0x48 receiveServerStats, 0x4d onCmdResponseExt,
0x4f onEnqueueFailure, 0x55 receiveQueueInfo, 0x57 update. Отсюда:

| Метод | Аргументы | ID | Статус |
|---|---|---|---|
| `Avatar.showOwnVehicleHitDirection` | FLOAT32 hitDirYaw, BOOL isDamage | 0x41 | INFERRED (фикс., между 0x40 и 0x42 по декларации) |
| `Avatar.onScoutEvent` | UINT8 eventType, OBJECT_ID reportedID | 0x42 | INFERRED |
| `Avatar.showShotResults` | ARRAY<UINT64> | 0x55, VAR1 | INFERRED |
| `Vehicle.damageStickers` | ARRAY<UINT64>, ALL_CLIENTS | свойство 6 → 0xa4, VAR1 | VERIFIED индекс 6 по create-layout шлюза; VAR1 — как 0xa5 |
| `Vehicle.engineMode` | TUPLE<UINT8,2> | 0xa2 | VERIFIED (ENGINE-SOUND, `codex/engine-sound`) |

### 1. Невидимый стрелок

- VERIFIED: `PlayerAvatar.showTracer` (line 1683) принимает отсутствующего
  стрелка: `BigWorld.entity(shooterID)` = None → трассер от `refStartPoint`.
  Клиент рассчитан на трассеры невидимых стрелков.
- VERIFIED: звук пролёта — эффект снаряда `projectile/effects/sound`
  (`/guns/tracers/tracer_*` в shot_effects.xml), идёт с трассером.
- VERIFIED: звук выстрела — `Vehicle.showShooting`, метод сущности стрелка.
  Без сущности (невидим) его не может быть и у родного сервера (INFERRED).
- VERIFIED: `Vehicle.showDamageFromShot` использует attackerID только для
  сравнения с `playerVehicleID` (маркер) — для своей машины можно слать 0.
- VERIFIED: `showOwnVehicleHitDirection` → `Aim.showHit(gYaw, isDamage)` →
  индикатор урона `wg_globalYaw` — мировой yaw, передаётся без преобразований (VERIFIED);
  поворот корпуса/камеры учитывает native-компонент. Направление: курс полёта снаряда
  `atan2(vx, vz)` (OBSERVED: обратный курс владелец 29.10 видел с противоположной стороны).
- Шлюз до AV-01: трассер, остановка и попадание только при видимом стрелке
  (`server.rs` ~2355), индикатора нет вовсе.
- UNKNOWN: откуда родной сервер начинал трассер невидимого стрелка.
  Проектная политика: стрелок в трассере = 0, `refStartPoint`/скорость сдвинуты
  вдоль баллистики на 40 м (`HIDDEN_TRACER_OFFSET_M`), остаток дальности
  уменьшен; если полёт короче — трассера нет. Точка начала не раскрывает
  позицию точнее, чем направление, которое и так показывает индикатор урона.

### 2. Двигатель

VERIFIED (ENGINE-SOUND): `engineMode` = (powerMode, dirFlags); 0 off, 1 idle,
3 high; create шлюза пишет (0,0) и не обновляет → двигатель «выключен».
Решение: после ACK создания слать текущий режим из серверного `Actor.input`
(throttle/steer/cruise), off при смерти/неактивном экипаже/уничтоженном
двигателе. Режим 2 не используется (условия родного сервера UNKNOWN).

### 3. Голос

- VERIFIED: «пробил / не пробил / рикошет / без урона» стрелку — только
  `Avatar.showShotResults` (флаги `VEHICLE_HIT_FLAGS` constants.pyc line 983);
  шлюз его не слал. Отображение исхода в флаги — INFERRED (пробитие с уроном →
  MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_PROJECTILE, непробитие →
  ..._NOT_PIERCED_BY_PROJECTILE, рикошет → RICOCHET, HE с уроном без пробития →
  ..._PIERCED_BY_EXPLOSION, пробитие без урона → ARMOR_WITH_ZERO_DF_PIERCED).
- VERIFIED: «Противник обнаружен» — `Avatar.onScoutEvent(SPOTTED=0, id)` →
  `enemy_sighted`/`enemies_sighted`. Шлюз не слал. Отправляем засветившему по
  журналу первого засвета (`result_spots`, тот же проектный policy, что в
  итогах) — только первый засвет каждой цели (INFERRED, родной повторял ли — UNKNOWN).
- VERIFIED (P07B_AUDIO_BOUNDARY): «Вас обнаружили»/шестое чувство в #717 —
  лампа без голоса; в `gui/sound_notifications.xml` такого события нет.
  Серверу слать нечего.
- Голос модулей (showVehicleDamageInfo) уже работал.

### 4. Декали

VERIFIED: декали ставит `Vehicle.set_damageStickers` (vehicle.pyc line 316):
множество кодов UINT64, тот же формат, что точки `showDamageFromShot`
(`decodeSegment`), но байт 0 = stickerID из `damage_stickers.xml`
(small_hole 0 … large_ricochet 7, порядок `_readDamageStickers`), выбор по
`targetStickers` группы эффектов снаряда (armorResisted/armorPierced). Шлюз
свойство не обновлял (create пишет пустой массив). Решение: последние 30
кодов на цель (лимит VAR1), рассылка видящим цель.

## Шаги

1. `shared/av01_feedback.rs`: кодеры и политики (+unit-тесты).
2. `server.rs`: анонимный трассер/остановка, попадание по себе от невидимого,
   индикатор, showShotResults, onScoutEvent, engineMode, damageStickers.
3. `mod.rs`: кэши по получателю, сброс при выходе из AoI.
4. Тесты: unit + набор шлюза против `a69ac83`, равные FAIL.

## Приёмка

Бой владельца на одном клиенте для звука (два клиента звучат искажённо).
Откат — не вливать ветку / `git revert`.

## Итог (2026-10-29)

Изменены: `shared/av01_feedback.rs` (новый: кодеры/политики + 5 unit-тестов),
`shared/server.rs` (анонимный трассер, остановка без ID стрелка, попадание по
себе от невидимого, индикатор, showShotResults, `publish_av01`: engineMode ≤6 и
damageStickers ≤2 тела за проход, onScoutEvent; `impact_visual` вынесен из
цикла попаданий), `shared/server_av01_tests.rs` (3 пакетных теста),
`shared/impact_wire.rs` (`show_damage_from` с явным ID атакующего),
`shared/mod.rs` (кэши по получателю, сброс при выходе из AoI).

Всё новое работает только при `visibility_v1` (как на стенде -11); прежние
лабораторные публикации без видимости байт-в-байт прежние. Логи:
`AV01_TRACER_ANONYMOUS`.

Тесты (incremental cargo, toolchain 1.90.0, `--test-threads=4`):
ветка 1747 PASS / 94 FAIL / 13 ign, база `a69ac83` 1739 / 94 / 13 —
множества FAIL равны (94 = 94; фикстуры удалённых worktree/сборок, как в базе).
Логи: worktree `local/test-runs/{branch-full3,base-full}.log`.

NOT_RUN: канонический gate, release, native-бой. Проверка владельцем одним
клиентом: трассер и свист от невидимого стрелка, индикатор урона и его
направление, голос «пробил/не пробил/рикошет», «Противник обнаружен»,
двигатель своего/чужих танков (газ/холостой/разворот/смерть), декали.
Если индикатор указывает не туда — поменять знак yaw в `hit_direction`.
Если 0x41/0x42/0x55 неверны, клиент отвергнет сообщение (канал) — тогда
откатить ветку.

## Приёмка владельца (2026-10-29 ~12:30)

Стенд -11, сборка `d988b3d` = `a69ac83` + NET-01 `8165663` + AV-01 `329643e`, бой 15×15 (1 игрок + 29 ботов):
«по AV-01 всё корректно работает» — звук двигателей, голос «пробил/не пробил/обнаружен», декали — **PASS (owner native)**.
Трассер незасвеченного стрелка владелец отдельно не проверял — NOT_RUN.
Канонический gate в составе `d988b3d`: 1840 PASS / 2 FAIL (tests_p04m, норма) / 13 ignored — PASS.

## Исправление индикатора (2026-10-29)

Владелец: индикатор рисовался с противоположной стороны (попали спереди — показывает сзади).
`hit_direction` теперь шлёт курс полёта снаряда `atan2(vx, vz)` вместо обратного. Тест
`av01_hit_direction_is_shell_heading_for_each_side` (фронт/корма/борта/глобальность yaw) — PASS;
тесты AV-01 8/8 PASS. Native-повтор индикатора — NOT_RUN (бой владельца).
