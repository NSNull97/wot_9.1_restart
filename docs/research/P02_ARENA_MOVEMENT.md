# P02 — native команда движения и серверное положение

2026-10-05. **PASS узкой карточки native movement/position. Полный бой — NOT_RUN.**
Q=`local/evidence/20261005-p02-arena-movement/`.
План: `../plans/P02_arena_movement_probe.md`.

## Цель и границы

Один настоящий #717, своя учётная запись, собственный МС-1. Установить цепочку:
original `PlayerAvatar.moveVehicle` → родной RPC → серверная команда →
серверный tick/position → original фильтр/сущность/модель → stop.
Это лабораторная кинематика, не исторический гусеничный контроллер.
Грунт, столкновения, баллистика, второй игрок, полноценный бой не входят.

## Подтверждённый статический контракт

VERIFIED: `Avatar.pyc`, original `scripts/client/Avatar.py:2130`, метод
`moveVehicle(flags,isKeyDown)`, code SHA256
`1fa74dc9bb83f2e8103aa1a146b9c174bb4bcae7b0a7280b993eef5f8ac2f826`.
В PREBATTLE original делает ранний возврат offset12; штатный путь до base
возвращает345. Для этой команды сервер отправляет period3 только внутри
явного `legacy091-arena-movement-probe`. Ordinary и прежний Ready period2
сохраняются. Original переход period3 может отправить автоматический stop0;
он не заменяет нашу отдельную пару forward1/stop0.

VERIFIED по original PE: server0x15 `avatarUpdateNoAliasDetailed`, own entity
u32 + позиция3float32 + направление3float32,28Bpayload. Перед ним идёт
`tickSync`0x0d/low8tick:31Bbody вместе. Фильтр использует сетевое время последнего
тика, а не значение `BigWorld.serverTime()` как прямой timestamp каждой точки.
Controlled entities могут игнорировать этот обычный update; фактическая реакция
в данном опыте должна проверяться отдельно. `controlEntity`/`forcedPosition`
не отправляются. Доказательства: Q/wire/CONTRACT.md и static-01.

VERIFIED: complete move envelope0x8a/VAR2/1B flags0или1. Отдельно распознаётся
bounded original aiming; эти сообщения явно неподдерживаемы и не меняют мир.
Whole-envelope и piggyback tree проверяются до commit; неверный хвост не может
применить первый валидный метод. Домен не принимает клиентские координаты.

## Лабораторная политика

10Hz — частота нашего опыта. Clock1000ticks, period3/end160/length60.
Старт[-58.499908447265625,33.770267486572266,-445.81304931640625].
Скорость1m/s по+Z, максимум2m, только после actual forward1. Stop0 обязателен
не позже8s; достижение2m само по себе успехом не считается. Сервер использует
монотонное время и отправляет последнее состояние без воспроизведения
пропущенных тиков. Клиентское наблюдение: original calls, разные entity/model
матрицы и filter speed/contacts, native PNG до/после, стабильная остановка≥2s.
XZдопуск0.02m меньше одного серверного шага0.1m; Y записывается отдельно.

UNKNOWN: историческая динамика, точное предсказание/коррекция, контакт с грунтом.
Original ресурсы не заменяются современными характеристиками. Ни координаты,
ни часы, ни inputkeys в клиенте диагностикой не присваиваются.

## Проверки до native запуска

181 Rust PASS,40 control PASS,40 runner PASS,18 profile PASS;
33 scenario Python3 PASS,32 Python2.7.3 PASS+1host-onlySKIP;
compile273 PASS. Первый Rust журнал180PASS/1FAIL сохранён: ошибка отрицательной
фикстуры — сам тест отправлял ACK, подтверждающий якобы неподтверждённый create.
Исправлена фикстура; поведение transport ACK не ослаблялось.
Q/wire/movement-integration-01/cargo-test-02.log; Q/root-checks-02;
Q/root-checks-01 (runner); Q/gui/scenario-checks-01.

Сборка EXE SHA256
`b878f7d91d6879421ce64f0ca75a82dca77ab3f6cc55b1cf0d888a439c6fde8c`.
Q/server-rebuild-01 содержит исходники, хеши, offline build и команды.
Baseline373 authored sources/17local files/2SQLite backups сохранён;
normal012 снят с сохранением ownerlogs. Все клиентские производные/секреты
остаются в ignored local. Оригинал только читался.

## Native результат

