# Ночные изменения: указатель файлов за 2026-10-05

Этот список помогает читать код после ночной доводки ангара. Он получен сравнением SHA-256 с фактическим снимком перед карточкой экипажа C, а не по `git diff`. Новым считается файл, которого не было в этом снимке; изменённым — файл с другим содержимым.

**Срез: 2026-10-05 07:28:55 +05:00 (02:28:55 UTC).** Проверены 317 authored файлов: **49 новых + 8 изменённых файлов кода/тестов**, **15 новых + 5 изменённых документов**, 240 файлов без изменений. Удалённых файлов — **0**. Этот индекс создан после среза и намеренно не входит в собственный manifest. Позднейшие редакционные правки утреннего отчёта, STATUS и `.gitignore` этим снимком не предвосхищаются.

Исходный `C/baseline-01/project-before.json` содержит ровно 253 записи. Для каждой проверены размер и SHA-256 соответствующего содержимого `project-before.zip`. Каталоги клиентов, `local/`, БД, credentials, ключи, дампы, зависимости, кэши, результаты сборки и compiled client modules в перечень authored sources не включены.

Для первого знакомства удобно читать [web/src/ms1-crew.mjs](<D:/WoT_9.1_Server/web/src/ms1-crew.mjs>) → [tools/ms1_crew_state.py](<D:/WoT_9.1_Server/tools/ms1_crew_state.py>) → [client_patch/ms1_crew_probe.py](<D:/WoT_9.1_Server/client_patch/ms1_crew_probe.py>), затем [tools/wg_probe/src/gateway091.rs](<D:/WoT_9.1_Server/tools/wg_probe/src/gateway091.rs>). Сценарии ниже показывают, что запускалось через родной GUI API; отдельные `verify_*` разбирают сохранённые доказательства. Наличие тестового файла само по себе не означает PASS: статусы запусков и ограничения находятся в отчётах карточек.

| Группа | Новые | Изменённые |
|---|---:|---:|
| Backend Rust | 0 | 2 |
| Web и bridge | 1 | 2 |
| Клиентские authored adapters/диагностика | 8 | 3 |
| Инструменты и verifiers | 12 | 1 |
| Отдельные файлы тестов | 28 | 0 |

Тесты Rust внутри двух изменённых `.rs` учитываются в группе backend; отдельные Python/Node test files — в группе тестов. Существовавшие до C выдача ИС-7, базовые генераторы, авторизация по email и большая часть сайта не перечислены как новая ночная работа.

**Backend Rust**

| Файл | Изменение | Назначение |
|---|---|---|
| [tools/wg_probe/src/gateway091.rs](<D:/WoT_9.1_Server/tools/wg_probe/src/gateway091.rs>) | изменён | Повторный вход с тем же транспортным ключом: новая проверка попытки авторизации, nonce и закрытых UDP endpoints; ограниченное окно retirement, отказ старому peer до обработки ACK. Тесты политики находятся в этом же Rust-файле. |
| [tools/wg_probe/src/hangar091.rs](<D:/WoT_9.1_Server/tools/wg_probe/src/hangar091.rs>) | изменён | Приём согласованного profile3 с экипажем при сохранении прежнего досье ИС-7 и его cache cursor; отрицательные Rust-тесты смешанных версий и подмен. |

**Web и bridge**

| Файл | Изменение | Назначение |
|---|---|---|
| [web/src/game-adapter.mjs](<D:/WoT_9.1_Server/web/src/game-adapter.mjs>) | изменён | Подключение проверки неизменяемого r3-catalog3 и данных экипажа к существующему bridge и обзору аккаунта. |
| [web/src/ms1-crew.mjs](<D:/WoT_9.1_Server/web/src/ms1-crew.mjs>) | новый | Отдельная выдача тестового экипажа: validate/plan/apply/rollback, журнал и проверка прежнего profile2; проекция profile3 для сайта. |
| [web/views/account.ejs](<D:/WoT_9.1_Server/web/views/account.ejs>) | изменён | Текст в личном кабинете различает назначенный экипаж МС-1 и пустой экипаж; незагруженный боекомплект отображается явно. |

