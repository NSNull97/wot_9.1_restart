# STAB-01 — диагностика устойчивости боя, 2026-10-15

Карточка STAB-01: пункт 1 `IMPLEMENTATION_ORDER.md`; после приёмки ACTIVE_GATE — P08B.
Ветка `codex/stab01-battle-isolation`, база `main` `1d19d2e`.

## Итог приёмки — VERIFIED / OBSERVED

STAB-01 принята на runtime `0574ab0c1df7a060bb6b3906febebf5e69d483d3`:
ошибка имеет caller context, world/trace fault закрывает только бой, оба клиента
вручную возвращаются в ангар и повторно входят через родную кнопку. Владелец
подтвердил движение, наведение и стрельбу обоих в повторном бою. P08B не начиналась.
Последующие изменения карточки — документация; runtime source pins неизменны.

- Финальный native-fix07: **5 worlds, 10 READY, 4 contained deadline faults,
  8 автоматических и2 ручных возврата**, все10 ACK/reset + warm complete,
  **0 SHARED_REJECT / SHARED_SESSION_CLOSED**, 10 workers завершились штатно.
  Это проверка изоляции сбоев; причины deadline >500ms не устранены.
- Ручной выход текущего head отделён от автоматического: session1
  `native_leave`3996 → Account ACK4002 → warm complete4021; session2
  `native_leave`4111 → ACK4116 → warm complete4122. В следующем мире
  `5514766083138551873` оба native Join приняты и READY4264/4272, слоты
  аккаунтов поменялись. Движение/aim обоих приняты; fire обоих подтверждён
  в совокупности повторных миров и owner-проверкой, не каждым отдельным миром.
- Evidence: `local/evidence/20261015-stab01-01/native-fix07/native-acceptance-summary.json`,
  SHA256 `2da816fe4bf7c15e30ccda191a8b497e5aa6d6b1133abbc74cf50d8ef295520f`;
  все строки выше — `gateway-stabfix07.stdout.log`. Сохранены две отдельные
  owner-проверки: управление после повторного входа, затем короткий ручной Esc-выход.
- Дополнительный старый helper `ready01/result.json` остаётся **FAIL_OR_NOT_READY**:
  предсуществующий пассивный observer на sample3 вызывает `getShotAngles` при
  `vehicleTypeDescriptor=None`, после ошибки перестаёт планировать снимки.
  Git blob `client_patch/sr_interactive.py` в main1d19d2e и runtime0574ab0 одинаков;
  игровая загрузка/родные обработчики продолжаются. Непрерывный native aim-oracle
  **NOT_RUN**, не выдан за PASS; обязательный native-критерий подтверждён владельцем
  и отдельными серверными событиями. Диагноз и source pins —
  `native-fix07/ready01diagnosis.json` SHA256
  `7b6b28b06a42d9ef1d0059297f69f5a1e0bf4812602d056fdb8c43f847fcff95`.
- Применимые проверки: полный gateway854 PASS / 5 ignored и сборка PASS на0574ab0,
  layout117files / 22relocations PASS; client/control194 PASS и Python2.7.3
  61 PASS / 3 host-only skips на неизменных client sources13edf3b. Исторический
  полный Python debt11failures / 8errors / 19skips, Linux и --legacy не закрывались.
- Native-fix07 остановлен строго по собственным receipts (`stop-acceptedrestore.json`),
  обе battle-установки и namespace откачены собственными ledgers. Ангар A/profile13
  установлен заново по прежним9 feature flags: `local/stands/p09e-main-01/install02-stab01-restore/`,
  fresh prepare/install PASS, прежний ledger повторно не использован. Его bridge/gateway
  не останавливались, контроль скопирован без вывода credentials. Свежий запуск
  восстановленного ангара **NOT_RUN**; эта операция восстановления не выдаётся
  за новый native-тест profile13. План/исходные SHA — `hangar-restore-plan.json`.

