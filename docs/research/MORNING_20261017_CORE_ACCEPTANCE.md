# Core: фактическая утренняя приёмка 17 октября 2026

Владелец явно разрешил запуск Core и обоих собственных клиентов. Продолжать
ручной сценарий; новые ночные фичи и merge непринятых карточек не начинать.
Исходный ночной отчёт сохраняет состояние до этого разрешения.

## Сборка и завершённый первый запуск

- Checkout `C:/wot091-night-20261017-01/w`, ветка
  `codex/build-legacy-entrypoints`; runtime64767ec / tested200dcd2, full925.
- Core binding SHA `f20b5b10feb7e56570be465108f84723167382f985d1ef0dd5c003f14ac27d50`.
- Завершённый service run `morning-core31-01`, Core data отдельно от rooms/Hold.
  UDP127.0.0.1:20130/20131, private identity127.0.0.1:3481.
- Собственные native A/B PID107940/78704. Каждый PID привязан к creation/image
  receipt, а не используется отдельно как разрешение на остановку.
- Оба выбранных танка — `ussr:MS-1`, inventory1,90HP. Initial loaded
  ББ/КС/ОФ A[0,48,48], B[0,50,46]; это зафиксированный исходный loadout.

Текущие trace/profile/control и установочные планы находятся в
`C:/wot091-night-20261017-01/w/local/stands/night-battle-20261017-03/unified-01/client-v8-morning61-final`.
Доказательства утра:
`C:/wot091-night-20261017-01/w/local/evidence/20261017-morning-core01`.
Не публиковать control, credentials, ключи, БД или клиентские ресурсы.

## Исправления именно операторской обвязки

Сначала фактически выполнены V7 rollback ОБОИХ, prepare ОБОИХ, install ОБОИХ.
Не повторять эти действия на используемом контексте. Все исходные отказы сохранены.

1. Prepare отказал FileNotFoundError: перенесённый helper загружает
   `client_patch/project_network.py` относительно себя. В ожидаемое новое место
   добавлена точная bound-source зависимость SHA
   `e4a8cc9547308890e7b36dc226563dade526d1ae3200c7a36e7ea1b45a94da0f`.
   Исходные46 frozen/22 helper members после обеих установок совпали.
2. Исходный check_clients отказал PORTABLE_MEMBER на реально созданных Windows
   `compiled\map_drive_client.pyc/json`. Новый guard114 принимает только эту
   точную пару в канонической POSIX/Windows записи; исходный child и остальные
   source/PYC/version8/settings1/ledger/installed-byte guards сохранены.
   Планы и ledgers не переписывались.
3. Launcher116 preflight отказал BOUNDED_INPUT на закреплённом Node93,580,104B.
   Новый117 потоково хеширует только этот точный Node image, с точными размером
   и SHA, максимум expected+1B. Для остальных файлов прежний64MiB guard.

Новые пакеты сохранены отдельно под
`C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk`:
`morning-client-guard114`, `morning-launcher116`, `morning-launcher117`.
Старые frozenM61/78 и отказы сохранены. Launcher117 сейчас **только Core**;
следующие rooms/Hold ещё требуют своего проверенного successor.

## Реально выполненные проверки

- Guard114:16PASS/0SKIP, включая полную readonly проверку ОБОИХ фактически
  установленных overlay:39source/52target/49immutable на каждый.
- Launcher117:9PASS, planPASS, actual full preflight A/B PASS.
- Оба private own identity HTTP200; реальные native launch A/B PASS.
- Каждый клиент дал два последовательных текущих native_hangar события:
  connected/cache/model=true, waiting=false, lobby_sub=Hangar/flash_bound=true.
  B запущен после этого подтверждения A.
- Full925, service image/argv/PID и source-bound markers повторно проверены;
  это не новая полная сборка Cargo и не приёмка всех боевых критериев.

