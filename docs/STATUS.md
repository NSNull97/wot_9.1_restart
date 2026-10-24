# Состояние проекта

## Сейчас: CREW-ANY — native gate частично принят, ветка `codex/crew-any`

Код CREW-ANY и контракт экипажа v2 уже реализованы: пожизненная ёмкость 192 танкиста,
казарма 16, обратимая миграция v1↔v2, bridge/gateway v1/v2 и клиентские P04H–P04K/P09D
для каталога CAT-01 за явными флагами `--catalog-v1 --crew-any`. Автоматические проверки
и стендовая миграция PASS; native-прогон 2026-10-24 дал частичный PASS.

На официально подготовленном стенде `local/stands/crew-any-native-20261024-02` gateway
прошёл загрузку пяти профилей MS-1/ИС-7/Т-26/Т-34/Т-34-85, terrain/obstacle pins,
каталога, P08C late results, P06T armament и ammo-rack policy, затем привязал
`legacy091-profile13` на `127.0.0.1:20340`/`20341`; bridge поднялся на `127.0.0.1:3692`.
После остановки сервисов стенд оставлен чистым.

Свежий клиентский trace на копии исследовательского клиента подтвердил CPython 2.7.3
32-bit, `crew_any_policy` (`max_tankmen=192`, `server_authoritative=true`), оригинальный
`LoginView.onLogin`, `connection_callback=LOGGED_ON`, `native_connected=true` и полностью
загруженный native hangar (`hangar_space_loaded=true`, четыре видимые модели). В trace
наблюдались native crew и P09D ammunition callbacks; команды найма/перевода/увольнения
не выполнялись. Отдельный arena-entry smoke завершился с `compatibility_acceptance=false`
и картой 01_karelia, поэтому он не считается боевым profile13 acceptance.

Условие `hangar_limits_observed` в диагностическом control не выполнилось:
зафиксирован `diagnostic_condition_failed`; это отдельный FAIL диагностического сценария,
а не отказ native login/hangar. Дополнительный P09D сценарий также завершился
`p09d_scenario_error`: его baseline probe требует unskilled MS-1 crew, а v2-аккаунт стенда
уже содержит crew descriptor со skill `commander_tutor`; gateway не получил CMD108 и БД
не мутировалась. Поэтому P09D native command acceptance помечен `NOT_RUN` на этом аккаунте.

Полная приёмка CREW-ANY остаётся `PARTIAL / NOT_ACCEPTED`. Ветка не сливается до ручного
прогона T-26/другой машины CAT-01, native recruitment, перевода/увольнения, номера экипажа
>16 и настоящего profile13 боя. Основная квитанция native gate:
`local/stands/crew-any-native-20261024-02/native-gate-crew-any-20261024-receipt.json`.
Основной клиентский trace: `D:/WoT_9.1_Server/local/client-runtime-crew-native-a-02/native-211624-1792827183386.jsonl`.
Серверный лог: `local/stands/crew-any-native-20261024-02/gateway-20261024-123150.stdout.log`.
Дополнительные native traces: arena export `D:/WoT_9.1_Server/local/client-runtime-crew-native-a-02/native-240536-1792826920991.jsonl` (static Karelia, `compatibility_acceptance=false`) и P09D descriptor guard `D:/WoT_9.1_Server/local/client-runtime-crew-native-a-02/native-237808-1792827224777.jsonl`.

## Ранее: MAPS-01 + MAPS-02 приняты владельцем (2026-10-21, стенд `-09`, Малиновка)

Ветка `codex/integration-maps02-poles` (main `2f611ec` + MAPS-01 `27488a5` + MAPS-02
`e973862`). Native (владелец): бой на Малиновке — рельеф, деревья валятся; столбы
(`fallingAtoms`, каталог v8 `61dd9a23`) на малой скорости стоят (танк проходит сквозь,
как в 0.9.1 по маскам коллизии), на скорости сносятся — PASS. Ограничения: постройки
(`structures`) и часть заборов/фрагилов исключены с причинами; выстрел по столбу — отдельная
карточка (D2). Доработка: `full_test_stand.py map` принимает только v7 — на `-09` каталог
v8 подставлен вручную (`battle-profiles.v7-malinovka.json` — откат).

## Ранее: CAT-01 единый каталог — принят владельцем 2026-10-21 (стенд `-07`, Прохоровка, флаги каталога включены)

Каталог `config/catalog/catalog.v1.json` (SHA `a6bd44f4…`) собирается `tools/catalog_build.py`
из пинов клиента + `server_profiles.v1.json`; генерации Rust/Python/JS/Py2.7; допуск —
поле `battle_admission`. Потребители (шлюз `parse_frozen`, bridge `p06t-mixed`/`p04m-pool`,
Python реестр/`freeze_mixed`, клиент `map_drive_client`) читают каталог только за флагами,
прежние списки остаются ([research](research/CAT01_SINGLE_CATALOG.md)). Контракт и сторы в
обоих режимах PASS; канонический gate `gateway-integration-20261021-01` (CAT-01 + MAPS-01)
1700/0/5; native владелец: бой Т-34 против Т-34-85, покупка, окна MS-1/ИС-7 — как прежде (PASS).
Флаги по умолчанию выключены; включение по умолчанию — отдельное решение.

## MAPS-01 — конвейер карт (ветка `codex/maps-01-map-pipeline`, не слита)

