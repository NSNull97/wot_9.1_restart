# Текущие ворота: DOM-01 — Domain/Account service (2026-10-26)

Ветка `codex/dom-01-domain-service` на main `e61a385`. План и итог —
[DOM01_DOMAIN_SERVICE](plans/DOM01_DOMAIN_SERVICE.md), факты — [исследование](research/DOM01_DOMAIN_SERVICE.md).

| Проверка | Статус |
|---|---|
| Ответы Domain = байты воркера (сид, стенд -10 A, аккаунт 192) | PASS |
| bridge без/с Domain — одинаковые ответы (копия стенда) | PASS |
| FAIL-наборы gateway/web/Python против main в этой среде | без новых |
| Чтение < 300 мс | PASS (обычные аккаунты), FAIL (192/162) |
| Канонический gate в `D:/WoT_9.1_Server` | NOT_RUN |
| Native: ангарный сценарий + бой с Domain на стенде -10 | NOT_RUN (владелец) |

Порядок на стенде: остановить стенд → `full_test_stand.py domain --stand <stand>` → `domain.ps1 start` →
`services.ps1 start`; откат — остановка и `domain --disable`.

## Предыдущая карточка

# Текущие ворота: CREW-ANY — native T-26/profile13/capacity boundary gate 2026-10-25

Ветка `codex/crew-any`, база карточки — `4b46f7e`. План карточки —
[CREW_ANY](plans/CREW_ANY.md). Исходная копия клиента
`C:\WoT_0.9.1_RU_0717_original` не трогалась.

## Текущий clean native lifetime результат — 2026-10-25

Полная CREW-ANY lifetime-проверка закрыта двумя чистыми native-прогонами на одном
изолированном v2 B-аккаунте (`native_database_id=2`, T-26 inventory `4`). Перед
install13 остановлены client/services, удалены `game.sqlite-wal`/`game.sqlite-shm`,
восстановлен baseline `game.before-lifetime-controller-20261025.sqlite`, а весь
каталог `fixtures` стенда пересоздан. Исходная копия клиента
`C:\WoT_0.9.1_RU_0717_original` не трогалась.

- install13: native hires `#18..#192` — **175/175 PASS**, оригинальный
  `RecruitWindow.buyTankman`, raw CMD303 `[5,4609,3,0]`, gateway/internal
  `[3,4609,3,0]`, `result=0`; `DropdownMenu.selectedIndex` — 704 selector
  observations/actions/readbacks с matching original callbacks; 162 native
  dismissal cycles через `Barracks.openPersonalCase → PersonalCase.dismissTankman
  → GUI.handleKeyEvent(KEY_RETURN)`, все `CMD306 result=0`, unassigned=15.
- install16: native reject-only `#193` от финального состояния — raw request
  `[5,4609,3,0]`, две proxy-фазы `result=-10`, inventory extension отсутствует,
  `onCmdResponseExt resultID=-10`, ни `_update`, ни callback success; snapshot
  остался неизменным, `diagnostic_condition_complete` — PASS.
- SQLite после обоих прогонов: `next_native_id=193`, `free_left=0`,
  `configuration_revision=354`, active members=30, retired members=162.
- Evidence: `local/stands/crew-any-native-t26-lifetime-fix-20261025-01/evidence-native-lifetime-controller-20261025.json`.
  Trace hashes: install13 `c7fd0e5dd80d5b46252260809b7a2a4aada22e536469d00910f739afea2d0bde`,
  install16 `b0ca2281448456b939f5d566a4a9325997e60aca6e5f00ad8ae9441d31224e27` (полный SHA — в evidence).

### Матрица текущей приёмки

| Проверка | Статус | Доказательство |
|---|---|---|
| Bounded controller через настоящий `DropdownMenu.selectedIndex` | **PASS** | 704 actions/readbacks, original callbacks; policy caps selector=1024, RecruitWindow=256 |
| Native lifetime hires `#18..#192` | **PASS** | install13: 175 callbacks, raw `[5,4609,3,0]` → internal `[3,4609,3,0]`, 162 CMD306 receipts |
| Native capacity reject `#193` | **PASS** | install16: raw request, proxy `-10/-10`, `onCmdResponseExt=-10`, no update/inventory/state change |
| Полная карточка CREW-ANY | **PASS / ACCEPTED** | Combined clean native evidence + final SQLite invariants |

Ниже сохранена история предыдущих попыток и их блокеров; она не меняет текущий
статус этой карточки.

## История предыдущих запусков

Официальный стенд: `local/stands/crew-any-native-t26-20261024-03`. В нём включены
`legacy091-profile13`, CAT-01 для T-26, смешанный P06T боекомплект, P08B/P08C,
terrain/obstacle pins и карта `05_prohorovka`. Адреса стенда: login/base
`127.0.0.1:20340/20341`, identity bridge `127.0.0.1:3692`.