Команды фактического запуска сохранены как структурированные argv в
`launcher117_launch_a.command.json` и `launcher117_launch_b.command.json`
в указанной папке доказательств. Не выполнять их повторно: попытки этого run
одноразовые. Launcher117 run SHA
`0da31929fa90961a3920564f044778c59dd13846e40c96fc2acf3783d7510026`,
context SHA `19c4d12373a3063890436ccaa3e653dab92bedb683cdf275af1aab31f1e6836a`,
guard SHA `3fe3899e2000a1711b221ac2c9c958d6142ce92c827d55693c5df82dfb11c22b`.

## Ручные случаи

| Случай | Состояние | Основание |
|---|---|---|
| Отмена и повтор очереди, общий бой, управление и красные маркеры | PASS этого случая | OBSERVED владельцем; VERIFIED сервером Cancel, повторные Join, READY×2 и Prebattle30000→Battle900000 |
| По1КС/1ОФ в землю каждым; ручной выход обоих; остатки A[0,47,47]/B[0,49,45] | FAIL возврата / PASS расхода | Владелец: выброс обоих; все4accepted shots и writerFinished×2; readonlySQLite revisions134/46, active0, остатки совпали |
| Повторный общий бой после ручного выхода | NOT_RUN | После подтверждения предыдущего шага |
| Уничтожение/личные и командные итоги/захват/таймер/автоприцел | NOT_RUN новой сборки | Отдельные случаи; автоприцел пока штатно сбрасывается, полного захвата нет |
| Смешанные машины/таран/засвет/rooms/Hold/детонация/дваПК | NOT_RUN новой сборки | Не подменять software compositions ручной приёмкой |

Первый ответ владельца: «Отмена сработала, общий бой начался, оба управляются,
маркеры красные». Бой4379300209826287858. Доказательство `manual-step01.json`;
логовый hash относится к зафиксированному префиксу растущего файла.
Наблюдательные oracle-события и их отказы сохранены отдельно в native-audit01:
уB AP-marker oracleFAIL/0cases и collision oracleValueError; gameplay=false.
Эти отказы не дают основания закрывать P05C по первому ручному случаю.

Шаг2: первый ручной выход дал Forfeit и asyncFinish; до завершения возврата
world был сброшен. Публикация Leaving обратилась к старому slot в новом пустом
world (`shared/mod.rs:303`), containment сохранял Leaving и повторял reset.
Фактические2157failures/2159resets;102,920,587B аварийных снимков из105,923,808B
gateway-лога. Gateway остановлен первым по своему receipt, чтобы остановить
рост; затем собственныеB,A,bridge. Старые логи и БД сохранены.
Доказательство manual-step02-fail01.json. Полная приёмка возврата — FAIL.

Дополнительно OBSERVED владельцем: отсутствуют трассер/взрыв незасвеченного
стрелка, даже рядом; сильные задержки queue/join/leave. VERIFIED: все4shots
имеют cross-peer SHARED_SHOT_CUE queued=false/not_observable_at_event;
публикация требует видимость стрелка. Нужен отдельный recipient-interest для
видимого участка снаряда без раскрытия скрытой позиции; просто передавать
исходную точку выстрела нельзя. Native anonymous FX ещё NOT_RUN. Ранние
join/cancel задержки возникли до logstorm; их причина UNKNOWN.

Readonly latency124 уточнил критический путь: один writer удерживается во время
последовательных battlePOST→profilePOST→полного fixture/metadata refresh. Два
отдельных Python процесса каждый заново разбирают426catalogfiles/3,973,052B и
audit16pyc/394,124B. Даже существующая revision проекция заново строится для
byte-compare. Затем требуются реальные outbox/txACK, фиксированный entryhold3с,
scene verification/spawn/180вычисленных settle steps и native handshake.
Actual sampled enqueue→BattleQueue A9.392/10.763с,B13.321с; повторный
enqueue→первыйPlayerAvatar A23.0867671с,B19.4731349с. Первые1000gatewaylines до
Prebattle не содержат retry/error/failure. HTTP20с — deadline, не sleep;
retry2с не наблюдался. Leaf durations и вклад CPU/IO UNKNOWN. Это диагностика,
не исправление задержки; новый retest наблюдать через readonly121.
Внешний audit124 SHA3f446fe1ca5c980945ca69a3ee1a4fea14a0d811f672fc08dfa4f50677828e1d.