**Клиентские authored adapters/диагностика**

| Файл | Изменение | Назначение |
|---|---|---|
| [client_patch/account_switch_scenario.py](<D:/WoT_9.1_Server/client_patch/account_switch_scenario.py>) | новый | Диагностический сценарий primary → secondary → primary в одном EXE, полные снимки каждого аккаунта и освобождение временных native references. |
| [client_patch/crew_capabilities.py](<D:/WoT_9.1_Server/client_patch/crew_capabilities.py>) | новый | Обратимое ограничение неподдержанных действий с экипажем и входа в личное дело; родной просмотр экипажа в ангаре сохранён. |
| [client_patch/hangar_bootstrap.py](<D:/WoT_9.1_Server/client_patch/hangar_bootstrap.py>) | изменён | Установка ограничения экипажа до создания родного BusinessHandler и снятие после завершения GUI. |
| [client_patch/hangar_capabilities.py](<D:/WoT_9.1_Server/client_patch/hangar_capabilities.py>) | изменён | К существующему ограничению смены модулей добавлены явные отказы для боя, внешнего вида и обслуживания; исходные данные техники не подменяются. |
| [client_patch/hangar_limits_scenario.py](<D:/WoT_9.1_Server/client_patch/hangar_limits_scenario.py>) | новый | Диагностика МС-1 → ИС-7 → профиль → возврат, complex tooltip и запрета боя с проверкой неизменности экипажа. |
| [client_patch/hangar_relogin_scenario.py](<D:/WoT_9.1_Server/client_patch/hangar_relogin_scenario.py>) | новый | Родной logoff → LoginView → повторный вход одним аккаунтом внутри того же EXE, без сброса кэша. |
| [client_patch/hangar_windows_scenario.py](<D:/WoT_9.1_Server/client_patch/hangar_windows_scenario.py>) | новый | Проверка двух предупреждений для внешнего вида и обслуживания, состояния native containers и трёх снимков экипажа. |
| [client_patch/long_hangar_scenario.py](<D:/WoT_9.1_Server/client_patch/long_hangar_scenario.py>) | новый | Длительное наблюдение одного ангара: не менее 181 original stats return за 900 секунд, три снимка данных и два PNG; завершение по наблюдаемому условию. |
| [client_patch/ms1_crew_probe.py](<D:/WoT_9.1_Server/client_patch/ms1_crew_probe.py>) | новый | Экспорт двух TankmanDescr через оригинальный API #717 и пассивное чтение реально полученного inventory/crew; без изменения аккаунта. |
| [client_patch/ms1_crew_scenario.py](<D:/WoT_9.1_Server/client_patch/ms1_crew_scenario.py>) | новый | Родной показ экипажа МС-1, проверка отказа неподдержанного действия и неизменности данных, создание диагностических PNG. |
| [client_patch/sr_interactive.py](<D:/WoT_9.1_Server/client_patch/sr_interactive.py>) | изменён | Подключение отдельных opt-in сценариев, пассивная запись native crew/battle/greeting/window/logoff/stats calls и штатный выход после завершённого наблюдения. |

**Инструменты и verifiers**

