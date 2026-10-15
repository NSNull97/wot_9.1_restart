# P08B — профиль13, выбранная машина и общий native-бой

Дата: 2026-10-15. Статус: IMPLEMENTATION_IN_PROGRESS, native приёмка NOT_RUN.
Ветка `codex/p08b-profile13-battle`, база main
`ffce8cb660e9e6af6872aa4a5de444f461bc73fe`.
План — `docs/plans/P08B.md`; evidence — `local/evidence/20261015-p08b-01/`.

## VERIFIED — предпроверка и границы

- `git status --short --branch`: чистая STAB-ветка до начала; main/origin/main и
  `git ls-remote origin refs/heads/main` совпали с ffce8cb. Новая ветка создана
  именно от main, а не от документационного head403804d STAB.
- Прочитаны ACTIVE_GATE, IMPLEMENTATION_ORDER п.2, STATUS, DEV_NOTES;
  native path рассматривается через P02_MAP_DRIVE/P02_MANUAL_BATTLE_BUTTON,
  текущую реализацию STAB и реальный writer профиля13.
- `battle/profile4_adapter.rs::validate_authenticated` закрепляет source SHA,
  MS-1 inv1/turret5891/gun5892/AP2570, профиль4/snapshot4 и экипаж/20снарядов.
  Это доменная проверка frozen fixture, не admission для реального профиля13.
- Существующий game_vehicle(state,battle_id) — потенциальная основа резерва;
  `NativeAmmoStore.reserve_vehicle` возвращает BATTLE_UNSUPPORTED. Обход через
  базовый writer может рассогласовать projections и не допускается.

## VERIFIED — контракт и реализация

- Original #717 native700 — `doCmdInt3`, request202, выбранный положительный
  `g_currentVehicle.invID`, gameplay mask с битом RANDOMS, map0. Queue502
  передаёт queueType1, а не inventory ID. Исходная Flash-кнопка передаёт map0.0;
  клиентский адаптер нормализует только это измеренное значение в int0.
- `Account.onEnqueueFailure(queueType,errorCode,errorStr)` и исходная
  RandomQueueFunctional снимают processing и показывают локализованную причину.
  Source-order индекс20 даёт wire0x4f; тот же расчёт воспроизводит принятые
  onEnqueued0x3f/onDequeued0x40/onCmdResponseExt0x4d. JOIN_FAILURE:
  ACCOUNT_LOCK3, WRONG_VEHICLE4, WRONG_ARENA_STATE8. Нативная доставка нового
  отказа пока NOT_RUN; статическая совместимость не объявляется live-приёмкой.
- Новый `tools/p08b_battle_store.py` — тот же SQLite-писатель с отдельной
  версионируемой P08B-схемой, run fencing, атомарным reserve/finish и ledger
  повторов. Старые frozen profile4/P09E source gates не ослаблены.
- Допускаются точные stock MS-1/ИС-7, собственный назначенный полный экипаж,
  полное HP и только реально загруженные AP: MS-1 до96, ИС-7 до30. APCR/HE,
  иной набор модулей, пустой БК/экипаж явно отклоняются. Никаких подставных
  inventory IDs, экипажа или пополнения при повторном attach.
- `p08b-battle.json` связывает owner/nativeID/revision/policy/state SHA и
  явные capability rows. Обычный P09E остаётся с battle_admission=false;
  старые runtime_supported flags каталога не превращаются в разрешение боя.
- Клиентский режим `--enable-profile13-battle` отделён от старых map-drive и
  shared-lab, требует весь профиль13 и сохраняет исходные FightButton callbacks.
  Серверный режим `legacy091-profile13` требует собственный manifest и flag.
- Gateway ставит только чистое намерение в клонируемой receive-транзакции.
  Внешний writer запускается после commit всего кадра, включая piggybacks.
  onEnqueued/Avatar разрешаются после durable reserve; terminal AP/HP снимаются
  до detach/reset, свежая owner projection загружается до возврата Account.
- У Account два разных курсора: durable revision и native wire revision.
  Reserve/cancel сохраняет живой native cursor; настоящая новая Account entity
  получает wire1 и новую command epoch. Периодический refresh в очереди допустим,
  ангарная мутация получает штатный отказ без обращения к БД.
- Original AccountRepository переживает Avatar: новый Account получает тот же
  syncData, поэтому warm100 несёт прежнюю native revision N. Это подтверждено
  статическим CPython2.7.3 disassembly без исполнения оригинального кода:
  `warm-account-sync-source.json`, SHA
  `574a2b4662efb89d6403fcdeb6771a4f24833d965432adf526565dc36be4a1b0`.
  RES_STREAM проходит отдельную ветку SyncController; full state без prevRev
  присваивает data.rev1, после чего следующий CMD100 использует1. Gateway
  хранит exact прежнюю native revision до rebind и проверяет её на warm100.

## Решения P08B, а не исторические факты клиента

