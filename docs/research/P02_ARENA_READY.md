# P02 — настоящая готовность клиента и серверная подготовка арены

2026-10-05. Карточка из [плана](../plans/P02_arena_ready_countdown.md).
O = `local/evidence/20261005-p02-arena-ready/`, N = предыдущая карточка
`local/evidence/20261005-p02-arena-entry/`. Все команды ниже выполняются из
`D:\WoT_9.1_Server`. Клиент #717 и исходные ресурсы не публикуются.

## Результат и границы

Настоящий Ready01: Account → Avatar → Карелия → собственный МС-1 →
родной `setClientReady` → серверный PREBATTLE → уменьшающийся родной таймер.
Клиент PID27912 работал90.528s, завершился сам с exit0;247 захваченных пакетов,
8202B. Снимки действительно просмотрены: **00:27 → 00:21**. Это узкая приёмка
подготовки арены, не приёмка полного боя. Независимая приёмка **18/18 PASS**:
`O/data/verify-ready01-final-02/arena-ready-native-verification.json`, SHA256
`094edf304e3b39f6871440f2793df22a5a73ee9f16c1ee0dcc7bf051e7e272f8`.
Финальная сверка filesystem/ordinary состояния имеет отдельный результат:
`O/final-audit-01/final-state-audit.json`; native18/18 не заменяет этот аудит.

Никаких действий мышью/клавиатурой и внешнего EXE kill/timeout не было.
Вход выполнен явным диагностическим вызовом оригинального LoginView.onLogin,
что не является доказательством ручного ввода. Выход запрошен клиентским
сценарием после наблюдения нужных условий. Счётчик времени интерфейса,
`BigWorld.serverTime`, original GUI/lifecycle не подменялись.

## Что подтверждено

| Категория | Вывод | Доказательство |
|---|---|---|
| VERIFIED | Native прислал целую33B связку: bindToVehicle, vehicle_changeSetting, setClientReady, autoAim; ready принимается после ACK именно create97 | `O/ready01-prepare/wire/`, пакет218, client sequence20; gateway-span.log |
| VERIFIED | Только ready применён как доменное действие; три соседних метода явно unsupported и не применены | `ARENA_READY_ACCEPTED`, три `AVATAR_METHOD_UNSUPPORTED`, `domain_applied=false` |
| VERIFIED | Сервер ответил51B: native frequency10, gameTicks1000, updateArena7 ownVehicle ready, updateArena3 `(2,130.0,30.0,None)` | пакет220, reliable sequence58; `tools/wg_probe/src/arena_ready091.rs`, независимый native parser |
| VERIFIED | Дедлайн на сервере создаётся по Instant, однократно; повторы не сдвигают его; expiry никогда не начинает BATTLE | source archive `O/server-rebuild-01/sources/`;162 Rust tests |
| OBSERVED | Original Battle/Flash показали уменьшающийся таймер; семь различных уменьшающихся значений на принятом интервале, native clock6.036s | `O/ready01-runtime/native-27912-1791197671175.jsonl`; native_countdown gate |
| OBSERVED | Ровно2 native PNG: карта, МС-1, HUD90/90,27 и21 секунды | `O/ready01-runtime/screenshots/`, `O/ready01-visual-review.json` |
| VERIFIED | Original LightManager нужен ветке PREBATTLE и запускается штатно; native disabled-режим допустим | `O/gui/period-services-01/`, `arena_ready_light` init_return(enabled=false) |
| OBSERVED | Original timer/Flash/Avatar/Vehicle и LightManager завершились; четыре стадии cleanup PASS, exit0, installer restore PASS | actual trace, native-outcome.json, `O/gui/native-ready01-review-02/` |

Частота10 и шкала100→130 — явные параметры нашего лабораторного опыта.
Они не объявлены исторической tickrate сервера. Подтверждена короткая native
привязка времени; длительная синхронизация, RTT-компенсация и clock drift UNKNOWN.
Серверное истечение30s проверено unit-тестами; настоящий клиент завершился
раньше, поэтому native expiry этой конкретной подготовки **NOT_RUN**.