| Файл | Изменение | Назначение |
|---|---|---|
| [tools/account_switch_expectations.py](<D:/WoT_9.1_Server/tools/account_switch_expectations.py>) | новый | Read-only ожидания для двух закреплённых аккаунтов: независимое чтение fixture/payload и сравнение identity, машин, экипажа и досье. |
| [tools/diagnostic_client_run.py](<D:/WoT_9.1_Server/tools/diagnostic_client_run.py>) | новый | Отдельный запуск одноразовой диагностики с проверкой control, исходников и capture budget; без внешнего таймера завершения EXE. |
| [tools/interactive_client.py](<D:/WoT_9.1_Server/tools/interactive_client.py>) | изменён | Подготовка, установка и откат новых compiled modules и точечного приветствия; opt-in настройки диагностики и сохранение before/backup/ledger. |
| [tools/ms1_crew_state.py](<D:/WoT_9.1_Server/tools/ms1_crew_state.py>) | новый | Неизменяемый profile3 и payload с двумя реально экспортированными танкистами; точная обратимость добавки к profile2, сохранение shop/dossier. |
| [tools/project_greeting_resources.py](<D:/WoT_9.1_Server/tools/project_greeting_resources.py>) | новый | Ограниченный MO parser и замена только ключа connected в проверенном оригинальном каталоге; остальные 655 значений сохраняются. |
| [tools/retired_base_probe.py](<D:/WoT_9.1_Server/tools/retired_base_probe.py>) | новый | Три точных повтора собственных ранее записанных BaseApp datagrams с освобождённого старого peer; проверки готовности, provenance и покадровый журнал отправок. |
| [tools/verify_account_switch.py](<D:/WoT_9.1_Server/tools/verify_account_switch.py>) | новый | Независимая проверка трёх последовательных native sessions, изоляции двух аккаунтов, кэшей, снимков и изображений. |
| [tools/verify_hangar_limits.py](<D:/WoT_9.1_Server/tools/verify_hangar_limits.py>) | новый | Проверка исходных callbacks/streams, явного запрета боя, собственного приветствия, снимков и сохранения состояния. |
| [tools/verify_hangar_windows.py](<D:/WoT_9.1_Server/tools/verify_hangar_windows.py>) | новый | Проверка двух native предупреждений, установленной политики, отсутствия входов в неподдержанные окна и повторного входа с кэшем. |
| [tools/verify_inprocess_relogin.py](<D:/WoT_9.1_Server/tools/verify_inprocess_relogin.py>) | новый | Проверка двух входов в одном EXE: retirement, свежая авторизация, потоки данных и точное разбиение исходного capture. |
| [tools/verify_long_hangar.py](<D:/WoT_9.1_Server/tools/verify_long_hangar.py>) | новый | Одна непрерывная native session: сопоставление команд 501, ответов, исходных returns и ACK; длительность, данные, PNG и полный lifecycle. |
| [tools/verify_ms1_crew_native.py](<D:/WoT_9.1_Server/tools/verify_ms1_crew_native.py>) | новый | Независимая проверка native происхождения экипажа, точной добавки profile3, Flash-показа, сохранения данных и cached relogin. |
| [tools/verify_retired_base_replay.py](<D:/WoT_9.1_Server/tools/verify_retired_base_replay.py>) | новый | Проверка трёх неизменённых повторов и трёх отказов; полное разбиение original corpus и явно обозначенное представление для повторного анализа. |

**Отдельные файлы тестов**

