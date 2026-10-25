# Состояние проекта

## Текущий статус: CREW-ANY native lifetime gate принят — 2026-10-25

Карточка `codex/crew-any` закрыта на clean native evidence. Изолированный B/v2
T-26 стенд запускался после удаления WAL/SHM и пересоздания fixtures. install13
доказал 175 настоящих CMD303 hires `#18..#192` и 162 настоящих original CMD306
dismissal’а; install16 отдельно доказал отказ `#193` с raw `[5,4609,3,0]`,
proxy/onCmdResponseExt `-10`, без `_update`, inventory extension или изменения
snapshot. Финальная SQLite-проверка: `next_native_id=193`, `free_left=0`,
`configuration_revision=354`, active=30, retired=162.

Evidence: `local/stands/crew-any-native-t26-lifetime-fix-20261025-01/evidence-native-lifetime-controller-20261025.json`.
Проверки: targeted unittest 49/49 PASS, py_compile PASS, git diff --check PASS.
Патчи bounded guard’ов конечны: input=4096, selector=1024, recruit windows=256,
dismissal windows=256, lifetime deadline=7200s. Старые install07–12 FAIL/partial
сохранены в trace/history и не подменяют clean acceptance.

**Приёмка карточки: PASS / ACCEPTED.**

Отдельная bounded-диагностика update-gate на 2026-10-25 завершена частично:
свежая research-copy через loopback `127.0.0.1:20340` дошла до обычного
`LoginView`, update/modal-событий не было, install rollback и остановка стенда —
PASS. Login-submit не выполнялся, поэтому raw reply/auth reason — `NOT_RUN`, а
не PASS. Evidence:
`local/evidence/update-gate-bounded-20261025-02/update-gate-evidence.json`.
Старый `tools/wg_probe` остаётся запрещённым backend для новых запусков: его
toolkit-путь формирует `74` (`UPDATER_NOT_READY`), тогда как актуальный gateway
для #717 отправляет `73` (`SERVER_NOT_READY`).

Один bounded account-run выполнен 2026-10-25 на той же чистой копии после
ручного ввода тестовой пары в native LoginView. Raw login reply был пойман в
loopback capture: `packet[11]=67` (`INVALID_PASSWORD`), 35 байт; callback клиента
зафиксировал `LOGIN_REJECTED_INVALID_PASSWORD`. Gateway успел записать
`SHARED_LOGIN_STARTED request_id=86428 identity_jobs=1`; финальная строка
`AUTH_REJECT` не успела попасть в stdout до controlled stop, поэтому причина
помечена как `INFERRED_FROM_SOURCE_AND_RAW_REPLY`: ветка `session.rs` с
`auth_result=Ok(None)` отправляет code 67 и означает отказ identity-проверки.
Коды `73/74` в этом единственном прогоне не наблюдались. Evidence:
`local/evidence/update-gate-bounded-20261025-03/update-gate-account-evidence.json`;
raw reply SHA256 `9df31244c3397a43a79d645b221fce617ac0dc2942edb894960c23dc39d0bce5`;
trace SHA256 `7d2e1961b31e05dfaa6003c6137354a21224be04b5b5b68626c8ee39eea0ca1e`.

Повтор с явно выбранным локальным account label `sr.ascii.f4d1e9` дал тот же
результат: raw `packet[11]=67 (INVALID_PASSWORD)`, а callback клиента —
`LOGIN_REJECTED_INVALID_PASSWORD`. `73 SERVER_NOT_READY` и `74
UPDATER_NOT_READY` снова не наблюдались. Gateway успел записать только
`SHARED_LOGIN_STARTED request_id=46912 identity_jobs=1`; финальный `AUTH_REJECT`
не был flushed до controlled stop. Поэтому причина gateway классифицирована как
`INFERRED`: ветка `session.rs` сводит `auth_result=Ok(None)` к коду `67`, а
различить lookup неизвестного аккаунта и несовпадение пароля этим контрактом
нельзя. Клиент, сервисы и install ledger после прогона восстановлены.