Файлы карточки: `client_patch/map_drive_client.py`; gateway `account/hangar.rs`,
`drive/worker.rs`, `session.rs`, `shared/{account_policy,destructible_wire,fragiles,
geometry,materials,mod,model,projectile,server,server_catalog_wire_tests,wire}.rs`;
`tests/test_map_drive_client.py`, `tests/test_map_drive_click_contract.py`;
`docs/{ACTIVE_GATE,STATUS}.md`, `docs/research/{INDEX,STAB01_BATTLE_STABILITY}.md`.
План STAB-01 удаляется из рабочего дерева при закрытии; сохранён в истории0574ab0.

Команды воспроизведения: fresh `create_stand.py --expected-head <полный runtime SHA>
--build gateway-p05b-stab01-fix07 --stand-name <новый native-...> --run <новый ID>
--stage fixed`, затем `run_commands.py --stand <...> prepare_a_dry_run
prepare_b_dry_run server_dry_run`, `prepare_a prepare_b`, `launch_server launch_a`;
после одного SESSION_ACTIVE — `launch_b`. Все argv сохранены в `native-fix07/commands.json`;
исторический binding status — только проверка соответствия runtime, не native-приёмка.
Следующий единственный шаг — P08B от main, начиная с одиночного map-drive пути.

## VERIFIED — диагностический срез

- Коммит `56f5f179dca2b6b3aebb1bda691e7e0c3c43031f`: `model::bad()` сохраняет
  `InvalidData` и сообщает файл/строку/столбец вызова через `#[track_caller]`.
  Передача функции в `ok_or_else` заменена явными ленивыми closures, иначе
  function-pointer shim теряет вызывающую позицию. Lifecycle пока не менялся.
- Полный gateway suite: **831 passed, 0 failed, 5 ignored**, затем сборка PASS.
  `local/build/server/gateway-p05b-stab01-diag01/{result.json,test.stdout.log}`.
  Gateway SHA256 `d18519235f421fcdad171a357cf463d4126048faf6325798750824199238cd93`.
- Новый локальный стенд `local/evidence/20261015-stab01-01/native-diag01/`.
  Binding SHA256 `f93b6066d63ba89828781f1839f93be043a05c9cc1c7e74416f7b5b93b470605`;
  все 321 tracked файла `server/tools/client_patch`, полный gateway artifact,
  шесть старых helpers (byte-for-byte) и зависимости candidate17 проверены.
  Старый `PASS_P05B_CURRENT_RUNTIME_BINDING` — имя схемы совместимости helper,
  не приёмка STAB-01. Неиспользуемый старый preprocessing probe выключен.
- Ангарная установка A `local/stands/p09e-main-01/install01` откачена по ledger.
  Для обеих разрешённых копий созданы новые namespace/install ledgers в новом
  стенде; оригинал клиента не менялся. Ангарный bridge/gateway не останавливались.
- Отдельный боевой identity bridge: `127.0.0.1:20020`, собственный PID 27000,
  `/health` PASS; receipt `local/stands/stab01-identity-01/launch.json`.

## OBSERVED — настоящий native-запуск

- Новый `legacy091-integrated-lab`, Прохоровка, однородная пара MS-1.
  Battle `11522436634285911744`; gateway log `gateway-stabdiag01.stdout.log`
  в новом стенде: два `SESSION_ACTIVE`, `SHARED_WORLD_STARTED`, два `SHARED_READY`
  (own IDs 152043523 и 152043525), движение/выстрелы обоих участников.
- Windows Computer Use не смог получить кадр обоих окон: `FrameArrived timed out`
  и `window capture timed out: timed out waiting on channel`; A повторно выбрана
  и проверена, B проверена после готовности боя. Слепые нажатия не выполнялись.
  Владелец запрошен выполнить Esc → «В ангар» в обоих окнах после двух минут.

## VERIFIED / OBSERVED — воспроизведение выхода

- OBSERVED: владелец выполнил выход обоих клиентов и подтвердил, что оба
  отключились/вернулись ко входу. Новый log: строки 12876 и 13038 —
  `SHARED_FAILED session=1|2 reason=shared laboratory contract at src\shared\server.rs:985:119`;
  следующие строки закрывают сессии на tick 2697 и 2743. Сводка —
  `native-exit-observation.json` в новом стенде.
- VERIFIED: на диагностическом head строка 985 — именно 90-секундный timeout
  `!full_ready`. Native Leave меняет фазу на Leaving, а full_ready требует Driving.
  Ошибка идентифицирована свежим executable и настоящим native-выходом обоих,
  а не только статической гипотезой.