| Файл | Изменение | Назначение |
|---|---|---|
| [tests/test_account_switch_control.py](<D:/WoT_9.1_Server/tests/test_account_switch_control.py>) | новый | Opt-in control для переключения аккаунтов, границы входных данных и исключение секретов из публичного metadata. |
| [tests/test_account_switch_expectations.py](<D:/WoT_9.1_Server/tests/test_account_switch_expectations.py>) | новый | Привязка ожиданий к двум настоящим fixture и отклонение подмен identity, payload и профиля. |
| [tests/test_account_switch_scenario.py](<D:/WoT_9.1_Server/tests/test_account_switch_scenario.py>) | новый | Последовательность трёх фаз, строгость снимков и хранение/очистка credentials на подставных unit boundaries. |
| [tests/test_account_switch_verifier.py](<D:/WoT_9.1_Server/tests/test_account_switch_verifier.py>) | новый | Отрицательные проверки изоляции аккаунтов, lifecycle, сегментов и точной публичной схемы control. |
| [tests/test_battle_capabilities.py](<D:/WoT_9.1_Server/tests/test_battle_capabilities.py>) | новый | Источник и сигнатуры родной кнопки боя, обратимая установка запрета и сохранение исходного update/tooltip lifecycle. |
| [tests/test_crew_capabilities.py](<D:/WoT_9.1_Server/tests/test_crew_capabilities.py>) | новый | Обратимый запрет неподдержанных операций с экипажем и личного дела, native readers и предупреждения. |
| [tests/test_diagnostic_client_run.py](<D:/WoT_9.1_Server/tests/test_diagnostic_client_run.py>) | новый | Control/preflight, bounds, capture reserve и поведение диагностического runner без внешнего kill. |
| [tests/test_hangar_limits_scenario.py](<D:/WoT_9.1_Server/tests/test_hangar_limits_scenario.py>) | новый | Последовательность переходов, native readiness, идентичность и экипаж, ожидание PNG; регрессия обращения к shared profile observer. |
| [tests/test_hangar_limits_verifier.py](<D:/WoT_9.1_Server/tests/test_hangar_limits_verifier.py>) | новый | Отрицательные проверки политики боя, приветствия, tooltip, снимков и парного cached прохода. |
| [tests/test_hangar_relogin_scenario.py](<D:/WoT_9.1_Server/tests/test_hangar_relogin_scenario.py>) | новый | Две фазы входа, реальная готовность LoginView, отказ входа, bounded failure и освобождение ссылок. |
| [tests/test_hangar_window_capabilities.py](<D:/WoT_9.1_Server/tests/test_hangar_window_capabilities.py>) | новый | Исходные entrypoint внешнего вида/обслуживания, отказ до вызова окна, идемпотентность и восстановление callbacks. |
| [tests/test_hangar_windows_scenario.py](<D:/WoT_9.1_Server/tests/test_hangar_windows_scenario.py>) | новый | Три шага сценария окон, неизменность экипажа/identity, actual view scan и сохранение readiness во время ожидания PNG. |
| [tests/test_hangar_windows_verifier.py](<D:/WoT_9.1_Server/tests/test_hangar_windows_verifier.py>) | новый | Подмены source/guard/actions, неверный view context, отсутствие снимков и ложные утверждения об открытых окнах. |
| [tests/test_inprocess_relogin_verifier.py](<D:/WoT_9.1_Server/tests/test_inprocess_relogin_verifier.py>) | новый | Разбиение двух sessions, новая авторизация/retirement, сведения о native попытках и lifecycle без ослабления старых проверок. |
| [tests/test_interactive_relogin_control.py](<D:/WoT_9.1_Server/tests/test_interactive_relogin_control.py>) | новый | Одноразовое подключение relogin, потребление private control и пассивные события без вывода credentials. |
| [tests/test_interactive_window_trace.py](<D:/WoT_9.1_Server/tests/test_interactive_window_trace.py>) | новый | Пассивный выбор четырёх оригинальных window entrypoints; собственные wrappers и чужие callbacks не считаются оригиналом. |
| [tests/test_long_hangar_control.py](<D:/WoT_9.1_Server/tests/test_long_hangar_control.py>) | новый | Подключение long scenario, точная публичная схема, запас capture, передача только primitive original-return notes и ошибка переполнения trace. |
| [tests/test_long_hangar_scenario.py](<D:/WoT_9.1_Server/tests/test_long_hangar_scenario.py>) | новый | Порог 181/900, непрерывность, снимки и bounded failure на подставных unit boundaries. |
| [tests/test_long_hangar_verifier.py](<D:/WoT_9.1_Server/tests/test_long_hangar_verifier.py>) | новый | Отрицательные проверки request/response/ACK, повторов, длительности, metadata и одного входа с учётом generator resumption. |
| [tests/test_ms1_crew_native_verifier.py](<D:/WoT_9.1_Server/tests/test_ms1_crew_native_verifier.py>) | новый | Подмены native export, descriptor, уровня/XP, identity, назначений и содержимого profile/payload. |
| [tests/test_ms1_crew_probe.py](<D:/WoT_9.1_Server/tests/test_ms1_crew_probe.py>) | новый | Bounds паспортов и getter-схемы; регрессия inventory.compDescr вместо принятия имён полей за inventory IDs. |
| [tests/test_ms1_crew_scenario.py](<D:/WoT_9.1_Server/tests/test_ms1_crew_scenario.py>) | новый | Порядок показа/отказа, неизменные снимки и проверки PNG на unit boundaries. |
| [tests/test_ms1_crew_state.py](<D:/WoT_9.1_Server/tests/test_ms1_crew_state.py>) | новый | Точная добавка к profile2, provenance оригинального экспорта, types/bounds и запрет подмен ресурсов/ИС-7/истории. |
| [tests/test_project_greeting_resources.py](<D:/WoT_9.1_Server/tests/test_project_greeting_resources.py>) | новый | Некорректные MO tables/ключи/placeholder, чужой hash и read-only проверка настоящего оригинального каталога. |
| [tests/test_retired_base_probe.py](<D:/WoT_9.1_Server/tests/test_retired_base_probe.py>) | новый | Отсутствие socket при плохом preflight, точный bind, прерывание после частичной отправки, bounds и чтение ранее принятого corpus без отправки. |
| [tests/test_retired_base_replay_verifier.py](<D:/WoT_9.1_Server/tests/test_retired_base_replay_verifier.py>) | новый | Исчерпывающее разбиение пакетов/логов, точные checkpoints и отклонение пропуска, подмены или четвёртого повтора. |
| [web/tests/account-crew-display.test.mjs](<D:/WoT_9.1_Server/web/tests/account-crew-display.test.mjs>) | новый | Рендер личного кабинета для профилей 1/2/3: назначение экипажа отображается отдельно от пустого боекомплекта. |
| [web/tests/ms1-crew.test.mjs](<D:/WoT_9.1_Server/web/tests/ms1-crew.test.mjs>) | новый | Plan/apply/rollback на изолированной SQLite, журнал, неизменность данных, отказ подмен и HTTP-проекция собственного profile3. |