## Остановка, откат и следующий шаг

### Свежий исправленный запуск full03 / retest120

Runtime/tested HEAD `19ba479917c0597495ebfa0a5f2b47a03521261b`, ветка
`codex/stab01-core-return-reset`. Полный canonical gateway:1628PASS/0FAIL/
5прежнихignored за1277.71с, buildPASS; source-before/source-after925raw exact.
Early14STAB:14PASS/0FAIL/0ignored за5.65с, включая все9новых регрессий карточки.
Серверный exe SHA `d159ff95041ac4eea7fc6aa0328625abb7cdf089b9aaac6d11829cbb293ddabc`.
Backup push/runtime remoteSHA19ba479 сверён; mainffce8cb не менялся.
Последующие docs-only descendants не меняют эти925source или testedHEAD.

Изменённые runtime-файлы: shared/server.rs (barrier/retained world/ingress/
retirement), shared/mod.rs (contained marker/reset); регрессии в detached_turret,
profile13_flow и owner_hold_integration. Node helper и owner_hold_four test
меняют только общий watchdog210/360с. Production deadlines прежние.

Новый stand `C:/wot091-night-20261017-01/w/local/stands/morning-core-retest-20261017-01`,
mode `core-loss4`, tag `core-retest118`, run `core-retest118-01`. Число118 —
неиспользованная data identity; выполняется исправленный frozen package120,
а не пакет118. Все21freeze members120 совпали. Исходный installedV8 обоих
переиспользован после readonly проверки всех source/PYC/installed bytes.
SQLite backup сохраняет все таблицы, depot/history, loaded и revisions134/46;
новых grants0, sourceDB не изменена. LoadedA[0,47,47]/B[0,49,45], active0.

Binding SHA `11adca7be7536664c8d18519bdf22e3531d6f5e29dc3a9b550ffc066f5e6bea5`;
context120 SHA `754306ca7c3f624e04366d09777b7a462c00aa1fe160a8fcec0149130ec0fc3e`;
operators SHA `8a1686be9c9f6e798fdd75b7595003b2736a19d6472ec9582b13335e714d5e5c`;
native commands SHA `620fcb697ebfb3f7ddaace78f46f38820b10135e599b78831faa25f6410e558c`.

Реально выполнены Python3.14 `-B -X utf8` команды из указанной папки evidence:
`run_stab01_full03.py`, затем `prepare_retest120_03.py` (verify-freeze→data→
publish→bind→seal), затем `run_retest120_action.py` с закрытыми действиями
check/check_clients/services, preflight_a/launch_a/ready_a и
preflight_b/launch_b/ready_b. Exact argv, UTC и exit0 сохранены в
`retest120_03_*.command.json`; не повторять одноразовые prepare/launch argv.
Public пакеты operators-core120.json/native-commands120.json находятся в
`C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk/morning-core-retest120`.

GatewayPID118080, nativeA118548, nativeB114600 связаны с creation/image receipts.
Оба privateauth и launchPASS; A дал два настоящих текущихангара до запускаB.
У обоих currentPlayerAccount(nativeDB1/2), connected/cache/model=true,
waiting=false, lobby_sub=Hangar/flash_bound=true. Это PASS запуска, а не боя.

Evidence full/source:
`C:/wot091-night-20261017-01/w/local/evidence/20261017-stab01-return-reset-full03`;
build/test logs:
`C:/wot091-night-20261017-01/w/local/build/server/gateway-stab01-return-reset-full03`;
actual launch/readiness/old failures:
`C:/wot091-night-20261017-01/w/local/evidence/20261017-morning-core01`.