- VERIFIED по исходникам: старый shared loop удаляет Leaving Session через
  `native_leave`, не отправляя native Account reset/create/warm sync.
- Диагностические процессы A/B/gateway остановлены после записи результата по
  своим PID/path/hash receipts: `stop-reprodone.json`. Старый ангар не затронут.
- Реализация исправления: отдельный shared Returning поверх ACK-bound
  WarmAccountReturn, warm100/300/600, сохранение каналов, явный лабораторный
  повтор через native700. Shared unit replay 9/9 и прежний warm regression 18/18
  PASS в изолированном worktree; это ещё не общий gateway gate и не native PASS.

## VERIFIED — исправленный lifecycle и граница ошибки боя

- Runtime head `9b4d26cfebe68e93d47aa2578c894d3cba9e55e3`: отдельный Returning
  сохраняет аутентифицированные UDP/reliable-каналы. Account reset/create следует
  после ранее поставленной отправки; новый warm sync принимается после ACK reset
  и native enable09. Проверены warm100/300/600 и ограниченный drain старого Avatar.
  Повторный native700 относится только к существующему laboratory profile4;
  выбранный танк ангара профиля 13 остаётся P08B.
- Обычный Leave после завершения подготовленной физической транзакции сразу
  отсоединяет своего actor и возвращает Account. Проверки area/correction и
  90-секундная проверка входа не блокируют выход. Команды вышедшего не применяются,
  оставшийся actor сохраняет управление. Объявленная очередь переживает повторное
  присоединение и явно отменяется при отказе до native Avatar.
- Ошибки world/trace-step и публикации ловятся общей границей боя в сервисе.
  `SHARED_BATTLE_FAILED` сохраняет причину и JSON-снимок в удерживаемом stdout:
  actor state/input/aim/fire/HP, снаряды, состояние объектов, SHA геометрии и
  ограниченный хвост последних 64 trace events с числом пропущенных событий.
  Это диагностический снимок, **не полный детерминированный replay**; команды и
  порядок сетевых сообщений остаются в отдельном журнале/pcap стенда.
- После ошибки старый runtime со всеми owned workers уничтожается, мир берётся
  из чистого source-bound шаблона с новым battle ID. Сессии возвращаются в Account;
  явная ошибка возврата журналируется и закрывает соответствующий transport.
  Сервисные sockets, авторизация, следующий session ID и retirement не сбрасываются.
  Подавления ошибок инфраструктуры через фиктивный успех нет.

## VERIFIED — проверки исправленного head

- Полный gateway suite и сборка: **845 passed, 0 failed, 5 ignored**.
  Команда `python -B -X utf8 server/build.py gateway --test --out
  local/build/server/gateway-p05b-stab01-fix04`; `result.json`, команды и полные
  stdout/stderr находятся в этом каталоге. Executable SHA256
  `cf1b068c757d4af311c5c82a46cea135d028e98426542d2b36299bbd9a82640a`.
- Пять meaningful STAB unit-сценариев: оба выхода после 90 с; отложенный выход
  через scene barrier при неготовых areas; настоящий native Leave до correction
  ACK6 сохраняет бой второго; отмена объявленной очереди после reattachment;
  инъекция настоящего trace invariant failure и новый бой в том же контроллере.
- Последний сценарий использует двух настоящих physics workers, проверяет их
  освобождение (EOF/exit0/reaped без принудительного завершения), новый чистый мир,
  сохранение transport/retirement и старт следующего боя с полным боекомплектом.
  Дополнительный exact-test replay с `--nocapture` сохранил действительный снимок
  с причиной `impact segment facts`: `local/evidence/20261015-stab01-01/fault-proof01/`
  (`result.json`, `failure-snapshot.json`, `test.stdout.log`). Это unit evidence;
  оно не подменяет проверку настоящего client UI.
- `python -B -X utf8 server/check_layout.py`: PASS, 116 source files / 22 relocations.
  `git diff --check`: PASS. Независимый статический review выявил и перепроверил
  исправления двух краёв: Leave до ACK6 и очередь до запуска Avatar.