**Документы относительно того же baseline**

Ниже отдельный список 20 новых/изменённых документов. Назначение взято из фактического заголовка файла. Их редакционные изменения после указанного времени должны попадать в отдельный финальный архив root.

| Документ | Изменение | Заголовок / содержание |
|---|---|---|
| [MISSING_INPUTS.md](<D:/WoT_9.1_Server/MISSING_INPUTS.md>) | изменён | Недостающие данные и незакрытая приёмка |
| [README.md](<D:/WoT_9.1_Server/README.md>) | изменён | Стальной рубеж |
| [docs/01_SCOPE.md](<D:/WoT_9.1_Server/docs/01_SCOPE.md>) | изменён | 01. Цель, границы и уровни готовности |
| [docs/STATUS.md](<D:/WoT_9.1_Server/docs/STATUS.md>) | изменён | Статус проекта |
| [docs/plans/OVERNIGHT_20261005.md](<D:/WoT_9.1_Server/docs/plans/OVERNIGHT_20261005.md>) | новый | Ночная работа05.10.2026 |
| [docs/plans/P02_account_switch.md](<D:/WoT_9.1_Server/docs/plans/P02_account_switch.md>) | новый | P02 — изоляция аккаунтов при переключении внутри EXE |
| [docs/plans/P02_hangar_service_limits.md](<D:/WoT_9.1_Server/docs/plans/P02_hangar_service_limits.md>) | новый | P02 — границы доступных действий ангара |
| [docs/plans/P02_hangar_windows.md](<D:/WoT_9.1_Server/docs/plans/P02_hangar_windows.md>) | новый | P02 — честные границы неподключённых окон ангара |
| [docs/plans/P02_inprocess_relogin.md](<D:/WoT_9.1_Server/docs/plans/P02_inprocess_relogin.md>) | новый | P02 — повторный вход в одном процессе |
| [docs/plans/P02_long_hangar.md](<D:/WoT_9.1_Server/docs/plans/P02_long_hangar.md>) | новый | P02 — длительный готовый ангар и родной периодический обмен |
| [docs/plans/P02_ms1_crew.md](<D:/WoT_9.1_Server/docs/plans/P02_ms1_crew.md>) | изменён | P02 — минимальный серверный экипаж МС-1 |
| [docs/plans/P02_retired_base_replay.md](<D:/WoT_9.1_Server/docs/plans/P02_retired_base_replay.md>) | новый | P02 — поздние пакеты закрытого BaseApp peer |
| [docs/research/OVERNIGHT_20261005.md](<D:/WoT_9.1_Server/docs/research/OVERNIGHT_20261005.md>) | новый | Ночная работа 5 октября 2026 года |
| [docs/research/P02_ACCOUNT_SWITCH.md](<D:/WoT_9.1_Server/docs/research/P02_ACCOUNT_SWITCH.md>) | новый | P02 — смена двух аккаунтов в одном клиентском процессе |
| [docs/research/P02_HANGAR_SERVICE_LIMITS.md](<D:/WoT_9.1_Server/docs/research/P02_HANGAR_SERVICE_LIMITS.md>) | новый | P02 — границы доступных действий ангара |
| [docs/research/P02_HANGAR_WINDOWS.md](<D:/WoT_9.1_Server/docs/research/P02_HANGAR_WINDOWS.md>) | новый | P02 — границы неподключённых окон ангара |
| [docs/research/P02_INPROCESS_RELOGIN.md](<D:/WoT_9.1_Server/docs/research/P02_INPROCESS_RELOGIN.md>) | новый | P02 — выход и повторный вход внутри одного EXE |
| [docs/research/P02_LONG_HANGAR.md](<D:/WoT_9.1_Server/docs/research/P02_LONG_HANGAR.md>) | новый | P02 — длительный ангар и периодический native обмен |
| [docs/research/P02_MS1_CREW.md](<D:/WoT_9.1_Server/docs/research/P02_MS1_CREW.md>) | новый | P02 — экипаж МС-1 |
| [docs/research/P02_RETIRED_BASE_REPLAY.md](<D:/WoT_9.1_Server/docs/research/P02_RETIRED_BASE_REPLAY.md>) | новый | P02 — настоящие поздние BaseApp packets закрытого аккаунта |