Один экспортёр `tools/map_package.py` (пакет карты с SHA-256: рельеф, физика, снарядная
геометрия, арена, статический native-индекс разрушаемого), реестр карт
`server/contracts/map_registry.json` вместо `enum MapId` в gateway и физике. Карелия/
Прохоровка — побайтно прежние пины/буферы/каталог; Малиновка — новая карта реестра.
Отчёт по 44 картам и факты — [MAPS01](research/MAPS01_MAP_PIPELINE.md).
Native-бой на Малиновке — NOT_RUN (владелец); `fallingAtoms` — исключены (правило
падения UNKNOWN).

## MAPS-02 — fallingAtoms (ветка `codex/maps-02-falling-atoms`, не слита)

Одобрено владельцем 2026-10-21 (D1–D4), реализовано: триггеры столбов, каталог v8/v9,
sensor-тела в IPC7, доменное правило и публикация `fallenColumns` 0xa0. Факты и
доказательства — [MAPS02](research/MAPS02_FALLING_ATOMS.md), план —
[plans/MAPS02](plans/MAPS02_FALLING_ATOMS.md). Gateway gate в worktree 1423/281/5, FAIL-набор = базе MAPS-01;
native-проверка владельца (Прохоровка) — NOT_RUN.

## Ранее: BRIDGE-01 + LOGIN-01 приняты (2026-10-20)

Интеграционная ветка `codex/full-test-integration-20261020` (main `859452d` +
`codex/full-test-pending-login-queue` + `codex/full-test-bridge-latency`): канонический
gate `gateway-integration-20261020-01` **1691 PASS / 0 FAIL / 5 ignored** (composition02
больше не падает), exe `e28b646e…`. Стенд `-06`: владелец — оба клиента вошли
одновременно, операции ангара быстрее, бой работает (native PASS). Следующая карточка —
CAT-01 (ADR-002).

## Ранее: FULL-TEST (2026-10-19) — слит в main 2026-10-20

Слит по приёмке владельца (native PASS, стенд `-05`) с явным исключением: полный gate
1685 PASS / 1 FAIL — `p08b_restart_cas_composition02` падает только под нагрузкой из-за
медленного старта bridge (проходит отдельно). Исправление — карточка bridge
(постоянные воркеры, кеш каталога). Дальше: независимый вход аккаунтов (ветка
`codex/full-test-pending-login-queue`, в работе), затем экипаж/БК для любой машины.

**Main `ffce8cb` (STAB-01) не менялся с 15 октября.** Всё последующее — одна
неслитая цепочка карточек P08B → P08C → P05C → P07B → P06T → nightly polygon →
ram publication (213 коммитов над main). Каждая карточка требовала native-приёмки,
а каждый native-прогон обрывался первым fail-closed сбоем, поэтому ни одна не
слилась. Текущая ветка `codex/full-test-20261019` — интеграционная голова этой
цепочки; [ACTIVE_GATE](ACTIVE_GATE.md) — один общий сценарий.

Исправлено в этой карточке (канонический gate 1685 PASS / 1 FAIL под нагрузкой,
проходит отдельно 1/0; native NOT_RUN; [19.10](research/FULL_TEST_20261019.md),
[20.10](research/FULL_TEST_20261020.md)):

- сбросы боя: выстрел в упор, паузы цикла gateway, гонка тестов каденса;
- стенд, физика, мост и клиентский патч из одного checkout (раньше физика без
  `279be0c`, клиенты — из ночного клона);
- отрыв башни: у жертвы больше нет второй башни, у атакующего она не исчезает;
- поворот на ходу делит скорость с вращением корпуса;
- явная политика `test_lab.zero-economy.v1`: 100 слотов, все цены 0, премиум без
  исследования, снаряды пула ≥100; купленные Т-26/Т-34/Т-34-85 допускаются в бой
  (стенд `-04`: у A готов Т-34, у B Т-34-85; UI экипажа/БК для них не подключён);
- проектный звук лампы 6-го чувства (`gun_intuition`, не оригинал 0.9.1);
- сервис profile13 живёт 12 ч вместо 1 ч.

## Принято владельцем раньше (native)

- STAB-01: изоляция ошибок боя, возврат и повторный вход (в main).
- P08B/P08C: вход в бой из ангара профиля 13, отсчёт, захват, итоги, возврат.
- P05C: переворот, столкновения, захват; таран без вылета (19.10, после `aa0dfcc`).
- P07B: геометрия засвета, переворот МС-1 с сохранением видимости, визуальная лампа.

## Открыто

- Native FULL-TEST по [матрице](ACTIVE_GATE.md): движение, покупки и бой на
  купленных Т-26/Т-34/Т-34-85, экипаж/БК, отрыв башни, звук лампы `gun_intuition`.
- Не сделано: коллизия ствола оторванной башни (нет тела в Jolt); ёмкость экипажа
  >16 за всё время аккаунта (CHECK в SQLite); бой на купленных машинах вне пула
  5 типов (нет профилей физики/брони); разрушаемость всех объектов всех карт
  (Прохоровка 1038 из 3904, других карт нет в экспорте).
- Причина пауз главного цикла gateway — UNKNOWN (теперь каждая пишется
  `SHARED_DRIVE_LAG_RESYNC`).
- Python full suite (Python06): 12 FAIL / 45 ERROR — прежний долг.
- P10B (N игроков), NET-02 (два ПК), микролаг ~150 мс.
- Задержка bridge (ветка `codex/full-test-bridge-latency`, не слита, стенд не
  перезапущен): кэш производного каталога + memo `Catalog.sha256` + один `lstat`
  на компонент — воркер ~3× быстрее (≈3,1 → ≈1,05 с), ответы побайтно равны base;
  [план](plans/FULL_TEST_BRIDGE_LATENCY.md). Долгоживущие воркеры — после очереди входа.
- D: освобождено 44 ГБ удалением старых `local/build/*/target` (решение владельца 19.10).