Evidence:
`local/evidence/update-gate-bounded-20261025-04/update-gate-account-evidence.json`;
raw reply SHA256 `30bac841b65ac369133798066e193fdc54acbfd9fc21d4ff5ad27765c78ba65e`;
trace SHA256 `2748bb57415c1b71b9cc01e3d2f0856c6b31b9d2b50dd79390a70407e6fd3cf8`.

Read-only identity audit после этого прогона подтвердил: в `web.sqlite` есть
единственная каноническая запись `sr.ascii.f4d1e9@example.test`, её scrypt
record структурно валиден, а game profile привязан к `native_database_id=1`.
Однако в семи локальных snapshot’ах цепочки обнаружены пять разных fingerprint’ов
password hash; текущая запись обновлена `2026-10-24 16:00:16` по
Asia/Yekaterinburg, а `last_login_at` остался от `2026-10-05`. Известный локальный
control-artifact `D:/WoT_9.1_Server/local/client-controls/crew-t26-control-20261024-06.json`
тоже не совпадает с текущим digest (кандидат проверен только в памяти, plaintext
не выводился). Значит, причина `67` теперь локализована до credential drift /
mismatch с текущим hash; пропавшей identity-записи или неправильной profile-bind
нет. Парольный plaintext неизвестен без ввода владельца, клиент повторно не
запускался.

Identity evidence: `local/evidence/update-gate-bounded-20261025-04/identity-record-audit.json`;
status `PASS_RECORD_PRESENT_HASH_FORMAT_VALID_PROFILE_BINDING_VALID_PASSWORD_MATCH_NOT_TESTED`.

Единственный следующий шаг: выполнить обычный review/merge карточки по
`docs/07_CODEX_WORKFLOW.md`, затем открыть следующую карточку для оставшихся
не native lifetime задач.

## История статуса до clean lifetime gate

## Сейчас: CREW-ANY — T-26/profile13 native slice принят, full card частично открыта

Карточка живёт в ветке `codex/crew-any`. На стенде
`local/stands/crew-any-native-t26-20261024-03` выполнен запрошенный native-шаг:
чистый v2 B-аккаунт с T-26 inventory `4`, тремя unskilled 50% членами экипажа,
пустыми навыками и AP/APCR/HE `96/32/32`; затем P04M recruitment в казарму создал
unassigned tankman `native_id=16` (revision `137→138`). Доказательство команды —
`local/stands/crew-any-native-t26-20261024-03/evidence-crew-barracks-t26.json`.

Оба native-клиента вошли в один настоящий profile13 бой на `05_prohorovka`:
B inventory `4` и A inventory `5`. Gateway записал `P08B_QUEUE_PENDING` Join,
`P06T_LOSS_RESERVED`, `SHARED_WORLD_STARTED` (`sessions=2`, `actors=2`),
`P05C_SCENE_READY`, `SHARED_ENTRY`, `SHARED_ANNOUNCED`, native snapshots и
подтверждённые результаты. Бой `4932769758126515471` завершился с двумя
`p06t_result.acked=1`; резервации закончены на ревизиях `141` и `198`.
Оба клиента оставили полноценные native traces с `native_fight_call`,
`arena_bootstrap`, `shared_native_snapshot`, `native_avatar_call` и
`onLeaveWorld`. Скриншоты countdown/боя/результата лежат в
`local/stands/crew-any-native-t26-20261024-03/evidence-profile13-t26-prohorovka-20261024/`.

Причина сообщения «сервер не готов» на приложенном скриншоте — клиентская
модалка «Требуется обновление»: она блокирует `sr_interactive.py` до native login.
После её закрытия и чистого перезапуска сервер принял обе сессии; это не новый
дефект gateway. Авторизационные изменения стенда делались только с резервными
копиями `web.before-*.sqlite`; секреты в доказательства не записывались.