Manual retest новойсборки NOT_RUN: оба «В бой!»→отсчёт→каждым1КС+1ОФ в землю→
первый Esc/Вангар и сразу второй Esc/Вангар (не ждать первогоангара, иначе
Forfeit успеет вернуть второго автоматически). Ожидание loadedA[0,46,46]/
B[0,48,44], оба настоящихангара, без выброса/чёрногоэкрана; наличие итогов
зафиксировать отдельно. Затем новый общий бой/управление. БК detonation,
эффекты/звук/UI и все остальные новые ручные случаи остаются NOT_RUN.
FX незасвеченного стрелка пока UNFIXED; задержки имеют readonly124audit, fix
не заявлен. Frozen observer121 подготовлен для actual run перед этим сценарием.

Остановка этого нового run: native-commands120 commands.stop.b, затем.a;
operators-core120 stop_gateway/stop_bridge — только с точными текущими receipts.
Откат runtime — остановка нового run и сохранённый совместимый старый binding
в новом контексте. Поздние mutableDB/израсходованные снаряды поверх старых не
восстанавливать. Ни старые targets, ни evidence, ни исходные клиенты не удалены.

### Сохранённая история неуспешных проверок

Исправление reset/retained-terminal-world проверено full01 на25ac184:
1624PASS/1FAIL/5old ignored,1292.59с; все6новых регрессий PASS. Единственный
FAIL actual4Hold — Node watchdog180с, Final4/all-finalSQL уже завершились на
162.139с, запросы/ACK результатов ещё шли. Точная причина изменения wall time
UNKNOWN. Raw925 исходников до/после совпали; source-after gate NOT_RUN приFAIL.
`stab01_full01_failure_retained.json` и исходные логи/failure.json сохранены.
Только тестовая обвязка получает Node210/Rust360с. Production timeouts и
assertions не меняются. Дополнительный review нашёл containedAvatar input ACK,
который до receive обновлял старый slot по replacementWorld. Incoming03 проверяет
retained identity/view/receipt и сохраняет фазуLeaving в атомарном receive;
результатный retirement также использует старый outcome. Три новые регрессии
проверяют positiveACK/confirm, poison/forged input, ordinary ingress и Hold5
natural-old/new-live. На этом checkpoint execution/full02 ещё не запускались.
Full02 b1beb0f compilePASS; early14:13PASS/1FAIL нового Hold fixture — Capture
не получил departed_after_detach peer12 до Forfeit. Строгий source/terminal
validator отказал корректно. Полный02 остановлен exact own process handle после
проверок image/creation/runner ancestry/children0; cargo/build/runner exited1.
925raw source совпал до остановки; full final counts отсутствуют, source-after
NOT_RUN. `stab01_full02_abort_retained.json` сохраняет логи/бинарник/stop proof.
Fixture04 добавляет только production departure hook и typed peer/own assertions;
production/validators прежние. Последующий PASS full03 описан выше;
ручной retest новойсборки ещё NOT_RUN.

Старый run из `live-handoff01.json` уже остановлен. Его одноразовые argv не
применять к текущему run120; актуальные stop packets указаны выше. Не убивать
процессы по одному имени/PID. Overlay rollback — только с фактическими V8
ledgers; уже списанные снаряды и БД сохранять. Ничего не сбрасывать/не выдавать.

Статус всей цепочки: **PENDING_OWNER_RETEST, вне main**; прежний ручной FAIL
сохранён. Текущая зависимая ветка `codex/stab01-core-return-reset`, runtime19ba479;
исходный tested200/runtime647 сохранён. Единственный следующий шаг — ручной
retest4groundshots→быстрый Escобоих→loadedA[0,46,46]/B[0,48,44]→общийбой.
