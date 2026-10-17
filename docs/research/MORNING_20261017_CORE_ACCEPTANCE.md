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

## Остановка, откат и следующий шаг

Точные stop argv сохранены в `live-handoff01.json`. Сначала штатный выход или
receipt-bound stop клиентаB, затемA; после них exact own gateway и bridge stop.
Не убивать процессы по одному имени/PID. Overlay rollback — только из исходного
публичного packet с фактическими V8 ledgers; уже списанные снаряды и БД сохранять.
Ничего не сбрасывать/не выдавать ради повторения сценария.

Статус всей цепочки: **FAIL_MANUAL_RETURN, вне main**. Текущая зависимая ветка
`codex/stab01-core-return-reset`; исходный tested200/runtime647 сохранён.
Единственный следующий шаг: исправить reset/terminal publication, выполнить
регрессию и полный suite новогоhead, затем свежий retest из actualCDB134/46.