В этом запуске вручную пройден native UI найм T-26. Оригинальный client callback
зафиксирован как `CMD303` с raw-layout `[5,4609,3,0]`: profile13 native shop
действительно публикует revision 5. Gateway нормализует его в принятый внутренний
P04K layout `[3,4609,3,0]`; это подтверждено исходником нормализации и успешным
ledger/SQLite commit. Новый tankman — `native_id=19`, роль `driver`,
`result_code=0`, конфигурационная ревизия экипажа `67→68`, бесплатный остаток
`174→173`. Доказательство —
`local/stands/crew-any-native-t26-20261024-03/evidence-native-ui-cmd303-t26-20261024.json`.

Следом выполнена отдельная capacity-проверка в свежей копии стенда
`local/stands/crew-any-native-t26-capacity-20261025-01` на том же чистом v2 B-аккаунте.
Настоящий native CMD303 из окна Казармы нанял 17-го tankman для T-26: raw
`[5,4609,3,0]`, роль `driver`, `result=0`, `inventory_id=17`, ledger revision
`143→144` и `snapshot_revision=144`. В SQLite `p04d_crew_meta` зафиксировано
`next_native_id 17→18`,
`free_left 176→175`, `configuration_revision 16→17`; после операции профиль13
содержит 17 членов. Evidence —
`local/stands/crew-any-native-t26-capacity-20261025-01/evidence-native-capacity-id17-20261025.json`,
trace и screenshot указаны в [ACTIVE_GATE](ACTIVE_GATE.md).

Исторически до clean lifetime gate: T-26/profile13 slice и boundary `#17` были PASS,
а full card оставалась PARTIAL / NOT_ACCEPTED: native boundary `#17` PASS, но native lifetime
`#18..#192` и отказ `#193` ещё **NOT_RUN**. Automated P04K evidence guard
по-прежнему намеренно MS-1/ИС-7-only. Подробная матрица и единственный
следующий шаг — в [ACTIVE_GATE](ACTIVE_GATE.md).

Попытка lifetime-прогона после этого boundary авторизовалась как B
(`native_database_id=2`) и прочитала native Казарму (`total=17`,
`unassigned=2`). После обновления списка client patch зафиксировал повторяющийся
`p04k_barracks_renderers_pending` с `ready=false`: виртуализированный original
renderer-пул не довёл `buy` tile до готового состояния. Поэтому native
RecruitWindow не открылся, `CMD303 #18` не был отправлен, а SQLite осталась на
`next_native_id=18/free_left=175/configuration_revision=17`; в P09D осталось 28
старых команд. Proof —
`local/stands/crew-any-native-t26-lifetime-20261025-01/evidence-native-lifetime-blocked-20261025.json`.
Это технический UI blocker для следующего шага, а не серверный отказ capacity.

После tail-only renderer fix повторный bounded native-запуск на
`local/stands/crew-any-native-t26-lifetime-fix-20261025-01` подтвердил
`p04k_barracks_open` и `p04k_barracks_window_ready` для того же списка
`total=17/unassigned=2`. Renderer blocker снят, но native selector цепочка
остановилась после одного `updateNationDropdown`: оригинальный `buyTankman`
callback не вызван, `CMD303 #18` не ушёл. Доказательство —
`local/stands/crew-any-native-t26-lifetime-fix-20261025-01/evidence-native-lifetime-fix-blocked-20261025.json`, trace
`D:/WoT_9.1_Server/local/client-runtime-crew-lifetime-fix-native-20261025-01/native-96800-1792898583101.jsonl`.
DB не изменилась (`next_native_id=18/free_left=175/configuration_revision=17`),
поэтому `#18..#192` и отказ `#193` остаются **NOT_RUN**. Статус full card:
**PARTIAL / NOT_ACCEPTED**; серверный capacity отказ не наблюдался.

## Historical note

The earlier PARTIAL / NOT_ACCEPTED wording below predates the clean install13/install16 native evidence. The active status is the accepted lifetime gate at the top of this file.

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