Контракты оригинала: `Battle.pyc` SHA256
`aa43bc6b7e1f7ae9e2bba03fa527a9e6ce95a5d41ef23f26785b1490cd6f38de`,
`Flash.pyc` SHA256
`059aad4f6ed0d3ce5b82e8a819dd0f0181e403ef25c803bfc7e452a621495dc4`.
Battle.__setArenaTime:841 normal RETURN1045; __callEx:940 RETURN23;
Flash.call:125 RETURN62. Flash.call действительно добавляет имя метода
в переданный список — profiler сохраняет отдельные копии до/после вызова.
Generic flash_bound не используется как доказательство для Battle: у него
поле movie. Полные offsets/хеши: `O/gui/countdown-contract-01/FINDINGS.md`.

## Состояние сохранено

До изменений: `O/baseline-01/`,365 authored sources,17 local files,
две согласованные SQLite backups; `O/normal011-prerollback-01/` сохраняет
29 immutable файлов и3 owner logs. Original только читался.
Архив сборки и прежний EXE: `O/server-rebuild-01/`. Новый EXE SHA256
`807fe8e6da0e5969b5b521450bb616e2c94695603e0c746bb28a91eee879fa7a`.

Автоматически созданный replay2096B сохранён отдельно, SHA256
`bcaf8dae60b2bd9f3890e449d56d5d65001f3f8ceb021e003c4d82c057211b6f`.
Baseline фиксировал отсутствие файла; header.dateTime и mtime связаны с
Ready01. Перед точечным удалением сохранены exact bytes, hash и proof.
Восстановление прежнего отсутствия: `O/ready01-replay/restore.json`, SHA256
`b68f74978d7844c31b0ee7d67a23a1812dc74a4589bbdc929684b9cb5c456217`.
Ранний helper не проверял дату replay; isolated negative control это выявил.
Helper исправлен **до реального удаления**,14 проверок PASS:
`O/wire/replay-guard-fix-01/`. Старый replay не затрагивался.

Gateway возвращён в обычный `legacy091-interactive`, без capture/arena trigger:
`O/ordinary-server-01/`, run `local/server/run-20261005T105936-a33e1a`.
Сайт этой карточкой не перезапускался. Установлен `local/client-install-012`:
21modules,30immutable+3ownerlogs; без control/autologin/autoquit/capture.
Клиент закрыт. Обычный вход открывает ангар. Ручной вход именно с normal012
**NOT_RUN**; диагностический реальный запуск использовал те же исходники.

## Изменённые файлы

- `tools/wg_probe/src/arena_ready091.rs` (новый), `gateway091.rs`,
  `arena_control091.rs`, `main.rs`: отдельный opt-in ready-режим и его tests.
- `client_patch/arena_ready_scenario.py` (новый), `sr_interactive.py`:
  пассивное наблюдение, оригинальный LightManager и штатное завершение.
- `tools/interactive_client.py`, `diagnostic_client_run.py`, `local_server.py`:
  сборка21модуля, проверка provenance, явный диагностический режим.
- `tools/verify_arena_ready_native.py` (новый),
  `tests/test_arena_ready_native.py` (новый),
  `tests/test_arena_ready_scenario.py` (новый),
  `tests/test_arena_diagnostic_control.py`: независимые проверки и guards.
- `README.md`, `docs/STATUS.md`, `MISSING_INPUTS.md`, этот отчёт,
  план и [исследование физики](PHYSICS_AUTHORITY.md).

Старые arena helpers/verifiers и источники прежних принятых экспериментов
не переписывались. Evidence/резервные копии/ресурсы/credentials остаются в
игнорируемом local. Работа отдельной сессии сайта в приёмку не включается.

## Повторные проверки

```powershell
python -B tests/test_arena_diagnostic_control.py
python -B tests/test_diagnostic_client_run.py
python -B tests/test_ms1_ammo_profile.py
python -B tests/test_arena_ready_scenario.py
local\toolchains\python-2.7.3-x86\python.exe -B tests/test_arena_ready_scenario.py
python -B tests/test_arena_ready_native.py
```