- Прежние общие Python/legacy-долги из preflight сохраняются. Полный Python-набор
  на этом head не перезапускался; Linux/ARM и bitwise cross-platform replay NOT_RUN.

## OBSERVED / UNKNOWN — повторный native-стенд

- Свежий `native-fix04`, run `stabfix04`, binding SHA256
  `fe009c724e283ca8e2bc7f3b99366e1f445fb5b9df30b85449563dc0225c6bc3`.
  Все 321 tracked runtime-файла, новый полный build и прежние закреплённые helpers /
  worker resources проверены; dry-run prepare A/B и server PASS. Клиентские патчи
  диагностического стенда откачены по ledger до нового prepare/install.
- Два настоящих клиента вошли в battle `8865067871889357875`; log
  `native-fix04/gateway-stabfix04.stdout.log` содержит два SESSION_ACTIVE и
  два SHARED_READY. `create-receipt.json`, commands и отдельные launch/prepare
  receipts удерживаются в том же каталоге.
- OBSERVED: владелец начал ехать; один клиент получил чёрный экран, другой вернулся
  в ангар. Перед ручным выходом случился настоящий runtime-сбой
  `integrated drive logical deadline lag exceeds500ms; fail closed`. Причина
  задержки UNKNOWN; политика deadline не ослабляется в рамках STAB-01.
- VERIFIED по новому журналу: `SHARED_BATTLE_FAILED` line5003, возврат обеих сессий
  и reset мира lines5004–5006; старые workers завершены EOF/exit0/reaped. Оба
  Account reset были ACKed и включены; A завершил warm100/300/600 и вернулся в
  ангар, B был отвергнут на первом warm bundle891 (`shared/mod.rs:266`), затем
  закрылся по idle timeout. Процесс и A продолжали служебный обмен.
- VERIFIED из настоящего B packet5031: warm100(req226,rev1), warm300(req227,rev2,
  descriptor430/CRC1559578668), warm600(req228,rev0,0,0). SHA256 исходного пакета
  `877c4027e6de5b03ea93fb19e20a27c1b1330eeb41a494718fb0e7baa1801e6a`.
  Прежняя проверка hardcoded warm300rev3 неверна для SECONDARY r1-catalog2,
  чей уже опубликованный shop имеет rev2. Дальнейшие token-only пакеты892+
  отвергались из-за атомарно отклонённого891. Это отдельная подтверждённая ошибка,
  не неопределённый UI-сбой и не повод ослаблять ordered channel validation.
- Стенд остановлен по собственным PID/path/hash receipts `stop-warmfailure.json`;
  обе установки откачены по ledger. Исправление привязывает warm300 к неизменяемым
  уже загруженным shop bytes конкретной сессии. **Native-приёмка FAIL** на этом
  срезе; оба ручных выхода и повторный вход пока UNKNOWN, merge не выполнен.

## VERIFIED / OBSERVED — revision-bound возврат, fix05

- Runtime `25e07d3122d84a4e15cb82b17d9614fdafe80843`. Новый
  `Fixtures::shop_sync_revision()` читает положительный `rev` только из
  канонического ограниченного префикса собственных уже загруженных shop bytes.
  Входящий cache revision не определяет состояние сервера; произвольного
  object decoder и ослабления ordered channel нет.
- Прямой replay настоящего B payload153 проходит всю последовательность
  reset821 → enable890/ACK822 → warm891/ACK823 → heartbeat892, rx893, Account,
  прежние identity/state SHA/channel и join_requested=false. Встречные проверки
  primary3/secondary2 отвергают чужой revision атомарно, затем принимают свой.
  Прежние тесты ошибочно использовали primary fixture для обоих native slots;
  новый сценарий загружает настоящий secondary r1-catalog2.
- Полный suite и build: **847 passed, 0 failed, 5 ignored**, свежий каталог
  `local/build/server/gateway-p05b-stab01-fix05/`, executable SHA256
  `ad197e16002eb69bece75e50dbbc26fc1ebf394408ebaea646917ac3fc61607a`.
  Команда — `python -B -X utf8 server/build.py gateway --test --out
  local/build/server/gateway-p05b-stab01-fix05`. Layout/diff check PASS;
  независимый read-only review новых условий и regression tests без замечаний.