- Явная policy `test_lab.profile13-stock-ap-free-repair.v1`, SHA256
  `cddd7d8cfabe8a4df5543fdcef14dd5518c36bc8bce431cfb502a5c72903ccda`:
  actual AP consumption; terminal HP/destroyed сохраняются в журнале;
  мгновенный бесплатный ремонт до source MAX; credits0/XP0. Экономика и UI
  итогов не реализуются этой карточкой.
- Gateway crash до terminal commit: новый run атомарно отменяет старый резерв,
  возвращает исходный AP и чинит машину; неизвестные terminal HP/destroyed=null.
  Уже committed итоги сохраняются exactly-once. Per-shot durability отсутствует.
- До P05C бой однородный и на двух клиентов. Оба существующих pinned профиля
  загружаются до открытия портов; первый подтверждённый reserve выбирает тип
  мира. Несовместимая вторая машина получает отказ и возврат резерва.
- Для настоящего второго website owner создан новый явный
  `P08B-owned-source.v1`: A-экспорты остаются доказательством A и используются
  только как определения #717. Чистые builders создают собственные B IDs,
  затем штатная цепочка 4→13. Это новый test_lab grant, не якобы native B export.
  B-only import проверяет DDL/catalog/policy, все owner rows, nativeID collision,
  неизменность A/global rows и rollback; живые базы при исследовании не менялись.

## Выполненные проверки до native стенда

- Writer18/18 PASS, zero skip: `writer-tests-04-full.log`.
- Новый Web7/7 PASS, настоящий HTTP→Python→SQLite, без unsafe pickle:
  `web-tests-02.log`. Резерв/все7 garage endpoints/lock1/расход20→17/HP0 и
  free repair/bridge restart/new-run refund/wrong owner/token/u64/8 DTO vectors.
- Старая Web-регрессия7 PASS и game-adapter11/11 PASS:
  `web-old-regression-01.log`, `web-game-adapter-02.log`. Старый исторический
  descriptor path первого прогона отсутствует; test-only env задаёт проверенный
  bundle blob, SHA18e6c2babfc205ce80fa24c2c9f23385a1731233c4d504be369638485652d6f2.
- Host client/control311 PASS, CPython2.7.3 79 PASS/3 host-only skips, compile
  трёх модулей PASS: `client-checks03/result.json`.
- Owner/onboard9 PASS; настоящая A13 backup + B import, reopen/idempotency,
  policy/schema/source/nativeID/changed-owner/open-run negatives. В свежем
  `local/stands/p08b-profile13-01/prepare-receipt.json` A account digest до/после
  `d61e38c2f36b7ef8338d274cebc1f70faf0732c13c84460551e22b72b6664a61`.
- Targeted gateway23 PASS / zero ignored, isolated build PASS:
  `local/build/server/gateway-p08b-integration02/result.json`. После него
  интеграция после него менялась; актуальный полный gate указан ниже.
- Шесть synthetic Session/transport flow tests PASS: полный piggyback rollback,
  pure JOIN до writer ACK, CANCEL во время admission, retired terminal receipt,
  bounded late Avatar drain и атомарный delivery. Реальные DTO writer закреплены
  SHA; синтетические Session inputs не выдаются за native delivery.
  `local/build/server/gateway-p08b-flow02/result.json`.
- Fresh configured HTTP preflight двух настоящих владельцев PASS, MS-1 admission
  true у A revision92 и B revision14: `local/stands/p08b-profile13-01/bridge-preflight.json`.
  Это проверка HTTP/projection, native остаётся NOT_RUN.
- Повтор owner+writer с явно заданным bundle:28 PASS/0SKIP,
  `owner-checks02/result.json`; первоначальный missing-env skip сохранён в01.
- Полный gateway890 PASS/5 штатных ignored, isolated build PASS на runtime
  `0834fee027af83044c13db353c9bfcb1d4a7fdd7`:
  `local/build/server/gateway-p08b-full02/result.json`, exe SHA256
  `b6ccb28c531a490198b86f61a8c87ff8eab5db95748b78b35f0b374e2e941f1d`.
  Первый full01:889 PASS/1 FAIL из-за старого теста, который считал shot60 MS-1
  недопустимым при временном20 БК. Тест исправлен для настоящего max96 БК:
  сохраняет разные native FX и пределы history192/60; production не менялся.
- Восемь flow tests PASS, включая preserved warm4→full1 и новый battle ID
  после завершения последнего queued reservation: `gateway-p08b-flow04`.
  Writer запрещает повторный admission того же owner/battle; пустая завершённая
  очередь получает новую генерацию. Пока peer держит старый резерв, новый JOIN
  получает явный BATTLE_BUSY. Тренировочная комната/динамический матчмейкинг P10B
  этим не реализуются.
- Автоматический gate со ссылками на все проверки: `automatic-gate.json`;
  native source/artifact/config binding: `local/stands/p08b-profile13-01/binding.json`.