Сохранённые первоначальные результаты:31 control +40 runner +18 profile
PASS (`O/root-checks-01/`);47 scenario Python3 PASS,46 Python2.7.3 PASS и1
host-only static-reader SKIP, отдельно проверенный на Python3
(`O/gui/scenario-checks-01/`);162 Rust PASS (`O/wire/ready-integration-01/`),
33 verifier tests PASS (`O/data/ready-verifier-checks-final-02/`).
Независимый GUI/lifecycle review15/15 PASS (`O/gui/native-ready01-review-02/`).
Первый review-helper FAIL сохранён: старое ammo-событие превышало ошибочный
лимит8KiB. Исправлен только reader до прежнего штатного64KiB; новые ready
события остаются меньше8KiB. Клиент и исходный corpus не переписывались.
Дополнительный review выявил четыре семейства слишком мягких проверок
анализатора: типы source metadata, обязательный afterCreate, свежесть привязки
PNG к итерации и границу teardown. Отрицательные RAM-копии были ошибочно
приняты старым reader; native corpus не имел этих дефектов. Проверки усилены,
33 regression tests PASS и тот же Ready01 повторно принят18/18 новым reader.
Прежний final01 и source snapshot сохранены; действующий отчёт — final02.
Для текущих Rust-исходников используйте закреплённое окружение toolchain:

```powershell
. .\tools\rust_env.ps1
cargo test --offline --locked --manifest-path tools/wg_probe/Cargo.toml
```

Для повторной независимой проверки сохранённого Ready01 без запуска игры
полная команда со всеми локальными путями и новым output записана в
`O/data/ready-verifier-checks-final-02/repeat-command.ps1.txt`.
Это обычный текст для просмотра/копирования, не новая приёмка native запуска.
Verifier SHA256 `74e7c3aeabea3c76c1fc96ca015cb66f464812533bc4f3bb82d1332775b3252b`.

Исторические точные native-команды записаны в
`O/ready01-prepare.command.json`, `O/server-rebuild-01/*.command.json` и
`O/ordinary-server-01/*.command.json`. Сам runner был запущен так:

```powershell
python -B -X utf8 tools/diagnostic_client_run.py --install local/evidence/20261005-p02-arena-ready/ready01-prepare --service local/server/service.json
python -B -X utf8 local/evidence/20261005-p02-arena-ready/trigger_ready01.py
```

Эти конкретные one-shot каталоги уже использованы и повторно не запускаются:
сначала нужно штатно откатить ordinary пакет при закрытом клиенте, подготовить
новый readyNN с явным control, собственным capture/trigger и baseline replay.
Копирование старого native-outcome или удаление кэша не заменяет новый опыт.

Обычный сервер и ручной запуск уже установленного EXE:

```powershell
python -B -X utf8 tools/local_server.py status --config local/server/service.json
python -B -X utf8 tools/local_server.py start --config local/server/service.json
Start-Process -FilePath 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research\WorldOfTanks.exe' -WorkingDirectory 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research'
```

## Неизвестное и следующий шаг

**NOT_RUN:** BATTLE, native Avatar ammo transfer, авторитетное движение,
контакт с грунтом, стрельба/попадания, второй игрок и завершение боя.
Звук не оценивался. В PNG остаётся цветная сетка UNKNOWN; свежий графический
лог содержит DEVICE_LOST/RESET и shader warnings, подобные прежним. Чистый
Python lifecycle не означает «вообще никаких ERROR во всех логах».
Стабильность за пределами измеренного интервала не заявляется.

Новых файлов или ручных действий владельца для принятого отсчёта не требуется.
На gateway пока одна активная сессия. Физическая библиотека и локальные
клиентские hooks разобраны в [PHYSICS_AUTHORITY](PHYSICS_AUTHORITY.md).

**Один следующий проверяемый шаг:** отдельный ограниченный native эксперимент
с одной командой движения собственного МС-1 и серверным обновлением положения,
с захватом настоящих сообщений и реакции фильтра. Полноценный контроллер и
историческая физика требуют последующих измерений. В этой карточке он не начат.

## Откат

При закрытом клиенте штатно снять normal012:

```powershell
python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-012
```

Это восстанавливает исходные файлы research из проверенного ledger;
original не затрагивается. Для полного возврата к состоянию до карточки:
остановить собственный supervisor через local_server.py stop, восстановить
только перечисленные изменённые исходники из `O/baseline-01/project-before.zip`,
вернуть EXE из `O/server-rebuild-01/gateway-before.exe` с проверкой SHA256
`40513e0cead8cb6193b9737293c45423d70c048cdf8ef8d613ed9584a68e6230`, затем
подготовить **новый** ordinary package прежними исходниками и запустить сервер.
Не распаковывать архив поверх проекта целиком: сторонняя web-работа сохраняется.
DB backups для этой карточки не восстанавливаются: игровые данные не менялись.