- Подготовлен и запущен новый стенд `native-fix05`, run `stabfix05`, binding SHA
  `37271ef9e5e0b7eec6e0ec5fbfccb68843f8e4a54b7a9f56792bf62a700a26b0`;
  321 runtime-файл, suite/build, helpers и assets закреплены. Все dry-runs PASS;
  новые ledgers prepare/install и launch receipts сохранены, старые не переиспользованы.
- UNKNOWN: owner/native-выход обоих и повторный бой на fix05. Предыдущий FAIL
  сохранён отдельно в `native-fix04/native-failure-summary.json` с реальным пакетом
  и ограниченными декодированными фактами (без keys/tokens/credentials).

## OBSERVED / VERIFIED — ручной возврат fix05 и блокеры повторной кнопки

- Владелец подтвердил: оба клиента в ангаре, повторный бой не начался. Лог
  `native-fix05` подтверждает native_leave сначала session2, потом session1,
  ACK/reset/warm100/300/600 и SHARED_HANGAR_RETURNED обоих. Между возвратами
  оставшийся actor1 продвинулся ещё на 90 логических тиков (9 секунд); затем
  оба workers завершены exit0/reaped, мир сброшен. Ошибок мира/SHARED_REJECT нет.
  Partial receipt — `native-fix05/native-manual-return-acceptance.json`.
- A: настоящий Flash click в client elapsed1098.1107 вызвал исходный fightClick /
  enqueue begin-return; затем blocked_external_captcha (line50545) запретил
  reCAPTCHA.getImageSource до внешнего HTTP. Исходный stats.battlesTillCaptcha=0
  требует CAPTCHA. Исследованный ordinary AccountPolicy передаёт service counter1;
  shared раньше публиковал raw state и возвращал no-change на warm100.
- B: ordinary adapter допускает только nativeID1, B имеет nativeID2 и исходный
  неполный экипаж. После возврата две battle_capability_disabled. Этот Account
  не должен изображать владельца готовой машины: лабораторный actor выдаётся
  сервером независимо от инвентаря. `native-fix05/reentry-failure-summary.json`.
- Предел evidence: native UDP capture достиг 48000 пакетов до позднего выхода;
  passive client profiler достиг 16 MiB. Поздние policy events записывались дальше.
  Отсутствие700 в обрезанном capture не выдаётся за доказательство; факты основаны
  на поздних policy events и отсутствии SHARED_QUEUE в полном серверном журнале.
- Проверен исходный #717 байткод: crew readiness блокирует FightButton.update
  через canPlayerDoAction; doAction проверяет presence. Сохраняемый decorated
  vehicleAmmoCheck/checkAmmoLevel при isReadyToFight=false достигает callback(True).
  SHA/code provenance семи оригинальных файлов —
  `local/evidence/20261015-stab01-01/native-reentry-policy/bytecode-provenance.json`.
- Минимальная коррекция: явный shared-lab режим существующего button adapter,
  connected Account ID1/2, синхронизированный cache, inv1 и точный MS-1 descriptor;
  только UI-доступность кнопки с пояснением временной серверной машины. Исходные
  fightClick, decorated enqueue, ammo/dialog path и CAPTCHA guard сохраняются.
  Готовность, экипаж, БК, инвентарь и ordinary-политика не подменяются.
- Shared initial/warm100 публикует полный state с уже исследованным counter1;
  PRIMARY использует прежнюю точную ordinary-проекцию, SECONDARY — независимый
  source SHA aa855586... и единственный byte605, outgoing SHA
  `d9b8e474f355b70ac2e2a4b3a29c44f78c4585c3eee623a9b4889d283f6aefb7`.
  Исходные фикстуры/БД не меняются. Независимое сравнение literal tree подтверждает
  только stats.battlesTillCaptcha0→1: `native-fix05/counter-policy-bindings.json`.
- Новый native-повтор с этими policy пока UNKNOWN. Возврат fix05 PASS не закрывает
  всю карточку: второй общий бой остаётся обязательным, merge не выполнен.

## VERIFIED — проверки lab-only повторного входа, fix06

