# P02: восстановление локальной службы после устаревшего lock

Дата: 2026-10-06, Asia/Yekaterinburg. Статус: **PASS_LOCAL_SERVICE_RECOVERY**.
Область: lifecycle локального стенда; сетевые и физические алгоритмы поездки
не менялись. Родной клиент в этой карточке не запускался.

## Проблема и доказательства

VERIFIED: `tools/local_server.py` до изменения отклонял любой существующий
supervisor.lock; status выводил сохранённый state.json без проверки процессов.
Старые PID supervisor88676/identity82056/gateway39372 были подтверждённо
отсутствующими (Windows OpenProcess, ошибка87), но state продолжал содержать
RUNNING. Точные файлы и SHA256: `E/baseline-01/manifest.json`, где
`E=local/evidence/20261006-service-recovery/`; наблюдение `E/observed-before.json`.

UNKNOWN: почему исчезли прежние процессы. Без журнала причины нельзя объявлять
аварию сервера, перезагрузку ПК или закрытие пользователем установленным фактом.

## Изменение

`tools/service_lifecycle.py` проверяет PID через Windows process handles, без
сигналов завершения. Статус различает recorded_status и фактические наблюдения:
STALE/ORPHANED/UNKNOWN/BUSY/INCONSISTENT/DEGRADED и обычные RUNNING/STOPPED.
Живой PID считается блокирующим даже при вероятном повторном использовании.
Отказ доступа также блокирует восстановление.

Операции восстановления и создания собственного supervisor.lock используют
OS byte lock `local/server/supervisor.lifecycle`. ОС освобождает его при смерти
владельца; файл может оставаться. Shared bare-PID supervisor.lock сохраняет
совместимость с существующими offline операциями экипажа/боеприпасов.

`start` автоматически восстанавливает только известное состояние: владелец
lock совпадает с supervisor state, все ещё не подтверждённо завершённые PID
отсутствуют, state/run/config принадлежат той же службе, игровые порты свободны.
После port preflight повторно проверяются байты и процессы. До изменения
создаётся recovery archive с точными bytes/SHA256 и receipt RECOVERY_PREPARED;
после восстановления receipt обновляется атомарно. Неизвестные exit_code
сохраняются, успешные завершения не выдумываются.

`serve` покрывает гарантированной очисткой lock раннюю подготовку run/state,
включая ошибку записи PID. Чужой, заменённый или частичный lock сохраняется.
`stop` умеет обработать доказанный STALE и при обычной остановке ждёт удаления
lock. Статус остаётся операцией только чтения.

## Реально выполненные проверки

| Проверка | Результат | Доказательство |
|---|---|---|
| Lifecycle matrix, 36 tests | PASS | `E/lifecycle-tests-02.log`, `.json` |
| Windows живой/завершённый subprocess | PASS | Тесты probe_pid в том же логе |
| Guard contention, освобождение после смерти, два владельца | PASS | Тесты реальных temporary Python processes в том же логе |
| Живой/переиспользованный PID, отказ доступа, maintenance owner, изменившиеся записи | PASS_LOCAL_CONTROLS | Изолированные отрицательные тесты; не проверка клиента |
| Ранний сбой записи PID и очистка после contention | PASS_LOCAL_CONTROLS | Lifecycle tests; инъекции собственных операций |
| Map-drive integration/capture/arena control regression, 7+7+51 | PASS | `E/regression.json`, три `test_*.log` |
| Обычный запуск исходной командой | PASS | `E/start-01.command.json`, stdout/stderr |
| Живые PID, identity/web health | PASS | `E/runtime-after-01.json`, service/health fields |
| Повторный start при живой службе | PASS_EXPECTED_REJECTION | `E/duplicate-start.json`; bytes state/lock неизменны |
| Пять конфигураций, полный семантический дамп игровой БД | PASS_UNCHANGED | `E/runtime-after-01.json` |
| Полный семантический дамп БД сайта | PARTIAL_DATA_CHANGED | Тот же receipt; не переименован в PASS |
| Родной вход и ручная поездка после восстановления | NOT_RUN | Выполняет владелец без таймера и управления ПК |