Проверен чистый v2-аккаунт B (`native_database_id=2`) с T-26 inventory `4`:
три экипажных места T-26 — unskilled 50%, навыки пустые, боекомплект
`AP=96/APCR=32/HE=32`. Для этого аккаунта через P04M bridge выполнена команда
найма в казарму: T-26 compact `4609`, роль driver `3`, revision `137 → 138`,
создан unassigned tankman `native_id=16`. Квитанция —
`evidence-crew-barracks-t26.json`.

После устранения клиентского блокера оба native-клиента вошли в один настоящий
profile13 бой на Прохоровке: B с inventory `4` и A с inventory `5`.
`SHARED_WORLD_STARTED` зафиксировал `sessions=2`, `actors=2`, затем пошли
`P05C_SCENE_READY`, `SHARED_ENTRY`, `SHARED_ANNOUNCED`, native snapshots и
результаты. Бой `4932769758126515471` завершился с `P06T_LOSS_RESULT_COMMITTED`
для обеих сторон; обе резервации имеют `status=finished`, результаты acked.

Модалка на приложенном скриншоте была клиентской «Требуется обновление».
Она останавливает `sr_interactive.py` до native login и даёт старый экран
`SERVER_NOT_READY`; это не отказ gateway. После закрытия модалки/чистого
перезапуска native-путь отработал.

В этом же запуске вручную пройден native-путь казармы для того же чистого
v2/profile13 аккаунта A (`native_database_id=1`). В оригинальном окне найма
выбраны СССР → лёгкие танки → T-26 → мехвод. Оригинальный callback отправил
настоящий `CMD303`; клиентский trace зафиксировал raw-layout
`[5,4609,3,0]`, `result=0`, новый `native_id=19` и descriptor с ролью
`driver`. Это не опечатка: profile13 `shop.bin` имеет revision **5**. На
границе gateway этот единственный profile13 revision нормализуется в
внутренний P04K revision **3**, поэтому серверный принятый layout —
`[3,4609,3,0]`. Подменять raw trace на тройку нельзя: это уже не настоящий
callback оригинального клиента. До команды было `configuration_revision=67`,
`free_left=174`; после — `68`, `173`.

Отдельно закрыта первая native capacity-граница на чистом v2 B-аккаунте
(`native_database_id=2`) в изолированной копии стенда
`local/stands/crew-any-native-t26-capacity-20261025-01`. До настоящего UI
callback было `next_native_id=17`, `free_left=176`,
`configuration_revision=16`, 16 записей; после настоящего CMD303 стало
`next_native_id=18`, `free_left=175`, `configuration_revision=17`, 17 записей.
Trace сохранил raw `[5,4609,3,0]`, `result=0`, `inventory_id=17`, а профиль13
подтвердил `snapshot_revision=144`, роль `driver`, `vehicle_inventory_id=null`.
На скриншоте native-казармы видно `17/17` танкистов и `14/16` свободных коек.
Это PASS именно для native boundary `#17`; полный native lifetime `18..192` и
отказ `#193` в этом запуске не выполнялись.

Попытка lifetime-прогона 2026-10-25 дошла до авторизованного native hangar и
казармы B-аккаунта, где фактический список прочитан как `total=17`,
`unassigned=2`. После обновления списка оригинальный виртуализированный
renderer-пул не стал готовым: trace повторяет
`p04k_barracks_renderers_pending` (`ready=false`), а `buy`-renderer остаётся
pending. Оригинальный RecruitWindow callback не открылся, поэтому ни
`p04k_barracks_submit`, ни native `CMD303 #18` до сервера не дошли. SQLite
осталась без изменений: `next_native_id=18`, `free_left=175`,
`configuration_revision=17`, 28 старых P09D-команд.

После tail-only исправления renderer lifecycle повторный bounded native-запуск
дошёл дальше: на свежей изолированной копии
`local/stands/crew-any-native-t26-lifetime-fix-20261025-01` авторизация,
native hangar, открытие казармы и `p04k_barracks_window_ready` прошли. Список
снова был `total=17`, `unassigned=2`; первый blocker снят. Дальше trace увидел
только один `p04k_native_selector` (`updateNationDropdown`): ввод селектора не
дошёл до оригинального `buyTankman`, поэтому `p04k_barracks_submit`, native
proxy и настоящий `CMD303 #18` отсутствуют. SQLite осталась
`next_native_id=18`, `free_left=175`, `configuration_revision=17`, P09D — 28;
native `#18..#192` и отдельный отказ `#193` по-прежнему **NOT_RUN**.