Move01 — **FAIL наблюдателя**, без команды вперёд. Original automatic
`moveVehicle(0,False)` законно вернулся offset12 до активной фазы. Наблюдатель
ошибочно требовал345. Узко исправлена только классификация автоматического
раннего stop0 как наблюдения без RPC; explicit forward/stop всё ещё требуют345.
Первый корпус не переписывался: PID74296,56.454s,154packets,exit0/restorePASS.
Q/gui/observer-fix-01 и Q/data/verify-move01-negative-01 сохраняют отказ.
Исправленный сценарий:36Python3 PASS,35Python2.7.3 PASS+1host-onlySKIP.

Move02: **OBSERVED настоящим клиентом** PID114140,63.536s,437packets/14794B.
Original forward call85/RETURN345 связан с native client sequence50,
stop call89/RETURN345 — с sequence80. Сервер принял один automatic idle0,
один forward1 и один stop0.97 server publications с own monotonic tick;
пересечение low8tick1023→1024 проверяется по actual последовательности.
Серверный интервал forward→stop2.989463s; лабораторный предел достигнут2m.

| Readback | До | После | Изменение |
| --- | --- | --- | --- |
| Vehicle.position Z | −445.8130188 | −443.8130188 | +2m |
| Entity matrix Z | −445.8130188 | −443.8130188 | +2m |
| Model matrix Z | −445.8130188 | −443.8130188 | +2m |
| getOwnVehicleMatrix Z | −445.8130493 | −445.8130493 | 0m |

Native XZ стабильно после stop≥3.015s по отдельной шкале trace elapsed.
Диагностический observed_at даёт3.022s; эти две шкалы не смешиваются.
Ground Y: server33.7702675/native33.6994286; contacts0/0,
gun_rotator_started=False. Это ограничения опыта, не доказанная поломка
исторической физики и не замаскированный PASS полноценного контроллера.

При закрытии осталось четыре отправленных stopped-target update sequence136–139
за0.38353s без клиентского ACK. Их **доставка NOT_RUN**, они отдельно перечислены
и не используются как доказательство движения/выдержки после stop. Решающий
интервал подтверждается уже ACKed publications и native readback. Допускается
только ограниченный terminal suffix собственного TXwindow8, а не произвольные
потерянные сообщения. Full production transport stress здесь NOT_RUN.

Exit0, четыре wrapper cleanup и оригинальный teardown PASS; свежего Python
traceback нет. Старые Vivox-unavailable/AccountRepositoryNone warnings остаются.
Оба nativePNG действительно просмотрены: карта, свой МС-1, HUD90/90 видны.
Цветная сетка остаётсяUNKNOWN, звук не оценивался. Управления мышью/клавиатурой,
внешнего kill/таймаута EXE не было. Выход — по диагностическому условию.

Доказательства:

- Q/move02-prepare/native-outcome.json — процесс, capture, source provenance,restore.
- Q/move02-prepare/wire/capture.json —437 реальных пакетов, исходные индексы/хеши.
- Q/move02-prepare/gateway-span.log — server commands/state/publications.
- Q/move02-runtime/native-114140-1791202105287.jsonl — original calls/readback/cleanup.
- Q/move02-visual-review.json — просмотр двух actual PNG; SHA256
  `d938e8934c596c465021e6817e00d43264f924017a2d8706fa4d8e027b23c0ec`.
- Q/gui/native-move02-review-01/result.json — независимый lifecycle review,
  SHA256 `4ba5c6e631b2614ed984d760acbb5700bd4a03240bd106c01852b6906194502a`.
- Q/data/verify-move02-final-01/arena-movement-native-verification.json —
  окончательная независимая связка evidence:19/19 PASS, SHA256
  `dc09da9016bb6fe6f2e8c4391dd7de7a3f4203271eb014aab759db53bd20548f`.
- Q/move01-replay/restore.json и Q/move02-replay/restore.json — generated replays
  сохранены, связаны с запуском/hash/header/mtime, прежнее отсутствие восстановлено.

PNG before SHA256 `b0837052c2dc62c169a2e82cd6f1c2beed0b287220a5000b9a95e2e90d131ec7`;
after `88e8c51075ac228d818446f09e3723e365e42c269a3e153004605d9eb587c43c`.
Оба лежат в Q/move02-runtime/screenshots/.

Проверщик:39 tests PASS, повторный анализ того же Move02 даёт байтово
одинаковый отчёт. Его ранние FAIL/кандидаты сохранены. Исправления reader:
точные положительные originalcallIDs, длительность по двум traceшкалам и
terminal suffix≤8 по фактическому transport window. Verifier SHA256
`43537771ab6d20898a6b502d679291b783fcb0446cac87f19077d43f1ca7e043`.
Это изменения анализатора; original capture не менялся.