- Runtime `13edf3bfe8f4681f720709f6195ec5ade5ec85d6`; gateway полный suite и build:
  **850 passed / 0 failed / 5 ignored**, `local/build/server/gateway-p05b-stab01-fix06/`.
  Executable SHA256 `02f7565fad12a6cdd916b103eaaff8337d41f06934ef66bfafa02faa831889f2`.
  Команда: `python -B -X utf8 server/build.py gateway --test --out
  local/build/server/gateway-p05b-stab01-fix06`. Layout PASS: 117 files / 22 relocations.
- Новые meaningful Rust-регрессии: full initial и full warm Account100 обоих
  настоящих профилей содержат только служебный counter delta; source fixture SHA
  неизменны, fake drive state не создаётся. Все 1106 однобайтных мутации secondary,
  усечение/дописка, подмена identity/профиля отвергаются.
- Клиент VERSION4: Python host 64 client-policy + 18 click-contract + 112
  acceptance/control tests PASS. CPython2.7.3: 64 выполнены, 3 ожидаемых host-only
  skip (61 PASS). Команды, stdout/stderr и результат —
  `native-reentry-policy/root-checks01/`. Первоначальный scoped FAIL одного
  VERSION3 assertion сохранён в subagent report; проверка обновлена до module.VERSION,
  полный применимый host прогон прошёл.
- Независимый read-only review client/server границ без замечаний. Фикстуры,
  их source hashes, DB, экипаж/БК/готовность не менялись; native700 ещё требует
  фактического повторного входа. Original внешняя CAPTCHA заблокирована как прежде.
- Свежий `native-fix06`, run `stabfix06`: binding SHA256
  `922e1578b0251bf02c6a05fbf0d493545efb43e428ea84ca718a3146a6c8b0e2`,
  322 tracked runtime-файла, все helper/build/asset pins проверены, dry-runs PASS.
  Новый client patch скомпилирован закреплённым Python2.7.3 и установлен в обе
  разрешённые копии по свежим ledger. Старый fix05 остановлен по receipts, обе
  установки откачены; оригинал не менялся. Новые процессы запущены.
- OBSERVED: владелец сначала сообщил, что оба вошли во второй общий бой, затем
  уточнил: один стрелял только прямо, второй висел на ожидании игроков.
  Загрузка карты не считается законченной готовностью; native-приёмка **FAIL**.
- VERIFIED: fix06 принял native700 обеих прежних сессий и создал второй мир
  `13855427602537674578`. A завершил READY (строка1310), B получил первый
  `SHARED_REJECT` на sequence204, `shared/mod.rs:407` (строка1311), затем gaps
  и idle timeout. Все3246 capture packets декодированы без ошибок. B204 —
  `packet-001947-base_client_to_server.bin`, SHA256
  `d55f115040b6d538fced5c1e111f0cc04d7e88c9d569b2ee347dd5b91726b344`,
  capture244.0124144s, body80 / application75, cumulative ACK271.
- VERIFIED: фактический application75 содержит точный собственный READY33,
  затем6 запросов областей152043563..568 (по7 байт). В первом бою оба клиента
  присылали обратный порядок: requests42 + READY33. Initial parser принимал
  только requests-prefix + READY-tail или голый READY33. Новый разбор проверяет
  точный owned READY33-prefix и весь хвост тем же bounded mixed parser в одной
  receive-транзакции; исходный `wire::ready` остаётся strict exact33.
  Packet metadata, raw application hex, decode hashes и timeline —
  `native-fix06/ready-failure-summary.json`.
- VERIFIED / UNKNOWN: A отправил92 разных aim intents; поздний snapshot tick1495
  имеет yaw−1.2608869 / pitch0.06873977, исходящие gunAnglesPacked меняются.
  Постоянная серверная блокировка наведения этим опровергается; источник ощущения
  «стрелял только прямо» ещё UNKNOWN. Раннее ожидание B — возможное объяснение,
  не установленная причина. Повторная проверка должна включать наведение обоих.
- VERIFIED: оба первых боя fix06 завершились отдельными deadline faults
  (`logical deadline lag exceeds500ms`), процесс сохранился, возвраты/reset
  отработали. Ручной выход обоих ранее подтверждён на fix05; полноценный повтор
  боя обоих на fix06 не подтверждён. После сохранения логов собственные процессы
  fix06 остановлены по receipts, обе установки откачены штатно. Merge закрыт.