## Матрица приёмки

| Проверка | Статус | Доказательство / граница |
|---|---|---|
| Подготовка стенда и профиль13 bind | **PASS** | `stand-receipt.json`; свежий gateway startup и `BOUND` |
| Контракт экипажа v2 | **PASS** | stand `game.sqlite`, `p04m-pool-crew.v2` для обоих аккаунтов |
| Чистый v2 T-26 baseline с unskilled crew | **PASS** | `provision-271022a3-t26.json`; trace B, inventory `4`, empty skills |
| Recruitment/crew command для T-26 | **PASS (P04M bridge)** | `evidence-crew-barracks-t26.json`, revision `137→138`, tankman `16` |
| Native login → native hangar обоих аккаунтов | **PASS** | traces `native-213612-...jsonl`, `native-48492-...jsonl`; `SESSION_ACTIVE` |
| Native «В бой» с T-26/T-26 | **PASS** | gateway `P08B_QUEUE_PENDING` Join для inventory `4/5`, P06T reservations |
| Настоящий profile13 бой на Прохоровке | **PASS** | battle `4932769758126515471`, `SHARED_WORLD_STARTED`, scene/entry/snapshots |
| Экран боя и native arena callbacks | **PASS** | `evidence-profile13-t26-prohorovka-20261024/client-*-in-battle.png`; traces |
| Результаты, возврат и списание БК | **PASS** | `p06t_result` acked; reservations finished `141/198`; run-evidence JSON |
| Нативный UI CMD303 recruit в казарме | **PASS** | `evidence-native-ui-cmd303-t26-20261024.json`; raw `[5,4609,3,0]` → gateway/internal `[3,4609,3,0]`, `result=0`, `native_id=19`, revision `67→68` |
| Native UI CMD303: первый номер за старым пределом, `#17` | **PASS** | capacity proof: raw `[5,4609,3,0]`, proxy `result=0`, `inventory_id=17`; `next_native_id 17→18`, `free_left 176→175` |
| Native lifetime `#18..#192` и отказ `#193` | **NOT_RUN (UI BLOCKED)** | authenticated native run увидел `total=17/unassigned=2`, но `p04k_barracks_renderers_pending` оставил `ready=false`; `CMD303 #18` и проверка `#193` не отправлялись |
| Native lifetime retry после tail renderer fix | **NOT_RUN (SELECTOR INPUT BLOCKED)** | `p04k_barracks_window_ready=1`, но только `p04k_native_selector=1`; `buyTankman`, `CMD303 #18` и `#193` не достигнуты, DB unchanged |

Исторически (до install13/install16): этот старый запуск был partial; его итог superseded текущей clean native acceptance.

## Evidence

- Компактный отчёт запуска: `local/stands/crew-any-native-t26-20261024-03/evidence-profile13-t26-prohorovka-20261024/run-evidence.json`.
- Gateway: `local/stands/crew-any-native-t26-20261024-03/gateway-20261024-153006.stdout.log`.
- Native traces: `D:/WoT_9.1_Server/local/client-runtime-crew-t26-native-04/native-213612-1792837839997.jsonl` и `D:/WoT_9.1_Server/local/client-runtime-crew-t26-native-05/native-48492-1792837834912.jsonl`.
- Скриншоты боя: `local/stands/crew-any-native-t26-20261024-03/evidence-profile13-t26-prohorovka-20261024/`.
- Recruitment: `local/stands/crew-any-native-t26-20261024-03/evidence-crew-barracks-t26.json`.
- Native UI CMD303: `local/stands/crew-any-native-t26-20261024-03/evidence-native-ui-cmd303-t26-20261024.json`.
- Native UI trace: `D:/WoT_9.1_Server/local/client-runtime-crew-t26-native-20261024-07/native-152112-1792841051960.jsonl`.
- Native UI screenshots: `D:/WoT_9.1_Server/local/client-runtime-crew-t26-native-20261024-07/screenshots/`.
- Native capacity proof `#17`: `local/stands/crew-any-native-t26-capacity-20261025-01/evidence-native-capacity-id17-20261025.json`.
- Native capacity trace: `D:/WoT_9.1_Server/local/client-runtime-crew-capacity-native-20261025-01/native-227820-1792895232761.jsonl`.
- Native capacity screenshot: `D:/WoT_9.1_Server/local/client-runtime-crew-capacity-native-20261025-01/screenshots/screenshot_045.png`.
- Capacity DB до/после: `local/stands/crew-any-native-t26-capacity-20261025-01/game.before-native-ui-cmd303-20261024-155518.sqlite` и `game.sqlite`.
- Native lifetime blocked proof: `local/stands/crew-any-native-t26-lifetime-20261025-01/evidence-native-lifetime-blocked-20261025.json`.
- Native lifetime trace: `D:/WoT_9.1_Server/local/client-runtime-crew-lifetime-native-20261025-01/native-248848-1792897736453.jsonl`.
- Native lifetime retry blocked proof: `local/stands/crew-any-native-t26-lifetime-fix-20261025-01/evidence-native-lifetime-fix-blocked-20261025.json`.
- Native lifetime retry trace: `D:/WoT_9.1_Server/local/client-runtime-crew-lifetime-fix-native-20261025-01/native-96800-1792898583101.jsonl`.
- Резервные копии авторизации: `web.before-*.sqlite` в каталоге стенда; plaintext credentials в отчёт не включались.