## Изменённые файлы и состояние

Новые: `client_patch/arena_movement_scenario.py`,
`tools/wg_probe/src/arena_movement091.rs`, `tools/verify_arena_movement_native.py`,
`tests/test_arena_movement_scenario.py`, `tests/test_arena_movement_native.py`,
план карточки и этот отчёт.
Изменены: `client_patch/sr_interactive.py`, `tools/interactive_client.py`,
`tools/diagnostic_client_run.py`, `tools/local_server.py`,
`tools/wg_probe/src/{gateway091,arena_control091,main}.rs`,
`tests/test_arena_diagnostic_control.py`, README,STATUS,MISSING_INPUTS.

Normal013 установлен:22modules/31immutable+3ownerlogs. Клиент закрыт; обычный
сервер run20261005T121443-951a48 без capture/trigger/autologin/autoquit.
Сайт не перезапускался. Manifestoriginal3469/research3496 выполнен после
обоих rollback/replayrestore и normal013. Итоговая сверка файлов, профилей и
конфигураций — Q/final-audit-01/final-state-audit.json, отдельная приёмка.

## Команды

Из корня `D:\WoT_9.1_Server`, host checks без запуска клиента:

```powershell
. .\tools\rust_env.ps1
cargo test --offline --locked --manifest-path tools/wg_probe/Cargo.toml
python -B -X utf8 tests/test_arena_diagnostic_control.py
python -B -X utf8 tests/test_arena_movement_scenario.py
python -B -X utf8 tests/test_arena_movement_native.py
```

Для повторной проверки сохранённого Move02 без игры точная полная команда
со всеми локальными входами и новым выходным каталогом находится в
Q/data/movement-verifier-checks-final-01/repeat-command.ps1.txt.

Точные исторические native команды (каталоги one-shot уже использованы):

```powershell
python -B -X utf8 tools/diagnostic_client_run.py --install local/evidence/20261005-p02-arena-movement/move02-prepare --service local/server/service.json
python -B -X utf8 local/evidence/20261005-p02-arena-movement/trigger_move02.py
```

Они не предназначены для повторной установки использованного ledger. Для нового
опыта нужны свежие каталог/control/trigger, штатный rollbackordinary и replay
baseline; очистка кэша или подстановка native-outcome не заменяют запуск.
Команды build/start/prepare сохранены в Q/*.command.json и соответствующих
Q/server-rebuild-01,Q/server-restart-02,Q/ordinary-server-01.

Обычный сервер и ручной вход в ангар:

```powershell
python -B -X utf8 tools/local_server.py status --config local/server/service.json
python -B -X utf8 tools/local_server.py start --config local/server/service.json
Start-Process -FilePath 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research\WorldOfTanks.exe' -WorkingDirectory 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research'
```

## Ограничения, приёмка и следующий шаг

**NOT_RUN:** полноценное управление гусеницами, historicalphysics,groundcontact,
Avatarammo/стрельба/попадания, второй игрок, итоги боя, replayplayback,
длительная нагрузка, ручной вход именноnormal013. **UNKNOWN:** семантика связи
nativecontrolled/physics/getOwnVehicleMatrix, причина Yoffset/нулевыхконтактов,
цветная сетка. Новых входных файлов или действий владельца для этого опыта
не требовалось. На gateway пока одна активная сессия.

Единственный следующий проверяемый шаг: установить и испытать родной контракт
управления собственной машиной — связь controlEntity/серверной коррекции с
getOwnVehicleMatrix. Сначала original код/пакеты и ограниченный опыт; full
контроллер/коллизии этим отчётом не начинаются.

## Откат

При закрытом клиенте:

```powershell
python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-013
```

Для полного возврата до карточки остановить только собственный supervisor,
восстановить только перечисленные изменённые исходники из
Q/baseline-01/project-before.zip и удалить только перечисленные новые файлы,
проверив текущие hashes по финальному inventory. Вернуть сохранённый
Q/server-rebuild-01/gateway-before.exe, SHA256
`807fe8e6da0e5969b5b521450bb616e2c94695603e0c746bb28a91eee879fa7a`.
Затем подготовить **новый** ordinary package прежними исходниками и запустить
сервер. Не распаковывать весь ZIP поверх проекта: webработа сохраняется.
DBbackups не восстанавливать: игровые данные карточка не меняет.