**Воспроизводимость и границы**

Полные `before`/`after` SHA-256 и размеры всех 317 файлов: [local/evidence/20261005-overnight-final/source-inventory-01/manifest.json](<D:/WoT_9.1_Server/local/evidence/20261005-overnight-final/source-inventory-01/manifest.json>).

- SHA-256 baseline manifest: `9ddafbc4e626f3a7783ad27f5a8d1f588874dc7a6af28d2e694b88699d25b73d`.
- SHA-256 baseline ZIP: `9f106815c4d6bb300838089361adc15ade9670949e184baa1fb73c985f775dba`.
- SHA-256 manifest этого среза: `98fccc954f306f9d66c8ac648143a91408485d09f173f93bba9f03ff12c4f748`.
- **PASS:** 253/253 записей исходного архива; SHA/размер текущих файлов; повторное чтение против изменения во время снимка; полнота групп и ссылок этого списка.
- **NOT_RUN в этой задаче:** повторные native/HTTP/Rust/Python/Node функциональные тесты. Этот индекс фиксирует состав файлов, а не заменяет приёмку карточек.
- **Откат этой задачи:** удалить только этот новый Markdown-индекс и его локальные evidence-файлы. Игровое состояние, конфигурация и клиентские копии при создании индекса не менялись.

Повторное сравнение создаёт новый снимок; существующие evidence не перезаписываются:

```powershell
python -B -X utf8 local/evidence/20261005-overnight-final/source_inventory.py --out local/evidence/20261005-overnight-final/source-inventory-02
```

Единственный следующий шаг для этого указателя — включить документ в финальный архив authored sources после завершения редакционных правок root. Самоиндекс не хеширует себя.