Сохранён ранний ошибочный тестовый прогон `E/lifecycle-tests-01.log`: harness
инъекции не предоставлял close; обработка записи переработана с закрытием stream
через context manager. Реальный отдельный startup в09:49 также сохранил FAILED
из-за отсутствующего внешнего сайта: `local/server/run-20261006T044932-f912cf/`
(не приписывается владельцу).
Успешный обычный run: `local/server/run-20261006T045129-130e11`.

Внешний сайт был подтверждённо остановлен, TCP3091 свободен. Запущен отдельно с
сохранёнными WEB_HOST/PORT/ORIGINS и тем же portal_data, без изменения ownership:
`E/start-existing-website.ps1`, `E/website-start.json`. После запуска PID43164
слушает прежний0.0.0.0:3091; игровые endpoints остались127.0.0.1:20014/20016,
identity127.0.0.1:20020. Этот script является одноразовым evidence, не общим launcher.

## Данные и ограничения

VERIFIED: игровой DB dump и пять конфигураций совпадают с утренним снимком.
Полный DB dump сайта отличается. Таблица users (3 строки) и rate_limits
совпадают с сохранённым SQLite эталоном ночной карточки; в этом эталоне одна
истёкшая sessions строка, в текущей базе их0:
`E/identity-table-comparison.json`, `E/data-preservation-addendum.json`.

INFERRED: изменение полного дампа сайта связано со штатной очисткой истёкших
sessions/rate_limits в `web/src/store.mjs:122` при запуске. UNKNOWN: точный
набор изменившихся утренних строк — до старта был сохранён общий semantic hash,
а не отдельный снимок каждой таблицы; ночной полный дамп не равен утреннему.
Нельзя заявлять полную неизменность portal.sqlite. Старые данные поверх текущей
БД для косметического PASS не восстанавливались.

Дополнительные ограничения: один PID не доказывает личность процесса; живые и
непроверенные PID блокируют recovery. Повреждённый/частичный/заменённый lock
автоматически не удаляется. Cleanup guard ждёт максимум5s, затем сообщает
ошибку. Физика остаётся test_lab; ручная плавность, стрельба и бой вдвоём этой
карточкой не проверялись.

## Команды

Из `D:\WoT_9.1_Server`:

```powershell
python -B -X utf8 tools/local_server.py status --config local/server/service.json
python -B -X utf8 tools/local_server.py start --config local/server/service.json --map-drive local/server/map-drive/pool.json
python -B -X utf8 tools/local_server.py recover --config local/server/service.json
python -B -X utf8 -m unittest discover -s tests -p test_service_lifecycle.py -v
python -B -X utf8 -m unittest discover -s tests -p test_map_drive_integration.py -v
python -B -X utf8 -m unittest discover -s tests -p test_map_drive_capture.py -v
python -B -X utf8 -m unittest discover -s tests -p test_arena_diagnostic_control.py -v
```

`start` нужен для остановленной службы; текущая уже работает. `recover` —
отдельная операция без запуска процесса; при живой службе получает отказ.
External website должен быть заранее поднят его существующим владельцем.

## Изменённые файлы и откат

- `tools/local_server.py`; новый `tools/service_lifecycle.py`.
- Новый `tests/test_service_lifecycle.py`.
- README.md, docs/STATUS.md; новый план P02_service_recovery.md и этот отчёт.
- Локальные evidence/runtime records; исходники web, клиент и игровой бинарник
  не менялись. Git local exclusions проверены.

Для отката реализации сначала закрыть игру и штатно остановить собственный
backend новой версией:

```powershell
python -B -X utf8 tools/local_server.py stop --config local/server/service.json
```

Затем сверить before/after manifest и вернуть tools/local_server.py из
`E/baseline-01/tools/local_server.py`; убрать новые helper/test и при желании
восстановить прежние README/STATUS. Архивы recovery и evidence сохраняются.
Старые RUNNING state/PID/lock поверх остановленной службы не возвращать:
это диагностические backups, а не рабочее состояние. БД и внешний сайт этим
откатом не заменяются и не останавливаются.

Единственный следующий шаг: ручной круг МС-1 через установленный normal014 —
«В бой!», W/S/A/D, задний ход с камерой, препятствие, возврат и повторная поездка.
