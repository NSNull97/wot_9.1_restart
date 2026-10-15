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
  интеграция ещё менялась: полный current-head gate пока NOT_RUN.
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

Все относительные evidence выше находятся в `local/evidence/20261015-p08b-01/`.

## UNKNOWN — обязательная оставшаяся проверка

- Native/UI обоих настоящих профилей13, выбор машины, отказ/отмена очереди,
  расход после ручного возврата, повторный бой и перезапуск с резервом NOT_RUN.
- Счётчики native full sync после настоящей ангарной мутации и цикла Avatar
  проверяются live; синтетические кадры/самосогласованный codec этого не доказывают.
- Полный current-head gateway gate и source/artifact binding свежего стенда
  ещё нужны; при FAIL/NOT_RUN карточка остаётся в ветке.

Оригинал клиента и рабочая БД при исследовании не меняются. Существенные решения
будут внесены сюда по конкретному коду/трассам; предложенная архитектура не
объявляется исследованным клиентским контрактом.