Все относительные evidence выше находятся в `local/evidence/20261015-p08b-01/`.

## UNKNOWN — обязательная оставшаяся проверка

Первый native P08B запуск A — FAIL_CLIENT_GATE до какого-либо reserve. Ангар
дошёл до original FightButton.disable; `_bool(item.isCrewFull)` выбросил
ValueError и сорвал LobbyView. У #717 это property с результатом
`(None not in mapped_crew) and len(mapped_crew)`: полный MS-1 возвращает int2,
ИС-7 int5, неполный False/0. Нельзя считать её boolean oracle. Исправлено в
map_drive_client VERSION6 на точное сравнение count==source seats с проверкой
типов; настоящие ownership/crew/AP/readiness checks сохранены.
Receipt `native-first-result.json`: reserve0, A дошёл до native hangar,
штатно завершился; gateway/bridge остановлены по своим receipts, оба client
install01 откатились своими ledgers. Повтор — свежий `native-fix01/` под стендом.
Клиентский fix:314 host PASS, CPython2.7.3 81 PASS/4 expected host-only SKIP,
compile3 PASS: `client-fix08-checks01/result.json`. Gateway code SHA не менялся;
full02 890/5 относится к тому же серверному исходнику, новый native gate впереди.

Повтор native-fix01 с VERSION6: A полностью загрузил настоящий ангар MS-1
(gui/cache/model ready, connected, no waiting); B получил LOGIN_REJECTED_NO_LOGINAPP_RESPONSE.
Это не ошибка B ownership: gateway подтвердил UUID/nativeID2 и создал pending
session, но не увидел BaseApp. Capture показал начальный request47999 в
t120.9227894, retries до48007 в t128.922203, поздний success в t129.0738594
ошибочно адресован начальному47999. A авторизовался за7.671с, B за8.151с —
его первый request уже истёк. Safe analysis/pins:
`local/stands/p08b-profile13-01/native-fix01/auth-request-id-analysis.json`.
В `87e2e8b` AuthJob сохраняет ID последнего строго совпадающего pending retry;
credentials/digest/key/nonce/peer/worker result не изменяются. Обе native ветки
используют общий метод. Negative и actual RSA/redirect wire tests проверяют,
что чужой request ID не подменяет ожидающий auth. Native повтор — `native-fix02`;
оба старых клиента/сервиса остановлены по receipts, оба install откатились,
резервов в этих попытках0. Полный current-head gate поправки:
891 PASS/5 ignored, build PASS, `local/build/server/gateway-p08b-full03/result.json`;
exe SHA613d84f46dc752369648eef5da713a7ea0836f8f8b4ca3b6d94bc57251d59a75.

Native-fix02: оба настоящих profile13 Account загрузились, родные CMD700
сделали два owned reserve, общий world и два Avatar READY. В бою сервер реально
принял по2 выстрела (20→18), затем два manual_leave. Оба terminal результата
committed: A revision97, B18, remaining_ap18/consumed2/HP90, free repair90,
credits0/XP0; world faults0. Это VERIFIED серверной трассой и SQLite, но вся
native приёмка FAIL: владелец сообщил два чёрных экрана при возврате.
Первый reject — shared warm Shop300; у обоих настоящий cache tuple
`(rev5,size23107,CRC248225827)` превосходит унаследованный lab limit16448.
`native-fix02/native-result.json` сохраняет весь outcome, safe packet analysis —
`warm-shop-cursor-analysis.json` (только sync поля, без tokens/keys/credentials).
В `5c08ef5` warm parser использует бюджет загруженной Fixtures: research32832,
legacy16448, точную shop revision и a0→b0. Новые regression cases проверяют
полный warm/ACK/stream24000/повтор, rollback ошибок и сохранение legacy deny.
Старые процессы остановлены по receipts, install откатились. Свежий `native-fix03`
использует ту же test DB с сохранёнными результатами: ожидаемый начальный БК18
у обоих, активных резервов0. Full current-head и native повтор этой поправки
full04 завершён:893 PASS/5 ignored, build PASS на `5c08ef5`;
exe SHA96d10ba2eb3266cb5fbaa9335a83d97d4f07f192cef344007f0812ed15509445.
Native повтор впереди; успешный READY/SQL не выдаётся за успешный возврат UI.

- Native/UI обоих настоящих профилей13, выбор машины, отказ/отмена очереди,
  расход после ручного возврата, повторный бой и перезапуск с резервом NOT_RUN.
- Счётчики native full sync после настоящей ангарной мутации и цикла Avatar
  проверяются live; синтетические кадры/самосогласованный codec этого не доказывают.
- Native owner gate обязателен; при FAIL/NOT_RUN карточка остаётся в ветке.

Оригинал клиента и рабочая БД при исследовании не меняются. Существенные решения
будут внесены сюда по конкретному коду/трассам; предложенная архитектура не
объявляется исследованным клиентским контрактом.