## Команды и проверки этого шага

- `python -m py_compile client_patch/p04k_crew_ui.py` — PASS.
- `python -m unittest -v tests.test_crew_any_client tests.test_p04k_crew_ui` — **40/40 PASS**.
- Native-клиент `crew-t26-native-20261024-07` — вход, казарма, выбор T-26/мехвода,
  настоящий `CMD303`, native reply `result=0` — PASS.
- Isolated native capacity client — вход B, казарма, выбор T-26/мехвода,
  настоящий `CMD303 #17`, native reply `result=0` — PASS; `p04d_crew_meta`
  `next_native_id 17→18`, `free_left 176→175`, `configuration_revision 16→17`.
- Isolated native lifetime client — login/hangar PASS, Barracks list OBSERVED
  (`total=17`, `unassigned=2`), но lifetime UI **NOT_RUN**: 288 повторов
  `p04k_barracks_renderers_pending`, `ready=false`, `CMD303 #18` отсутствует.
- Isolated retry after tail-only renderer patch — `p04k_barracks_open=1`,
  `p04k_barracks_window_ready=1`, один `p04k_native_selector`, но
  `p04k_barracks_submit=0`, native request/proxy `0`; `CMD303 #18` и отказ
  `#193` **NOT_RUN**.
- `$b=(Resolve-Path 'local\\stands\\p09e-main-01\\source-bundle-05').Path; $env:P04D_TEST_BUNDLE=$b; $env:P04F_TEST_BUNDLE=$b; $env:P04G_TEST_BUNDLE=$b; $env:P04H_TEST_BUNDLE=$b; $env:P04I_TEST_BUNDLE=$b; $env:P04J_TEST_BUNDLE=$b; $env:P04K_TEST_BUNDLE=$b; $env:P09D_TEST_BUNDLE=$b; python -B -X utf8 -m unittest -v tests.test_p04m_pool_crew_v2.CrewV2Tests.test_v1_stays_capped_at_sixteen_and_v2_issues_seventeen_onwards` — **PASS** (1/1, synthetic writer boundary).
- `test_lifetime_192_is_exhausted_exactly_and_barracks_stay_sixteen` — **NOT_RUN**:
  bounded local attempt остановлен после длительного fixture-прогона; native
  lifetime loop этим не подменяется.
- SQLite до/после: `p04d_crew_meta` `67→68`, `free_left` `174→173`, запись
  `p04d_crew_member.native_id=19`, `p09d_native_command.result_code=0` — PASS.
- Targeted Rust `cargo test` для `ammo_session` — **NOT_RUN**: `cargo` не установлен
  на этом хосте; mapping revision подтверждён исходником и фактическим commit.

## Historical note

The older matrix and limitation text below records pre-fix attempts. It is superseded by the current clean native lifetime matrix at the top of this file; the active acceptance status is **PASS / ACCEPTED**.

## Ограничения и единственный следующий шаг

Этот прогон доказывает настоящий локальный native бой двух T-26 на Прохоровке,
native UI recruitment T-26 через оригинальный `CMD303` и переход первой
capacity-границы `16→17`. В native trace остаётся 44 не относящихся к найму
исключения `AttributeError: 'module' object has no attribute 'addChatMsg'`; они
не помешали proxy `result=0` и записи в SQLite. Полный CREW-ANY всё ещё не
принят: первый renderer blocker закрыт tail-only патчем и покрыт unit-тестами,
но retry остановился на native selector input до оригинального `buyTankman`.
Официальный T-26 стенд не трогался; оба lifetime-стенда остановлены, их DB не
изменилась. Откат — удалить только изолированные lifetime-копии после сохранения
evidence или восстановить их `game.sqlite` из pre-backup. Единственный следующий
шаг: довести selector chain до настоящего native `CMD303 #18`, затем повторить
`#18..#192`, native `CMD306` для освобождения 16 коек и отдельный отказ `#193`.