## VERIFIED — fix07: READY-prefix и проверка точного B204

- Runtime `0574ab0c1df7a060bb6b3906febebf5e69d483d3`. Только shared parser и
  meaningful Rust-регрессии; client runtime с проверенного `13edf3b` не менялся.
  Strict owned READY33 теперь допускается перед native records, хвост полностью
  проверяется существующим parser. Общий512-byte bound стоит до обеих веток
  initial requests/READY. Собственное creation ACK, correction/fire gates и
  атомарная Session receive-транзакция сохранены. Read-only source review PASS.
- Полный gateway **854 passed / 0 failed / 5 ignored**, сборка PASS:
  `python -B -X utf8 server/build.py gateway --test --out
  local/build/server/gateway-p05b-stab01-fix07`.
  Executable SHA256 `46cc6540a04be40bd7475b828b2d0b19f09cfd0717fc34d46cbc2405cbf33683`.
  `python -B -X utf8 server/check_layout.py` — PASS117files / 22relocations;
  `git diff --check` PASS. Полные stdout/stderr/argv/result — в каталоге сборки.
- Четыре новые регрессии: точный native B75, оба slot, transport retry, fresh
  duplicate READY и новые area tails без нового binding; damaged/truncated/foreign
  READY, unknown/duplicate/future/truncated area и513B откатываются целиком;
  own creation без ACK отвергается; обе очередности резервируют binding и
  принимают ACK создания из того же frame при полном reliable window.
- Свежий `native-fix07`, run `stabfix07`, binding SHA256
  `96a1a8438a1330757699a703b8162d4c85c204b40fd73efa24bdc1003bec2842`:
  322 runtime pins, исходные6 helpers byte-identical, assets/pools/build pins и
  три dry-run PASS. Обе разрешённые копии подготовлены по новым ledger;
  сервер и A запущены. Native-приёмка нового fix **NOT_RUN_PENDING_OWNER**,
  прежний fix06 FAIL сохранён; merge закрыт до фактического движения/наведения
  обоих во втором бою и подтверждения возврата.

## OBSERVED / VERIFIED — инцидент локальных фикстур

- Вспомогательный managed worktree содержал junctions `local/server` и
  `local/vendor` к основному checkout. Root заархивировала worktree, не проверив
  эти ссылки. После архивации обнаружено отсутствие 70 файлов: 68 старых fixture
  files, bridge.json и client-digest.bin. Причинный механизм архиватора отдельно
  не воспроизводился — **UNKNOWN**, последовательность и junction targets записаны.
- Native-запуски были приостановлены; 64 файла восстановлены с совпадением
  независимо удержанного исходного SHA256. Шесть вспомогательных JSON в двух
  старых `r1` воспроизведены из закреплённых данных/генератора с прежними размерами,
  но независимый SHA прежнего файла **UNKNOWN**. Их статус явно отличается от
  точного восстановления. Все файлы текущего боевого профиля и все native
  manifests имеют совпавшие независимые исходные SHA.
- Финальный read-only аудит: все 91 159 файлов прежней инвентаризации server/vendor
  на месте, все размеры совпали; 70/70 восстановленных проверены по указанной
  provenance, 45/45 боевых pins PASS. `local/evidence/20261015-stab01-01/fixture-recovery/`
  содержит `INCIDENT.md`, `audit-final.json`, исходный missing-map, рецепты,
  exact candidates и отчёты переноса. Identity/content pins не ослаблялись.
- Неудачные полные прогоны сохранены: fix02 — 673 passed / 171 failed / 5 ignored
  на отсутствовавших ресурсах; fix03 во время частичного восстановления —
  843 passed / 1 failed / 5 ignored (`grant manifest missing`). Финальный fix04
  выполнялся после восстановления и прошёл полностью.

## Откат

Сохранить все evidence. Остановить только процессы из собственных receipts,
откатить battle install и namespace по новым ledgers. Для ангара A выполнить
новый prepare/install из сохранённых параметров прежнего `install01`; старый
ledger повторно не устанавливать. Код карточки откатывается revert её коммитов.
